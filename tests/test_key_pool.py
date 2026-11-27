"""Several API keys per service: parsing, switching on quota/auth errors, error codes, safe logs."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from src.app import key_pool
from src.app.config import Settings
from src.app.key_pool import KeyPool, KeysExhaustedError
from src.audio_processing.contracts import MasterAudio, SttUnavailable
from src.audio_processing.stt import transcribe
from src.text_processing.contracts import ScriptGenerationError
from src.text_processing.groq_pool import PooledGroqClient
from src.text_processing.template_engine import TokenBucketLimiter, _call_llm_with_fallback


@pytest.fixture(autouse=True)
def fresh_pools(monkeypatch):
    """Pools are shared per key list; each test starts with none locked."""
    monkeypatch.setattr(key_pool, "_pools", {})


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# ---------- Settings: comma-separated lists ----------


def test_keys_are_split_on_commas(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", " k1, k2 ,, ")
    assert Settings(_env_file=None).groq_api_keys == ["k1", "k2"]


def test_single_key_is_a_list_of_one(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEYS", "only")
    assert Settings(_env_file=None).deepgram_api_keys == ["only"]


def test_old_single_key_name_is_not_read(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "old")
    assert Settings(_env_file=None).groq_api_keys == []


# ---------- KeyPool ----------


def test_quota_locks_key_then_next_key_is_used_until_cooldown_ends():
    clock = FakeClock()
    pool = KeyPool("svc", ["a", "b"], cooldown_s=60, clock=clock)
    assert pool.current() == "a"
    assert pool.report("a", 429) is True
    assert pool.current() == "b"
    clock.now = 61
    assert pool.current() == "a"  # cooldown over: back to the first key


def test_rejected_key_stays_locked():
    clock = FakeClock()
    pool = KeyPool("svc", ["a", "b"], cooldown_s=60, clock=clock)
    pool.report("a", 401)
    clock.now = 10_000
    assert pool.current() == "b"


def test_other_errors_do_not_lock_the_key():
    pool = KeyPool("svc", ["a"], cooldown_s=60)
    assert pool.report("a", 500) is False
    assert pool.report("a", None) is False
    assert pool.current() == "a"


def test_no_key_left_raises():
    pool = KeyPool("svc", ["a"], cooldown_s=60)
    pool.report("a", 402)
    with pytest.raises(KeysExhaustedError):
        pool.current()
    with pytest.raises(KeysExhaustedError):
        KeyPool("svc", []).current()


def test_scopes_are_counted_apart():
    pool = KeyPool("groq", ["a"], cooldown_s=60)
    pool.report("a", 429, scope="model-1")
    assert pool.current(scope="model-2") == "a"


def test_logs_show_position_not_key(caplog):
    pool = KeyPool("deepgram", ["secret-one", "secret-two"], cooldown_s=60)
    with caplog.at_level(logging.WARNING):
        pool.report("secret-two", 429)
    assert "deepgram key #2" in caplog.text
    assert "secret" not in caplog.text


# ---------- STT: every Deepgram key, then Gladia ----------


@pytest.fixture
def master(tmp_path):
    path = tmp_path / "a.wav"
    path.write_text("fake")
    return MasterAudio(path=path, duration_s=5.0, warnings=[])


def _stt_post(status_by_key: dict[str, int]):
    """requests.post stub: answers each key with the given status (200 = success)."""
    used: list[str] = []

    def post(url, headers=None, **kwargs):
        key = (headers or {}).get("Authorization", "").removeprefix("Token ") or headers.get(
            "x-gladia-key"
        )
        used.append(key)
        resp = MagicMock()
        status = status_by_key.get(key, 200)
        if status != 200:
            resp.raise_for_status.side_effect = requests.HTTPError(
                response=SimpleNamespace(status_code=status)
            )
        elif "deepgram" in url:
            resp.json.return_value = {
                "results": {"channels": [{"alternatives": [{"transcript": "hi", "words": []}]}]}
            }
        else:
            resp.json.return_value = {"prediction": "hi", "prediction_raw": {"words": []}}
        return resp

    return post, used


def _stt_settings():
    return SimpleNamespace(deepgram_api_keys=["dg1", "dg2"], gladia_api_keys=["gl1", "gl2"])


def test_deepgram_429_switches_to_next_deepgram_key(monkeypatch, master):
    post, used = _stt_post({"dg1": 429})
    monkeypatch.setattr("src.audio_processing.stt.requests.post", post)
    result = transcribe(master, settings=_stt_settings())
    assert result.provider == "deepgram"
    assert used == ["dg1", "dg2"]


def test_all_deepgram_keys_out_then_gladia(monkeypatch, master):
    post, used = _stt_post({"dg1": 429, "dg2": 401})
    monkeypatch.setattr("src.audio_processing.stt.requests.post", post)
    result = transcribe(master, settings=_stt_settings())
    assert result.provider == "gladia"
    assert used == ["dg1", "dg2", "gl1"]


def test_locked_key_is_skipped_on_the_next_request(monkeypatch, master):
    post, used = _stt_post({"dg1": 429})
    monkeypatch.setattr("src.audio_processing.stt.requests.post", post)
    transcribe(master, settings=_stt_settings())
    used.clear()
    transcribe(master, settings=_stt_settings())
    assert used == ["dg2"]


def test_server_error_goes_to_gladia_without_trying_other_deepgram_keys(monkeypatch, master):
    post, used = _stt_post({"dg1": 500})
    monkeypatch.setattr("src.audio_processing.stt.requests.post", post)
    assert transcribe(master, settings=_stt_settings()).provider == "gladia"
    assert used == ["dg1", "gl1"]


def test_every_key_out_gives_stt_unavailable(monkeypatch, master):
    post, _ = _stt_post({"dg1": 429, "dg2": 429, "gl1": 402, "gl2": 403})
    monkeypatch.setattr("src.audio_processing.stt.requests.post", post)
    with pytest.raises(SttUnavailable):
        transcribe(master, settings=_stt_settings())


# ---------- Groq: every key for one model, then the fallback model ----------


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def _groq_factory(status: dict[tuple[str, str], int], calls: list):
    """groq.Groq stub: answers (key, model) with the given status (200 = success)."""

    def factory(api_key):
        def create(model, **kwargs):
            calls.append((api_key, model))
            code = status.get((api_key, model), 200)
            if code != 200:
                raise _StatusError(code)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": 1}'))], usage=None
            )

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    return factory


def test_groq_tries_every_key_for_a_model_before_the_fallback_model(monkeypatch):
    monkeypatch.setattr("src.text_processing.template_engine.time.sleep", lambda s: None)
    calls: list = []
    status = {("k1", "m1"): 429, ("k2", "m1"): 429}
    client = PooledGroqClient(
        KeyPool("groq", ["k1", "k2"], cooldown_s=60), _groq_factory(status, calls)
    )
    data, model = _call_llm_with_fallback(
        [{"role": "user", "content": "x"}],
        ("m1", "m2"),
        TokenBucketLimiter(),
        10,
        client,
        max_retries=1,
    )
    assert (data, model) == ({"ok": 1}, "m2")
    assert calls == [("k1", "m1"), ("k2", "m1"), ("k1", "m2")]  # k1 still works for m2


def test_groq_every_key_out_gives_generation_unavailable(monkeypatch):
    monkeypatch.setattr("src.text_processing.template_engine.time.sleep", lambda s: None)
    status = {(k, m): 429 for k in ("k1", "k2") for m in ("m1", "m2")}
    client = PooledGroqClient(
        KeyPool("groq", ["k1", "k2"], cooldown_s=60), _groq_factory(status, [])
    )
    with pytest.raises(ScriptGenerationError) as err:
        _call_llm_with_fallback([], ("m1", "m2"), TokenBucketLimiter(), 10, client, max_retries=1)
    assert err.value.error_code == "generation_unavailable"
