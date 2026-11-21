"""Tests for transient retry requests and the sliding-window limiter."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.app.constants import CONSTANTS
from src.app.db.factory import get_repos
from src.app.deps import CurrentUser, get_current_user
from src.app.main import app
from src.app.rate_limit import SlidingWindowLimiter
from src.app.routes import practice
from src.audio_processing.contracts import (
    AudioRejected,
    InsufficientAudio,
    SttResult,
    SttUnavailable,
    WordTimestamp,
)


@pytest.fixture(autouse=True)
def setup_retry(monkeypatch):
    practice.limiter.reset()
    monkeypatch.setattr(practice, "probe", lambda *a, **k: None)
    monkeypatch.setattr(practice, "decode_to_master", lambda *a, **k: object())
    yield
    practice.limiter.reset()


def post(target="hello", kind="word"):
    return TestClient(app).post(
        "/api/practice/retry",
        data={"target_text": target, "kind": kind},
        files={"audio": ("sample.webm", b"fake audio", "audio/webm")},
    )


def stt(text):
    return SttResult(text, [WordTimestamp(x, 0, 1) for x in text.split()], "test", "test", [])


@pytest.mark.parametrize(
    ("target", "heard", "verdict"),
    [
        ("hello", "hello", "correct"),
        ("hello world", "hello", "not_yet"),
        ("hello", "um", "not_heard"),
        ("their", "there", "correct"),
    ],
)
def test_retry_verdict(monkeypatch, target, heard, verdict):
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt(heard))
    response = post(target)
    assert response.status_code == 200
    assert response.json()["verdict"] == verdict


def test_empty_and_cleanup(monkeypatch):
    paths = []

    def check(path, **kwargs):
        paths.append(Path(path))
        assert path.exists()

    def empty(*args, **kwargs):
        raise InsufficientAudio()

    monkeypatch.setattr(practice, "probe", check)
    monkeypatch.setattr(practice, "transcribe", empty)
    assert post().json()["verdict"] == "not_heard"
    assert paths and not paths[0].exists() and not paths[0].parent.exists()


def test_invalid_and_rate_limit(monkeypatch):
    assert post(kind="other").json()["error_code"] == "invalid_kind"
    assert post(target="  ").json()["error_code"] == "target_invalid"
    monkeypatch.setattr(practice, "limiter", SlidingWindowLimiter(1, 600))
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt("hello"))
    assert post().status_code == 200
    assert post().json()["error_code"] == "rate_limited"


def test_limiter_clock():
    now = [0.0]
    limiter = SlidingWindowLimiter(1, 10, lambda: now[0])
    assert limiter.hit("a") and not limiter.hit("a") and limiter.hit("b")
    now[0] = 10
    assert limiter.hit("a")
    limiter.reset()
    assert limiter.hit("a")


def test_close_and_insertions(monkeypatch):
    from types import SimpleNamespace

    item = SimpleNamespace(
        ref_index=0, ref_word="hello", hyp_word="hallo", status="near_miss", homophone=False
    )
    insertion = SimpleNamespace(ref_index=None, status="ins")
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt("hallo extra"))
    monkeypatch.setattr(practice, "align", lambda *a, **k: SimpleNamespace(items=[item, insertion]))
    result = post().json()
    assert result["verdict"] == "close"
    assert len(result["words"]) == 1


def test_temp_deleted_on_unexpected_error(monkeypatch):
    paths = []
    monkeypatch.setattr(practice, "probe", lambda path, **k: paths.append(Path(path)))

    def fail(*args, **kwargs):
        raise RuntimeError("failure")

    monkeypatch.setattr(practice, "transcribe", fail)
    with pytest.raises(RuntimeError):
        post()
    assert paths and not paths[0].exists() and not paths[0].parent.exists()


def test_unauthenticated():
    app.dependency_overrides.pop(get_current_user)
    assert post().status_code == 401


def test_does_not_use_repositories(monkeypatch):
    def fail():
        raise AssertionError("repository access")

    app.dependency_overrides[get_repos] = fail
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt("hello"))
    assert post().status_code == 200


def test_validation_and_user_limits(monkeypatch):
    monkeypatch.setattr(practice, "limiter", SlidingWindowLimiter(1, 600))
    def fail(*args, **kwargs):
        raise AssertionError("STT called for invalid input")

    monkeypatch.setattr(practice, "transcribe", fail)
    for target, kind, error in [
        ("hello", "other", "invalid_kind"),
        ("!!!", "word", "target_invalid"),
        ("...", "word", "target_invalid"),
        ("a" * 501, "word", "target_invalid"),
    ]:
        response = post(target, kind)
        assert response.status_code == 422 and response.json()["error_code"] == error
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt("hello"))
    assert post().status_code == 200
    assert post().status_code == 429
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=UUID("00000000-0000-4000-8000-000000000002"), email="b@example.com"
    )
    assert post().status_code == 200


def test_empty_alignment_is_invalid(monkeypatch):
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt("hello"))
    monkeypatch.setattr(
        practice, "align", lambda *a, **k: SimpleNamespace(items=[SimpleNamespace(ref_index=None)])
    )
    response = post()
    assert response.status_code == 422 and response.json()["error_code"] == "target_invalid"


def test_empty_limiter_entry_removed():
    now = [0.0]
    limiter = SlidingWindowLimiter(1, 10, lambda: now[0])
    assert limiter.hit("a")
    now[0] = 10
    limiter.limit = 0
    assert not limiter.hit("a")
    assert "a" not in limiter._hits
    assert not limiter.hit("new")
    assert "new" not in limiter._hits


def test_stt_unavailable_cleanup(monkeypatch):
    paths = []
    monkeypatch.setattr(practice, "probe", lambda path, **kwargs: paths.append(Path(path)))
    def fail(*args, **kwargs):
        raise SttUnavailable("unavailable")
    monkeypatch.setattr(practice, "transcribe", fail)
    response = post()
    assert response.status_code == 503 and response.json()["error_code"] == "stt_unavailable"
    assert paths and not paths[0].parent.exists()


@pytest.mark.parametrize("kind", ["word", "sentence"])
def test_probe_duration_and_rejection(monkeypatch, kind):
    def reject(path, **kwargs):
        assert kwargs["max_seconds"] == (
            CONSTANTS["retry"][f"{kind}_max_seconds"] + CONSTANTS["retry"]["server_grace_s"]
        )
        raise AudioRejected("too_long", "too long")
    monkeypatch.setattr(practice, "probe", reject)
    response = post(kind=kind)
    assert response.status_code == 422 and response.json()["error_code"] == "too_long"


@pytest.mark.parametrize(("target", "heard", "verdict"), [
    ("hello", "um hello", "correct"),
    ("hello world", "world", "not_yet"),
    ("cat", "bat", "close"),
])
def test_sentence_real_alignment(monkeypatch, target, heard, verdict):
    monkeypatch.setattr(practice, "transcribe", lambda *a, **k: stt(heard))
    response = post(target, "sentence")
    assert response.status_code == 200 and response.json()["verdict"] == verdict
