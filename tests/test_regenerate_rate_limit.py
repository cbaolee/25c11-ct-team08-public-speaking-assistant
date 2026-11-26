"""Anti-spam limits of POST /api/generate-script (ADR-015, issue #121).

Offline: in-memory counters with a fake clock; script jobs are finished without any LLM call.
"""

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import get_args
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient

from src.app import main as app_main
from src.app.constants import CONSTANTS
from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.memory import MemoryRateLimitRepo, MemoryState
from src.app.db.models import StorageError
from src.app.deps import CurrentUser, get_current_user
from src.app.script_limits import (
    GenerateBlock,
    Reason,
    check_generate_limits,
    rate_limited_response,
    user_rate_key,
    validate_generate_input,
)
from src.text_processing.chat_session import ChatSessionState, ChatSessionStore
from src.text_processing.contracts import ScriptGenerationError, ScriptGenerationRequest
from src.text_processing.pipeline import ScriptGenerationPipeline
from src.text_processing.template_store import TemplateStore

USER = str(uuid5(NAMESPACE_URL, "limit-user-a"))
OTHER = str(uuid5(NAMESPACE_URL, "limit-user-b"))

# Fixed here so the hand-counted numbers below survive tuning app_constants.toml.
LIMITS = {
    "regenerate_cooldown_s": 15,
    "regenerate_long_cooldown_s": 30,
    "regenerate_long_min_duration": 15,
    "regenerate_max_per_window": 5,
    "regenerate_window_s": 600,
    "generate_max_per_window": 10,
    "generate_window_s": 600,
    "active_job_retry_after_s": 5,
    "active_job_stale_s": 300,
}


@pytest.fixture(autouse=True)
def fixed_limits(monkeypatch):
    monkeypatch.setitem(CONSTANTS, "script_limits", dict(LIMITS))


class Counters:
    """In-memory rate limit repo whose clock is `now`, in seconds."""

    def __init__(self) -> None:
        self.now = 0.0
        self.state = MemoryState()
        self.repo = MemoryRateLimitRepo(self.state, clock=lambda: self.now)

    def check(self, at_s: float, *, regen: bool = False, duration: int = 5, user: str = USER):
        self.now = at_s
        return check_generate_limits(
            self.repo, user, is_regenerate=regen, duration_min=duration
        )

    def hits(self, bucket: str, user: str = USER) -> int:
        return self.state.rate_limits.get((bucket, user_rate_key(user)), (0.0, 0))[1]


def test_repo_toml_defines_every_script_limit():
    from src.app.constants import load_constants

    section = load_constants()["script_limits"]
    assert set(section) == set(LIMITS)
    assert all(isinstance(value, int) and value > 0 for value in section.values())


# ---------- check_generate_limits ----------


def test_generate_total_blocks_the_eleventh_request():
    counters = Counters()
    assert [counters.check(t) for t in range(10)] == [None] * 10
    assert counters.check(10) == GenerateBlock("generate_quota", 590)  # 600 - 10


def test_generate_has_no_cooldown():
    counters = Counters()
    assert counters.check(0) is None
    assert counters.check(0) is None
    assert counters.hits("script_regen_cooldown") == 0
    assert counters.hits("script_regen_window") == 0


@pytest.mark.parametrize("duration", [5, 10])
def test_short_speech_uses_the_short_cooldown(duration):
    counters = Counters()
    assert counters.check(0, regen=True, duration=duration) is None
    blocked = counters.check(10, regen=True, duration=duration)
    assert blocked == GenerateBlock("cooldown", 5)
    assert counters.check(15, regen=True, duration=duration) is None


@pytest.mark.parametrize("duration", [15, 20])
def test_long_speech_uses_the_long_cooldown(duration):
    counters = Counters()
    assert counters.check(0, regen=True, duration=duration) is None
    blocked = counters.check(29, regen=True, duration=duration)
    assert blocked == GenerateBlock("cooldown", 1)
    assert counters.check(30, regen=True, duration=duration) is None


def test_one_cooldown_bucket_uses_the_length_of_the_request_being_checked():
    counters = Counters()
    assert counters.check(0, regen=True, duration=20) is None
    assert counters.check(10, regen=True, duration=5) == GenerateBlock("cooldown", 5)


def test_requests_during_the_cooldown_cost_no_quota_and_do_not_extend_it():
    counters = Counters()
    assert counters.check(0, regen=True) is None
    for at_s in range(1, 15):
        assert counters.check(at_s, regen=True) == GenerateBlock("cooldown", 15 - at_s)
    assert counters.hits("script_gen_window") == 1
    assert counters.hits("script_regen_window") == 1
    assert counters.check(15, regen=True) is None


def test_sixth_regenerate_is_refused_until_the_window_ends():
    counters = Counters()
    for at_s in (0, 15, 30, 45, 60):
        assert counters.check(at_s, regen=True) is None
    assert counters.check(75, regen=True) == GenerateBlock("regenerate_quota", 525)
    assert counters.check(600, regen=True) is None


def test_requests_refused_by_the_regenerate_quota_still_use_the_total():
    """Accepted cost of the order cooldown -> total -> Regenerate quota (ADR-015)."""
    counters = Counters()
    assert counters.check(0) is None  # total 1
    for at_s in (20, 35, 50, 65, 80):  # total 2..6, Regenerate 1..5 (window starts at 20)
        assert counters.check(at_s, regen=True) is None
    # total 7, refused by the Regenerate quota: 600 - (95 - 20) = 525
    assert counters.check(95, regen=True) == GenerateBlock("regenerate_quota", 525)
    for at_s in (110, 125, 140):  # total 8, 9, 10
        assert counters.check(at_s, regen=True).reason == "regenerate_quota"
    # total 11: full although only 6 requests passed; 600 - 155 = 445
    assert counters.check(155, regen=True) == GenerateBlock("generate_quota", 445)
    assert counters.check(155) == GenerateBlock("generate_quota", 445)


def test_full_total_does_not_use_the_regenerate_quota():
    counters = Counters()
    for _ in range(10):
        counters.check(0)
    assert counters.check(1, regen=True) == GenerateBlock("generate_quota", 599)
    assert counters.hits("script_regen_window") == 0


def test_users_are_counted_apart():
    counters = Counters()
    for _ in range(10):
        counters.check(0)
    assert counters.check(0).reason == "generate_quota"
    assert counters.check(0, user=OTHER) is None
    assert counters.check(0, regen=True, user=OTHER) is None


def test_limits_are_read_when_checking(monkeypatch):
    monkeypatch.setitem(CONSTANTS["script_limits"], "generate_max_per_window", 1)
    counters = Counters()
    assert counters.check(0) is None
    assert counters.check(0).reason == "generate_quota"


def test_counter_down_lets_the_request_through_and_logs_only_the_bucket(monkeypatch, caplog):
    counters = Counters()

    def down(bucket, key, *_args):
        raise StorageError(f"down for {USER} {key}")

    monkeypatch.setattr(counters.repo, "hit", down)
    assert counters.check(0, regen=True) is None
    for bucket in ("script_regen_cooldown", "script_gen_window", "script_regen_window"):
        assert f"counter unavailable for {bucket}; allowing the request" in caplog.text
    assert USER not in caplog.text
    assert user_rate_key(USER) not in caplog.text


def test_a_failing_layer_does_not_skip_the_later_layers(monkeypatch):
    counters = Counters()
    real_hit = counters.repo.hit

    def cooldown_down(bucket, *args):
        if bucket == "script_regen_cooldown":
            raise StorageError("down")
        return real_hit(bucket, *args)

    for _ in range(10):
        counters.check(0)
    monkeypatch.setattr(counters.repo, "hit", cooldown_down)
    assert counters.check(0, regen=True).reason == "generate_quota"


def test_unreadable_wait_still_blocks_for_the_whole_window(monkeypatch, caplog):
    counters = Counters()
    assert counters.check(0, regen=True) is None

    def down(bucket, key, window_s):
        raise StorageError(f"down for {USER} {key}")

    monkeypatch.setattr(counters.repo, "retry_after_s", down)
    assert counters.check(10, regen=True) == GenerateBlock("cooldown", 15)
    assert "wait time unavailable for script_regen_cooldown" in caplog.text
    assert USER not in caplog.text
    assert user_rate_key(USER) not in caplog.text


def test_buckets_and_keys_fit_the_table_constraints():
    repo = MagicMock()
    repo.hit.return_value = True
    check_generate_limits(repo, USER, is_regenerate=True, duration_min=5)
    check_generate_limits(repo, USER, is_regenerate=False, duration_min=5)
    calls = [call.args for call in repo.hit.call_args_list]
    assert len(calls) == 4
    for bucket, key, _max_hits, _window_s in calls:
        assert re.fullmatch(r"[a-z_]{1,40}", bucket)
        assert re.fullmatch(r"[0-9a-f]{64}", key)


# ---------- validate_generate_input ----------


@pytest.mark.parametrize(
    ("topic", "duration", "feedback", "message"),
    [
        ("", 7, None, "Topic must not be empty."),  # the topic is checked first
        ("   ", 5, None, "Topic must not be empty."),
        ("Reefs", 7, None, "duration"),
        ("Reefs", 5, "one two three four", "feedback is too long"),
    ],
)
def test_validate_generate_input_rejects(monkeypatch, topic, duration, feedback, message):
    monkeypatch.setitem(CONSTANTS["web"], "composer_max_words", 3)
    with pytest.raises(ScriptGenerationError, match=message) as caught:
        validate_generate_input(topic, duration, feedback)
    assert (caught.value.error_code, caught.value.status_code) == ("output_invalid", 422)


@pytest.mark.parametrize("feedback", [None, "one two three"])
def test_validate_generate_input_accepts_up_to_the_word_limit(monkeypatch, feedback):
    monkeypatch.setitem(CONSTANTS["web"], "composer_max_words", 3)
    validate_generate_input("Reefs", 20, feedback)


# ---------- POST /api/generate-script ----------


def _pipeline() -> ScriptGenerationPipeline:
    pipeline = ScriptGenerationPipeline(
        template_store=TemplateStore(Path("nonexistent_dir_for_fast_test")),
        moderator=MagicMock(),
        template_engine=MagicMock(),
        llm_generator=MagicMock(),
    )
    pipeline.session_store = ChatSessionStore()  # an empty store passed in would be replaced
    return pipeline


class Api:
    """TestClient with one shared set of repos, a fake clock and jobs that finish at once."""

    def __init__(self, monkeypatch) -> None:
        self.counters = Counters()
        self.pipeline = _pipeline()
        self.user = CurrentUser(id=uuid5(NAMESPACE_URL, "limit-user-a"))
        self.saved: list[Path] = []
        self.requests: list[ScriptGenerationRequest] = []
        repos = replace(build_memory_repos(), rate_limits=self.counters.repo)
        app_main.app.dependency_overrides[get_repos] = lambda: repos
        app_main.app.dependency_overrides[get_current_user] = lambda: self.user
        monkeypatch.setattr(app_main, "_script_pipeline", self.pipeline)
        monkeypatch.setattr(self.pipeline, "run_job", self._finish_job)
        real_save = app_main.save_upload_limited

        def spy_save(upload, dest, **kwargs):
            self.saved.append(dest)
            return real_save(upload, dest, **kwargs)

        monkeypatch.setattr(app_main, "save_upload_limited", spy_save)
        self.client = TestClient(app_main.app)

    def _finish_job(self, job_id, request, cleanup_pdf=False) -> None:
        self.requests.append(request)
        self.pipeline.get_job(job_id).status = "completed"
        if cleanup_pdf and request.pdf_path:
            Path(request.pdf_path).unlink(missing_ok=True)

    def post(self, at_s: float = 0, *, pdf: bool = False, **form):
        self.counters.now = at_s
        files = {"pdf": ("notes.pdf", b"%PDF-1.4 notes", "application/pdf")} if pdf else None
        return self.client.post(
            "/api/generate-script", data={"topic": "Coral reefs", **form}, files=files
        )


@pytest.fixture()
def api(monkeypatch) -> Api:
    return Api(monkeypatch)


def _assert_blocked(response, reason: str, retry_after_s: int) -> None:
    assert response.status_code == 429
    body = response.json()
    assert set(body) == {"error_code", "message", "retry_after_s", "reason"}
    assert body["error_code"] == "rate_limited"
    assert body["message"]
    assert (body["reason"], body["retry_after_s"]) == (reason, retry_after_s)
    assert response.headers["Retry-After"] == str(body["retry_after_s"])


def test_endpoint_refuses_regenerate_during_the_cooldown(api):
    first = api.post(0, user_feedback="Shorter please")
    assert first.status_code == 202
    assert set(first.json()) == {"job_id", "status"}
    _assert_blocked(api.post(10, user_feedback="Shorter please"), "cooldown", 5)
    assert api.post(15, user_feedback="Shorter please").status_code == 202


@pytest.mark.parametrize(
    ("session_duration", "form_duration"), [(None, 20), (20, 5)]
)
def test_endpoint_long_speech_waits_longer(api, session_duration, form_duration):
    form = {"duration_min": form_duration, "user_feedback": "More examples"}
    if session_duration is not None:  # the session length replaces the form default of 5
        form["session_id"] = "long-speech"
        api.pipeline.session_store.put(
            ChatSessionState(
                session_id="long-speech",
                user_id=str(api.user.id),
                category="free",
                duration_min=session_duration,
            )
        )
    assert api.post(0, **form).status_code == 202
    _assert_blocked(api.post(20, **form), "cooldown", 10)
    assert api.post(30, **form).status_code == 202


def test_endpoint_blank_feedback_is_a_generate_stopped_only_by_the_total(api):
    for _ in range(10):  # no cooldown and no Regenerate quota
        assert api.post(0, user_feedback="   ").status_code == 202
    _assert_blocked(api.post(0, user_feedback="   "), "generate_quota", 600)


def test_endpoint_takes_a_blank_topic_from_the_session(api):
    api.pipeline.session_store.put(
        ChatSessionState(
            session_id="prompt-only",
            user_id=str(api.user.id),
            category="free",
            duration_min=5,
            initial_prompt="Deep sea vents",
        )
    )
    assert api.post(0, topic="", session_id="prompt-only").status_code == 202
    assert [request.topic for request in api.requests] == ["Deep sea vents"]


@pytest.mark.parametrize(
    "form",
    [{"topic": "   "}, {"duration_min": 7}, {"user_feedback": "one two three four"}],
)
def test_endpoint_invalid_input_costs_no_attempt(api, monkeypatch, form):
    monkeypatch.setitem(CONSTANTS["web"], "composer_max_words", 3)
    response = api.post(0, pdf=True, **form)
    assert response.status_code == 422
    assert response.json()["error_code"] == "output_invalid"
    assert api.counters.state.rate_limits == {}
    assert api.saved == []
    assert len(api.pipeline._jobs) == 0


def test_endpoint_new_chats_share_the_total_limit(api):
    for n in range(10):
        assert api.post(0, session_id=f"chat-{n}").status_code == 202
    _assert_blocked(api.post(100, session_id="chat-new"), "generate_quota", 500)


def test_endpoint_refuses_a_second_job_without_counting_it(api):
    job = api.pipeline.create_job(user_id=str(api.user.id))
    _assert_blocked(api.post(0, pdf=True), "job_running", 5)
    assert api.counters.state.rate_limits == {}
    assert api.saved == []

    api.user = CurrentUser(id=uuid5(NAMESPACE_URL, "limit-user-b"))
    assert api.post(0).status_code == 202

    api.user = CurrentUser(id=uuid5(NAMESPACE_URL, "limit-user-a"))
    job.status = "completed"
    assert api.post(0).status_code == 202


def test_endpoint_job_created_during_the_upload_blocks_and_removes_the_file(api, monkeypatch):
    spy_save = app_main.save_upload_limited

    def save_while_other_request_wins(upload, dest, **kwargs):
        written = spy_save(upload, dest, **kwargs)
        assert dest.exists()
        api.pipeline.create_job(user_id=str(api.user.id))
        return written

    monkeypatch.setattr(app_main, "save_upload_limited", save_while_other_request_wins)
    _assert_blocked(api.post(0, pdf=True), "job_running", 5)
    assert len(api.pipeline._jobs) == 1
    assert len(api.saved) == 1
    assert not api.saved[0].exists()
    assert api.counters.hits("script_gen_window") == 1  # already counted: known cost


def test_endpoint_limited_request_does_not_save_the_upload(api):
    assert api.post(0, pdf=True, user_feedback="Shorter").status_code == 202
    assert len(api.saved) == 1
    _assert_blocked(api.post(1, pdf=True, user_feedback="Shorter"), "cooldown", 14)
    assert len(api.saved) == 1


def test_endpoint_lets_requests_through_when_the_counter_is_down(api, monkeypatch):
    def down(*_args):
        raise StorageError("down")

    monkeypatch.setattr(api.counters.repo, "hit", down)
    for _ in range(3):
        assert api.post(0, user_feedback="Shorter").status_code == 202


@pytest.mark.parametrize("reason", get_args(Reason))
def test_every_reason_has_a_message(reason):
    response = rate_limited_response(GenerateBlock(reason, 7))
    body = json.loads(response.body)
    assert body["reason"] == reason
    assert body["message"].strip()
