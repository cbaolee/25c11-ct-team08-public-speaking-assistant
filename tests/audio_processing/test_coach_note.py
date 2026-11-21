from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.app.deps import get_current_user
from src.app.main import app
from src.audio_processing import coach_note as coach


@pytest.fixture
def result():
    return {
        "overall": 85,
        "components": {"accuracy": 85, "fluency": 60},
        "fluency_detail": {"wpm": 120.55},
        "sentences": [{"passed": True}],
        "alignment": [{"ref_word": "mp3", "hyp_word": "85", "status": "sub"}],
        "transcript": "private",
        "script": "private",
        "user_id": "private",
    }


def note(summary="Score 85.0"):
    return {"summary": summary, "strengths": [], "focus": [], "next_step": "Practise."}


def test_payload_and_numbers(result):
    payload = coach.build_payload(result, 1)
    assert not {"transcript", "script", "user_id", "session_id", "name", "email"} & payload.keys()
    assert len(payload["error_words"]) == 1
    assert payload["wpm"] == 120.6
    assert payload["sentences_meeting_cosine"] == 1
    assert coach.find_numbers("mp3 85.0") == {Decimal("85")}
    assert coach.validate_output(
        note(), payload, 900, Mock(check_text=Mock(return_value=SimpleNamespace(allowed=True)))
    )


@pytest.mark.parametrize(
    "bad", [None, {}, note("Score 999"), {**note(), "focus": ["a"] * 4}, note("x" * 901)]
)
def test_invalid_falls_back(result, bad):
    output = coach.generate_coach_note(result, None, cerebras=lambda *a: bad)
    assert output["source"] == "rule"


def test_moderation_and_rule(result):
    moderator = Mock()
    moderator.check_text.side_effect = [
        SimpleNamespace(allowed=False),
        SimpleNamespace(allowed=True),
    ]
    assert (
        coach.generate_coach_note(
            result, None, moderator=moderator, cerebras=lambda *a: note()
        )["source"]
        == "rule"
    )


def test_cerebras_rotation_and_missing(monkeypatch):
    post = Mock(side_effect=[SimpleNamespace(ok=False, status_code=429), _cerebras_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    settings = _cerebras_settings(keys=["rotation-one", "rotation-two"])
    assert coach.call_cerebras({}, settings, 1) == {}
    args, kwargs = post.call_args
    assert args[0] == coach._CEREBRAS_URL
    assert kwargs["headers"]["Authorization"] == "Bearer rotation-two"
    assert kwargs["json"]["model"] == "model"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}
    assert (kwargs["json"]["max_completion_tokens"]
            == coach.CONSTANTS["coach"]["max_completion_tokens"])
    assert kwargs["json"]["reasoning_effort"] == coach.CONSTANTS["coach"]["reasoning_effort"]
    post.reset_mock()
    settings.cerebras_api_keys = []
    assert coach.call_cerebras({}, settings, 1) is None
    settings.cerebras_api_keys = ["key"]
    settings.cerebras_model = " "
    assert coach.call_cerebras({}, settings, 1) is None
    post.assert_not_called()


def test_generate_cerebras_and_no_groq(result, monkeypatch):
    from src.text_processing import groq_pool

    def fail(*args, **kwargs):
        raise AssertionError("Groq must not be called")

    monkeypatch.setattr(groq_pool, "make_groq_client", fail)
    output = coach.generate_coach_note(result, None, cerebras=lambda *a: note())
    assert output["source"] == "cerebras"
    assert coach.generate_coach_note(result, None, cerebras=lambda *a: None)["source"] == "rule"


def test_cache():
    cache = coach.CoachNoteCache(10, clock=lambda: 0)
    cache.put("a", {"source": "rule"})
    assert cache.get("a") is None
    cache.put("a", {"source": "cerebras"})
    assert cache.get("a")["source"] == "cerebras"


def test_cache_put_removes_expired_entries_and_keeps_live_entries():
    now = [0]
    cache = coach.CoachNoteCache(10, clock=lambda: now[0])
    cache.put("expired", {"source": "cerebras"})
    now[0] = 5
    cache.put("live", {"source": "cerebras"})
    now[0] = 10
    cache.put("rule", {"source": "rule"})
    assert "expired" not in cache._entries
    assert cache.get("live")["source"] == "cerebras"
    assert cache.get("rule") is None


def test_endpoint_not_found_and_auth(endpoint_env):
    client = TestClient(app)
    response = client.post("/api/sessions/not-a-uuid/coach-note")
    assert response.status_code == 404 and response.json()["error_code"] == "session_not_found"
    app.dependency_overrides.pop(get_current_user)
    assert client.post("/api/sessions/not-a-uuid/coach-note").status_code == 401


@pytest.fixture
def endpoint_env(monkeypatch):
    from uuid import UUID

    from src.app.db.factory import build_memory_repos, get_repos
    from src.app.routes import coach as route

    repos = build_memory_repos()
    user_id = UUID("00000000-0000-4000-8000-000000000001")
    app.dependency_overrides[get_repos] = lambda: repos
    settings = _cerebras_settings(keys=["endpoint-key"])
    monkeypatch.setattr(route, "settings", settings)
    monkeypatch.setattr(route, "cache", coach.CoachNoteCache(3600))
    post = Mock(return_value=SimpleNamespace(ok=False, status_code=400))
    monkeypatch.setattr(coach.requests, "post", post)
    yield repos, user_id, post



def _endpoint_session(repos, user_id, result, status="ok"):
    from uuid import uuid4

    from src.app.db.models import NewSession

    return repos.sessions.create_session(
        user_id, NewSession(
            id=uuid4(), script_snapshot="Practice", status=status, result=result,
            result_schema_version="2.1",
        )
    )


def test_endpoint_ok_and_cache(endpoint_env, result):
    import json

    repos, user_id, post = endpoint_env
    post.return_value = _cerebras_ok(json.dumps(note()))
    row = _endpoint_session(repos, user_id, result)
    client = TestClient(app)
    responses = [client.post(f"/api/sessions/{row.id}/coach-note") for _ in range(2)]
    assert all(response.status_code == 200 for response in responses)
    assert set(responses[0].json()) == {"summary", "strengths", "focus", "next_step", "source"}
    assert responses[0].json()["source"] == "cerebras"
    assert responses[1].json() == responses[0].json()
    post.assert_called_once()


def test_endpoint_other_user(endpoint_env, result):
    from uuid import uuid4

    repos, _, post = endpoint_env
    row = _endpoint_session(repos, uuid4(), result)
    response = TestClient(app).post(f"/api/sessions/{row.id}/coach-note")
    assert response.status_code == 404
    assert response.json()["error_code"] == "session_not_found"
    post.assert_not_called()


def test_endpoint_invalid_uuid(endpoint_env):
    _, _, post = endpoint_env
    response = TestClient(app).post("/api/sessions/not-a-uuid/coach-note")
    assert response.status_code == 404
    assert response.json()["error_code"] == "session_not_found"
    post.assert_not_called()


@pytest.fixture
def insufficient_result():
    return {"status": "insufficient_audio", "reason": "low_voiced_ratio",
            "audio": {"duration_s": 12.34, "voiced_ratio": 0.12}, "flags": [],
            "transcript": "secret transcript", "script": "secret script",
            "user_id": "secret user", "session_id": "secret session",
            "email": "secret@example.com", "name": "secret name"}


def test_insufficient_payload_is_minimal(insufficient_result):
    import json

    payload = coach.build_insufficient_payload(insufficient_result)
    assert set(payload) == {"status", "reason", "duration_s", "voiced_pct",
                            "min_voiced_pct", "flags"}
    assert payload["duration_s"] == 12.3
    assert payload["voiced_pct"] == 12 and payload["min_voiced_pct"] == 30
    assert all(value not in json.dumps(payload) for value in (
        "secret transcript", "secret script", "secret user", "secret session",
        "secret@example.com", "secret name"))
    assert coach.allowed_numbers(payload) == {Decimal("12.3"), Decimal("12"), Decimal("30")}
    assert coach.build_insufficient_payload({})["duration_s"] is None
    assert coach.build_insufficient_payload({})["voiced_pct"] is None


@pytest.mark.parametrize("ratio, expected",
                         [(0.29, 29), (0.57, 57), (0.299, 29), (0.12, 12), (None, None)])
def test_insufficient_payload_voiced_pct(insufficient_result, ratio, expected):
    insufficient_result["audio"]["voiced_ratio"] = ratio
    payload = coach.build_insufficient_payload(insufficient_result)
    assert payload["voiced_pct"] == expected
    assert payload["min_voiced_pct"] == 30


def test_endpoint_insufficient_audio(endpoint_env, insufficient_result):
    import json

    repos, user_id, post = endpoint_env
    post.return_value = _cerebras_ok(json.dumps(note("Please record again.")))
    row = _endpoint_session(repos, user_id, insufficient_result, status="insufficient_audio")
    client = TestClient(app)
    responses = [client.post(f"/api/sessions/{row.id}/coach-note") for _ in range(2)]
    assert all(response.status_code == 200 for response in responses)
    assert {"summary", "next_step", "source"} <= responses[0].json().keys()
    assert responses[0].json()["source"] == "cerebras"
    assert responses[1].json() == responses[0].json()
    post.assert_called_once()
    messages = post.call_args.kwargs["json"]["messages"]
    assert messages[0]["content"] == coach._SYSTEM_INSUFFICIENT != coach._SYSTEM
    assert messages[1]["content"] == coach._data(
        coach.build_insufficient_payload(insufficient_result))


@pytest.mark.parametrize("bad", [note("Your score is available."), note("Result 8/100"),
                                note("Try 45 times."), {**note("Try again."), "next_step": "  "}])
def test_insufficient_invalid_output_falls_back(insufficient_result, bad):
    output = coach.generate_coach_note(insufficient_result, None, cerebras=lambda *a, **kw: bad)
    assert output["source"] == "rule"


@pytest.mark.parametrize("summary", ["Your grades are available.", "Ratings are available.",
                                     "You ranked highly."])
def test_insufficient_banned_word_falls_back(insufficient_result, summary):
    output = coach.generate_coach_note(
        insufficient_result, None, cerebras=lambda *a, **kw: note(summary))
    assert output["source"] == "rule"


@pytest.mark.parametrize("reason", ["low_voiced_ratio", "empty_transcript", "unknown"])
def test_insufficient_rule_validates(insufficient_result, reason):
    insufficient_result["reason"] = reason
    payload = coach.build_insufficient_payload(insufficient_result)
    value = coach.rule_based_insufficient_note(payload)
    moderator = Mock(check_text=Mock(return_value=SimpleNamespace(allowed=True)))
    assert value["strengths"] == []
    banned = coach.CONSTANTS["coach"]["insufficient_banned_words"]
    assert coach.validate_output(value, payload, coach.CONSTANTS["coach"]["max_output_chars"],
                                 moderator, banned_words=banned, require_next_step=True) == value


def test_endpoint_unsupported_status(endpoint_env, insufficient_result, monkeypatch):
    repos, user_id, post = endpoint_env
    row = _endpoint_session(repos, user_id, insufficient_result)
    monkeypatch.setattr(repos.sessions, "get_session",
                        lambda *args: SimpleNamespace(status="processing"))
    response = TestClient(app).post(f"/api/sessions/{row.id}/coach-note")
    assert response.status_code == 409
    assert response.json()["error_code"] == "coach_note_unavailable"
    post.assert_not_called()


def test_min_voiced_ratio():
    assert coach.MIN_VOICED_RATIO == 0.30


def test_endpoint_storage_error(endpoint_env, monkeypatch):
    from uuid import uuid4

    from src.app.db.models import StorageError

    repos, _, post = endpoint_env
    def fail(*args):
        raise StorageError("unavailable")

    monkeypatch.setattr(repos.sessions, "get_session", fail)
    response = TestClient(app).post(f"/api/sessions/{uuid4()}/coach-note")
    assert response.status_code == 503
    assert response.json()["error_code"] == "session_storage_unavailable"
    post.assert_not_called()


def test_endpoint_cerebras_failure_uses_rule(endpoint_env, result):
    repos, user_id, post = endpoint_env
    row = _endpoint_session(repos, user_id, result)
    response = TestClient(app).post(f"/api/sessions/{row.id}/coach-note")
    assert response.status_code == 200
    assert response.json()["source"] == "rule"
    post.assert_called_once()


def _payload(**components):
    return {"components": components, "warnings": []}


def test_rule_note_has_no_focus_when_every_part_is_good():
    good = coach.CONSTANTS["web"]["part_good_min"]
    note = coach.rule_based_note(_payload(accuracy=good, fluency=good + 5))
    assert note["focus"] == []
    assert note["summary"] == "Every scored part is in good shape."


def test_rule_note_focuses_on_the_lowest_part_below_good():
    good = coach.CONSTANTS["web"]["part_good_min"]
    note = coach.rule_based_note(_payload(accuracy=good - 20, fluency=good - 5, semantic=good + 5))
    assert note["focus"] == ["Practise Accuracy."]
    assert note["strengths"] == ["Meaning match"]


def test_prompt_states_the_output_limits():
    assert str(coach.CONSTANTS["coach"]["max_output_chars"]) in coach._SYSTEM


def _cerebras_ok(content="{}"):
    return SimpleNamespace(ok=True, status_code=200,
                           json=lambda: {"choices": [{"message": {"content": content}}]})


def _cerebras_settings(keys=None, fallback=""):
    return SimpleNamespace(cerebras_api_keys=keys if keys is not None else ["retry-key"],
                           cerebras_model="model", cerebras_fallback_model_1=fallback)


def test_cerebras_model_fallback_on_bad_response(monkeypatch):
    post = Mock(side_effect=[SimpleNamespace(ok=False, status_code=400), _cerebras_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_cerebras({}, _cerebras_settings(fallback="backup"), 1) == {}
    assert [c.kwargs["json"]["model"] for c in post.call_args_list] == ["model", "backup"]


def test_cerebras_retries_once_when_overloaded(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(coach.time, "sleep", sleep)
    post = Mock(side_effect=[SimpleNamespace(ok=False, status_code=503), _cerebras_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_cerebras({}, _cerebras_settings(), 1) == {}
    sleep.assert_called_once_with(coach.CONSTANTS["coach"]["retry_backoff_s"])


def test_cerebras_gives_up_after_retry_per_model(monkeypatch):
    monkeypatch.setattr(coach.time, "sleep", Mock())
    post = Mock(return_value=SimpleNamespace(ok=False, status_code=503))
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_cerebras({}, _cerebras_settings(fallback="backup"), 1) is None
    assert [c.kwargs["json"]["model"] for c in post.call_args_list] == [
        "model", "model", "backup", "backup"
    ]


def test_cerebras_retries_after_timeout(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(coach.time, "sleep", sleep)
    post = Mock(side_effect=[coach.requests.Timeout("slow"), _cerebras_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_cerebras({}, _cerebras_settings(), 1) == {}
    sleep.assert_called_once_with(coach.CONSTANTS["coach"]["retry_backoff_s"])


def test_cerebras_invalid_json_tries_fallback(monkeypatch):
    post = Mock(side_effect=[_cerebras_ok("bad json"), _cerebras_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_cerebras({}, _cerebras_settings(fallback="backup"), 1) == {}
    assert post.call_args.kwargs["json"]["model"] == "backup"


def test_cerebras_falls_back_when_all_model_keys_are_exhausted(monkeypatch):
    keys = ["exhausted-fallback-key-one", "exhausted-fallback-key-two"]
    post = Mock(side_effect=[
        SimpleNamespace(ok=False, status_code=429),
        SimpleNamespace(ok=False, status_code=429),
        _cerebras_ok(),
    ])
    monkeypatch.setattr(coach.requests, "post", post)
    settings = _cerebras_settings(keys=keys, fallback="backup")
    assert coach.call_cerebras({}, settings, 1) == {}
    assert [c.kwargs["json"]["model"] for c in post.call_args_list] == [
        "model", "model", "backup"
    ]
    pool = coach.get_pool("cerebras", keys)
    with pytest.raises(coach.KeysExhaustedError):
        pool.current(scope="model")


def test_cerebras_duplicate_fallback_model_is_called_once(monkeypatch):
    post = Mock(return_value=SimpleNamespace(ok=False, status_code=400))
    monkeypatch.setattr(coach.requests, "post", post)
    settings = _cerebras_settings(keys=["duplicate-model-test-key"], fallback="model")
    assert coach.call_cerebras({}, settings, 1) is None
    post.assert_called_once()


@pytest.mark.parametrize(
    "value, limit, options, allowed, expected",
    [
        (None, 900, {}, True, "no_response"),
        ({}, 900, {}, True, "schema"),
        ({**note("Fine"), "focus": ["a", "b"]}, 900, {"max_focus": 1}, True,
         "too_many_focus"),
        (note("scored"), 900, {"banned_words": ("scored",)}, True, "banned_word"),
        (note("Fine"), 1, {}, True, "too_long"),
        (note("999"), 900, {}, True, "stray_number"),
        (note("Fine"), 900, {}, False, "moderation"),
        (note("Fine"), 900, {}, True, None),
    ],
)
def test_validation_failure_codes(value, limit, options, allowed, expected):
    moderator = Mock(check_text=Mock(return_value=SimpleNamespace(allowed=allowed)))
    assert coach.validation_failure(value, {}, limit, moderator, **options) == expected


def test_insufficient_prompt_requires_checked_and_no_guessing():
    assert "checked" in coach._SYSTEM_INSUFFICIENT
    assert "do not guess" in coach._SYSTEM_INSUFFICIENT


def test_insufficient_banned_word_logs_reason(insufficient_result, caplog):
    with caplog.at_level("WARNING", logger="src.audio_processing.coach_note"):
        output = coach.generate_coach_note(
            insufficient_result, None, cerebras=lambda *a, **kw: note("It was scored."))
    assert output["source"] == "rule"
    assert [record.getMessage() for record in caplog.records] == [
        "coach_note fallback: status=insufficient_audio reason=banned_word"]


@pytest.mark.parametrize("insufficient", [False, True])
def test_exception_logs_reason(result, insufficient_result, caplog, insufficient):
    def fail(*args, **kwargs):
        raise RuntimeError("private details")

    with caplog.at_level("WARNING", logger="src.audio_processing.coach_note"):
        output = coach.generate_coach_note(
            insufficient_result if insufficient else result, None, cerebras=fail)
    assert output["source"] == "rule"
    status = "insufficient_audio" if insufficient else "ok"
    assert [record.getMessage() for record in caplog.records] == [
        f"coach_note fallback: status={status} reason=exception"]


@pytest.mark.parametrize("insufficient", [False, True])
def test_accepted_output_does_not_log_warning(result, insufficient_result, caplog, insufficient):
    with caplog.at_level("WARNING", logger="src.audio_processing.coach_note"):
        output = coach.generate_coach_note(
            insufficient_result if insufficient else result, None,
            cerebras=lambda *a, **kw: note("Please practise."))
    assert output["source"] == "cerebras"
    assert not caplog.records
