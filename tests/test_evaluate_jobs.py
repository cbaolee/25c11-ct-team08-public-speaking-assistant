from pathlib import Path

import pytest

from src.app.evaluate_jobs import EvaluateJobStore, RateLimited, load_weights, run_evaluate_job
from src.audio_processing.contracts import AudioRejected, SttUnavailable


def test_job_progress_and_cleanup(tmp_path: Path):
    store = EvaluateJobStore()
    workdir = tmp_path / "job"
    workdir.mkdir()
    job = store.create_job("user", workdir)
    progress = []

    def evaluate(*, on_stage, should_cancel):
        for key in ("decode", "vad", "stt", "align", "fluency", "pitch", "semantic"):
            assert not should_cancel()
            on_stage(key)
            progress.append(store.get(job.job_id, "user")["progress"])
        return {"status": "ok"}

    run_evaluate_job(store, job, evaluate, lambda result: result)
    state = store.get(job.job_id, "user")
    assert state["status"] == "done"
    assert all(s["state"] == "done" for s in state["stages"])
    assert progress == sorted(progress)
    assert state["progress"] == 100
    assert not workdir.exists()


def test_cancel_limit_and_ttl(tmp_path: Path):
    now = [0.0]
    store = EvaluateJobStore(clock=lambda: now[0], ttl=10, limit=1)
    job = store.create_job("user", tmp_path / "job")
    with pytest.raises(RateLimited):
        store.create_job("user", tmp_path / "other")
    assert store.get(job.job_id, "other") is None
    store.cancel(job.job_id, "user")
    run_evaluate_job(
        store, job, lambda **kw: kw["on_stage"]("decode"), lambda _: pytest.fail("saved")
    )
    assert store.get(job.job_id, "user")["status"] == "cancelled"
    now[0] = 10
    assert store.get(job.job_id, "user") is None


def test_invalid_weights():
    with pytest.raises(ValueError):
        load_weights({"stage_weights": {"upload": 1}})


@pytest.mark.parametrize(
    "last,skipped",
    [
        ("vad", ["stt", "align", "fluency", "pitch", "semantic"]),
        ("stt", ["align", "fluency", "pitch", "semantic"]),
    ],
)
def test_insufficient_still_saves(tmp_path, last, skipped):
    store = EvaluateJobStore()
    workdir = tmp_path / "job"
    workdir.mkdir()
    job = store.create_job("user", workdir)

    def evaluate(*, on_stage, should_cancel):
        for key in ("decode", "vad", "stt"):
            on_stage(key)
            if key == last:
                break
        return {"status": "insufficient_audio"}

    run_evaluate_job(store, job, evaluate, lambda result: result)
    state = store.get(job.job_id, "user")
    stages = {s["key"]: s["state"] for s in state["stages"]}
    assert all(stages[key] == "skipped" for key in skipped)
    assert stages["save"] == "done"
    assert state["result"]["status"] == "insufficient_audio"
    assert state["progress"] == 100
    assert not workdir.exists()


def test_cancel_before_save(tmp_path):
    store = EvaluateJobStore()
    workdir = tmp_path / "job"
    workdir.mkdir()
    job = store.create_job("user", workdir)

    def evaluate(*, on_stage, should_cancel):
        on_stage("vad")
        store.cancel(job.job_id, "user")
        return {}

    run_evaluate_job(store, job, evaluate, lambda _: pytest.fail("saved"))
    assert store.get(job.job_id, "user")["status"] == "cancelled"
    assert not workdir.exists()


@pytest.mark.parametrize(
    "exc,code",
    [
        (AudioRejected("corrupt", "bad"), "corrupt"),
        (SttUnavailable("down"), "stt_unavailable"),
        (RuntimeError("private"), "evaluation_failed"),
    ],
)
def test_failure_removes_workdir(tmp_path, exc, code):
    store = EvaluateJobStore()
    workdir = tmp_path / "job"
    workdir.mkdir()
    job = store.create_job("user", workdir)

    def evaluate(**kwargs):
        kwargs["on_stage"]("vad")
        raise exc

    run_evaluate_job(store, job, evaluate, lambda _: pytest.fail("saved"))
    state = store.get(job.job_id, "user")
    assert state["status"] == "failed"
    assert state["error_code"] == code
    assert next(s for s in state["stages"] if s["key"] == "vad")["state"] == "pending"
    assert not workdir.exists()


def test_save_started_cannot_be_cancelled(tmp_path):
    store = EvaluateJobStore()
    job = store.create_job("user", tmp_path / "job")

    def save(result):
        store.cancel(job.job_id, "user")
        return result

    run_evaluate_job(store, job, lambda **kw: {}, save)
    assert store.cancel(job.job_id, "user")["status"] == "done"


def test_api_visibility_limit_and_config(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from src.app import main
    from tests.conftest import TEST_USER_ID

    store = EvaluateJobStore(limit=1)
    monkeypatch.setattr(main, "_evaluate_jobs", store)
    job = store.create_job(str(TEST_USER_ID), tmp_path / "job")
    client = TestClient(main.app)
    assert client.get("/api/evaluate/missing").status_code == 404
    assert client.delete("/api/evaluate/missing").status_code == 404
    other = store.create_job("another-user", tmp_path / "other")
    assert client.get(f"/api/evaluate/{other.job_id}").status_code == 404
    assert client.delete(f"/api/evaluate/{other.job_id}").status_code == 404
    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main.tempfile, "mkdtemp", lambda: pytest.fail("workdir created"))
    monkeypatch.setattr(main, "save_upload_limited", lambda *a, **k: pytest.fail("upload saved"))
    response = client.post(
        "/api/evaluate", data={"script": "Hello."}, files={"audio": ("a.wav", b"x")}
    )
    assert response.status_code == 429
    assert response.json()["error_code"] == "rate_limited"
    assert client.get(f"/api/evaluate/{job.job_id}").status_code == 200
    config = client.get("/api/config").json()["evaluate_job"]
    assert sum(config["stage_weights"].values()) == 100


def test_running_job_survives_ttl(tmp_path):
    now = [0.0]
    store = EvaluateJobStore(clock=lambda: now[0], ttl=10)
    job = store.create_job("user", tmp_path / "job")
    store.mark_running(job)
    now[0] = 100
    assert store.get(job.job_id, "user")["status"] == "running"


def test_cancel_between_stages_via_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from src.app import main
    from src.audio_processing.pipeline import EvaluationCancelled
    from tests.conftest import TEST_USER_ID

    store = EvaluateJobStore()
    monkeypatch.setattr(main, "_evaluate_jobs", store)
    monkeypatch.setattr(main, "_save_result_to_history", lambda **kw: pytest.fail("saved"))
    job = store.create_job(str(TEST_USER_ID), tmp_path / "job")
    client = TestClient(main.app)

    def evaluate(*, on_stage, should_cancel):
        on_stage("vad")
        assert client.delete(f"/api/evaluate/{job.job_id}").status_code == 200
        if should_cancel():
            raise EvaluationCancelled()
        pytest.fail("cancellation not observed")

    run_evaluate_job(store, job, evaluate, lambda result: main._save_result_to_history())
    state = client.get(f"/api/evaluate/{job.job_id}").json()
    assert state["status"] == "cancelled"
    assert next(s for s in state["stages"] if s["key"] == "vad")["state"] == "pending"


def test_api_too_large_cleans_workdir(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from src.app import main

    workdir = tmp_path / "upload"
    def make_workdir():
        workdir.mkdir()
        return str(workdir)

    monkeypatch.setattr(main.tempfile, "mkdtemp", make_workdir)
    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main, "max_upload_bytes", 1)
    monkeypatch.setattr(main, "_evaluate_jobs", EvaluateJobStore())
    response = TestClient(main.app).post(
        "/api/evaluate", data={"script": "Hello."}, files={"audio": ("a.wav", b"xx")}
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "too_large"
    assert not workdir.exists()


def test_api_done_progress(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from src.app import main
    from tests.conftest import TEST_USER_ID

    store = EvaluateJobStore()
    monkeypatch.setattr(main, "_evaluate_jobs", store)
    job = store.create_job(str(TEST_USER_ID), tmp_path / "job")
    run_evaluate_job(store, job, lambda **kw: {}, lambda result: result)
    state = TestClient(main.app).get(f"/api/evaluate/{job.job_id}").json()
    assert state["status"] == "done"
    assert state["progress"] == 100
