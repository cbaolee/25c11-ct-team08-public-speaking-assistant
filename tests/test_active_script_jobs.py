"""ScriptGenerationPipeline.has_active_job (ADR-015, issue #121). Offline, fake clock."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.app.constants import CONSTANTS
from src.text_processing import pipeline as pipeline_module
from src.text_processing.contracts import ScriptJobState
from src.text_processing.pipeline import ScriptGenerationPipeline
from src.text_processing.template_store import TemplateStore

USER = "user-a"
OTHER = "user-b"


@pytest.fixture()
def clock(monkeypatch) -> list[float]:
    """The pipeline's monotonic time, in seconds; jobs expire 300 s after creation."""
    now = [1000.0]
    fake_time = SimpleNamespace(monotonic=lambda: now[0])
    monkeypatch.setattr(pipeline_module, "time", fake_time)
    monkeypatch.setitem(CONSTANTS["script_limits"], "active_job_stale_s", 300)
    return now


@pytest.fixture()
def pipeline(clock) -> ScriptGenerationPipeline:
    return ScriptGenerationPipeline(
        template_store=TemplateStore(Path("nonexistent_dir_for_fast_test")),
        moderator=MagicMock(),
        template_engine=MagicMock(),
        llm_generator=MagicMock(),
    )


@pytest.mark.parametrize("status", ["queued", "extracting", "moderating", "generating"])
def test_has_active_job_for_unfinished_statuses(pipeline, status):
    pipeline.create_job(user_id=USER).status = status
    assert pipeline.has_active_job(USER) is True
    assert pipeline.has_active_job(OTHER) is False


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_has_active_job_ignores_finished_jobs(pipeline, status):
    job = pipeline.create_job(user_id=USER)
    assert pipeline.has_active_job(USER) is True
    job.status = status
    assert pipeline.has_active_job(USER) is False
    assert pipeline._active_since == {}


def test_has_active_job_expires_a_job_counted_from_its_creation(pipeline, clock):
    pipeline.create_job(user_id=USER)  # created at 1000
    assert pipeline.has_active_job(USER, now=1200) is True
    assert pipeline.has_active_job(USER, now=1299.9) is True
    assert pipeline.has_active_job(USER, now=1300) is False


def test_has_active_job_expires_an_old_job_on_its_first_check(pipeline, clock):
    pipeline.create_job(user_id=USER)
    clock[0] = 1300  # nothing asked about the job until now
    assert pipeline.has_active_job(USER) is False


def test_has_active_job_keeps_creation_times_across_calls(pipeline, clock):
    first = pipeline.create_job(user_id=USER)
    clock[0] = 1100
    second = pipeline.create_job(user_id=OTHER)
    pipeline.has_active_job(OTHER, now=1150)
    pipeline.has_active_job(USER, now=1200)
    assert pipeline._active_since == {first.job_id: 1000, second.job_id: 1100}


def test_has_active_job_times_a_job_without_creation_time_from_the_first_check(pipeline):
    pipeline._jobs["manual"] = ScriptJobState(job_id="manual", user_id=USER)
    assert pipeline.has_active_job(USER, now=5000) is True
    assert pipeline.has_active_job(USER, now=5299.9) is True
    assert pipeline.has_active_job(USER, now=5300) is False


def test_has_active_job_counts_a_newer_job_and_forgets_removed_ones(pipeline, clock):
    stuck = pipeline.create_job(user_id=USER)
    clock[0] = 1400
    pipeline.create_job(user_id=USER)
    assert pipeline.has_active_job(USER) is True
    del pipeline._jobs[stuck.job_id]
    pipeline.has_active_job(USER)
    assert stuck.job_id not in pipeline._active_since
