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
    r = TestClient(main.app).post(
        "/api/baseline", files={"audio": ("b.webm", b"x", "audio/webm")}
    )
    assert r.status_code == 422
    assert seen["loop"] is False
