"""The heavy audio pipelines must not run on the event loop (they would block every request)."""

import asyncio

from fastapi.testclient import TestClient

from src.app import main
from src.app.routes import baselines
from src.audio_processing.contracts import AudioRejected


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def test_evaluate_session_runs_in_worker_thread(monkeypatch):
    seen: dict[str, bool] = {}

    def fake_evaluate(audio_path, script, baseline, *, vad_params):
        seen["loop"] = _on_event_loop()
        raise AudioRejected("corrupt", "stop here")

    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main, "evaluate_session", fake_evaluate)
    r = TestClient(main.app).post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"RIFF", "audio/wav")},
        data={"script": "Hello."},
    )
    assert r.status_code == 422
    assert seen["loop"] is False


def test_analyze_baseline_runs_in_worker_thread(monkeypatch):
    seen: dict[str, bool] = {}

    def fake_analyze(audio_path, *, vad_params):
        seen["loop"] = _on_event_loop()
        raise AudioRejected("corrupt", "stop here")

    monkeypatch.setattr(baselines, "analyze_baseline", fake_analyze)
    r = TestClient(main.app).post("/api/baseline", files={"audio": ("b.webm", b"x", "audio/webm")})
    assert r.status_code == 422
    assert seen["loop"] is False


def _record_upload_thread(module, monkeypatch) -> dict[str, bool]:
    seen: dict[str, bool] = {}
    real_save = module.save_upload_limited

    def recording_save(*args, **kwargs):
        seen["loop"] = _on_event_loop()
        return real_save(*args, **kwargs)

    monkeypatch.setattr(module, "save_upload_limited", recording_save)
    return seen


def test_evaluate_upload_copy_runs_in_worker_thread(monkeypatch):
    seen = _record_upload_thread(main, monkeypatch)

    def fake_evaluate(audio_path, script, baseline, *, vad_params):
        raise AudioRejected("corrupt", "stop here")

    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main, "evaluate_session", fake_evaluate)
    TestClient(main.app).post(
        "/api/evaluate", files={"audio": ("a.wav", b"RIFF", "audio/wav")}, data={"script": "Hi."}
    )
    assert seen["loop"] is False


def test_baseline_upload_copy_runs_in_worker_thread(monkeypatch):
    seen = _record_upload_thread(baselines, monkeypatch)

    def fake_analyze(audio_path, *, vad_params):
        raise AudioRejected("corrupt", "stop here")

    monkeypatch.setattr(baselines, "analyze_baseline", fake_analyze)
    TestClient(main.app).post("/api/baseline", files={"audio": ("b.webm", b"x", "audio/webm")})
    assert seen["loop"] is False
