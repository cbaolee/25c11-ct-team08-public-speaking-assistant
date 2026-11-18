from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.app import coach_note as coach
from src.app.deps import get_current_user
from src.app.main import app


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
    output = coach.generate_coach_note(result, None, gemini=lambda *a: bad, groq=lambda *a: note())
    assert output["source"] == "groq"


def test_moderation_and_rule(result):
    moderator = Mock()
    moderator.check_text.side_effect = [
        SimpleNamespace(allowed=False),
        SimpleNamespace(allowed=True),
    ]
    assert (
        coach.generate_coach_note(
            result, None, moderator=moderator, gemini=lambda *a: note(), groq=lambda *a: None
        )["source"]
        == "rule"
    )


def test_gemini_rotation_and_missing(monkeypatch):
    post = Mock(
        side_effect=[
            SimpleNamespace(ok=False, status_code=429),
            SimpleNamespace(
                ok=True, json=lambda: {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
            ),
        ]
    )
    monkeypatch.setattr(coach.requests, "post", post)
    settings = SimpleNamespace(
        gemini_api_keys=["test-coach-one", "test-coach-two"], gemini_model="model"
    )
    assert coach.call_gemini({}, settings, 1) == {}
    assert post.call_count == 2
    post.reset_mock()
    settings.gemini_model = ""
    assert coach.call_gemini({}, settings, 1) is None
    post.assert_not_called()


def test_cache():
    cache = coach.CoachNoteCache(10, clock=lambda: 0)
    cache.put("a", {"source": "rule"})
    assert cache.get("a") is None
    cache.put("a", {"source": "groq"})
    assert cache.get("a")["source"] == "groq"


def test_cache_put_removes_expired_entries_and_keeps_live_entries():
    now = [0]
    cache = coach.CoachNoteCache(10, clock=lambda: now[0])
    cache.put("expired", {"source": "gemini"})
    now[0] = 5
    cache.put("live", {"source": "groq"})
    now[0] = 10
    cache.put("rule", {"source": "rule"})
    assert "expired" not in cache._entries
    assert cache.get("live")["source"] == "groq"
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
    settings = SimpleNamespace(
        gemini_api_keys=[], gemini_model="", groq_api_keys=["fake"],
        groq_llm_model="fake-model", groq_llm_fallback_model_1="",
        groq_llm_fallback_model_2="",
    )
    monkeypatch.setattr(route, "settings", settings)
    monkeypatch.setattr(route, "cache", coach.CoachNoteCache(3600))
    post = Mock(side_effect=AssertionError("Unexpected Gemini HTTP request"))
    groq_create = Mock(side_effect=RuntimeError("Mock Groq unavailable"))
    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=groq_create)
    ))
    monkeypatch.setattr(coach.requests, "post", post)
    monkeypatch.setattr(coach, "make_groq_client", Mock(return_value=client))
    yield repos, user_id, post, groq_create
    post.assert_not_called()


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

    repos, user_id, post, create = endpoint_env
    create.side_effect = None
    create.return_value = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(note()))
    )])
    row = _endpoint_session(repos, user_id, result)
    client = TestClient(app)
    responses = [client.post(f"/api/sessions/{row.id}/coach-note") for _ in range(2)]
    assert all(response.status_code == 200 for response in responses)
    assert set(responses[0].json()) == {"summary", "strengths", "focus", "next_step", "source"}
    assert responses[0].json()["source"] == "groq"
    assert responses[1].json() == responses[0].json()
    assert create.call_count == 1
    post.assert_not_called()


def test_endpoint_other_user(endpoint_env, result):
    from uuid import uuid4

    repos, _, post, create = endpoint_env
    row = _endpoint_session(repos, uuid4(), result)
    response = TestClient(app).post(f"/api/sessions/{row.id}/coach-note")
    assert response.status_code == 404
    assert response.json()["error_code"] == "session_not_found"
    post.assert_not_called()
    create.assert_not_called()


def test_endpoint_invalid_uuid(endpoint_env):
    _, _, post, create = endpoint_env
    response = TestClient(app).post("/api/sessions/not-a-uuid/coach-note")
    assert response.status_code == 404
    assert response.json()["error_code"] == "session_not_found"
    post.assert_not_called()
    create.assert_not_called()


def test_endpoint_insufficient_audio(endpoint_env, result):
    repos, user_id, post, create = endpoint_env
    row = _endpoint_session(repos, user_id, result, status="insufficient_audio")
    response = TestClient(app).post(f"/api/sessions/{row.id}/coach-note")
    assert response.status_code == 409
    assert response.json()["error_code"] == "insufficient_audio"
    post.assert_not_called()
    create.assert_not_called()


def test_endpoint_storage_error(endpoint_env, monkeypatch):
    from uuid import uuid4

    from src.app.db.models import StorageError

    repos, _, post, create = endpoint_env
    def fail(*args):
        raise StorageError("unavailable")

    monkeypatch.setattr(repos.sessions, "get_session", fail)
    response = TestClient(app).post(f"/api/sessions/{uuid4()}/coach-note")
    assert response.status_code == 503
    assert response.json()["error_code"] == "session_storage_unavailable"
    post.assert_not_called()
    create.assert_not_called()


def test_endpoint_groq_failure_uses_rule(endpoint_env, result):
    repos, user_id, post, create = endpoint_env
    row = _endpoint_session(repos, user_id, result)
    response = TestClient(app).post(f"/api/sessions/{row.id}/coach-note")
    assert response.status_code == 200
    assert response.json()["source"] == "rule"
    create.assert_called_once()
    post.assert_not_called()


def _gemini_ok():
    return SimpleNamespace(
        ok=True, status_code=200,
        json=lambda: {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
    )


def _gemini_settings():
    return SimpleNamespace(gemini_api_keys=["test-retry-key"], gemini_model="model")


def test_gemini_retries_once_when_overloaded(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(coach.time, "sleep", sleep)
    post = Mock(side_effect=[SimpleNamespace(ok=False, status_code=503), _gemini_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_gemini({}, _gemini_settings(), 1) == {}
    assert post.call_count == 2
    sleep.assert_called_once_with(coach.CONSTANTS["coach"]["retry_backoff_s"])


def test_gemini_gives_up_after_the_retry(monkeypatch):
    monkeypatch.setattr(coach.time, "sleep", Mock())
    post = Mock(return_value=SimpleNamespace(ok=False, status_code=503))
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_gemini({}, _gemini_settings(), 1) is None
    assert post.call_count == 1 + coach.CONSTANTS["coach"]["retry_unavailable"]


def test_gemini_retries_after_a_timeout(monkeypatch):
    monkeypatch.setattr(coach.time, "sleep", Mock())
    post = Mock(side_effect=[coach.requests.Timeout("slow"), _gemini_ok()])
    monkeypatch.setattr(coach.requests, "post", post)
    assert coach.call_gemini({}, _gemini_settings(), 1) == {}


def test_groq_uses_the_default_chain_when_env_models_are_empty(monkeypatch):
    create = Mock(side_effect=RuntimeError("Mock Groq unavailable"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(coach, "make_groq_client", lambda keys: client)
    settings = SimpleNamespace(groq_api_keys=["fake"], groq_llm_model=" ",
                               groq_llm_fallback_model_1="", groq_llm_fallback_model_2="")
    assert coach.call_groq({}, settings, 1) is None
    tried = [call.kwargs["model"] for call in create.call_args_list]
    assert tried == list(coach._DEFAULT_MODEL_CHAIN)
