from dataclasses import asdict

from fastapi.testclient import TestClient

import src.app.main as main
from src.audio_processing.contracts import BaselineProfile, InsufficientAudio

KEYS = {"schema_version", "status", "reason", "profile", "flags"}


def _post(monkeypatch, fake):
    monkeypatch.setattr(main, "analyze_baseline", fake)
    client = TestClient(main.app)
    return client.post("/api/baseline", files={"audio": ("b.wav", b"x", "audio/wav")})


def test_baseline_ok_shape(monkeypatch):
    profile = BaselineProfile(
        median_pause_s=0.5, hesitation_threshold_s=1.0, median_f0_hz=120.0,
        mean_loudness_db=65.0, flags=[],
    )

    def fake(audio_path, *, vad_params):
        return {"schema_version": "2.0", "status": "ok", "reason": None,
                "profile": asdict(profile), "flags": []}

    r = _post(monkeypatch, fake)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == KEYS
    assert body["status"] == "ok"
    assert body["profile"]["mean_loudness_db"] == 65.0


def test_baseline_insufficient_same_keys(monkeypatch):
    def fake(audio_path, *, vad_params):
        return {"schema_version": "2.0", "status": "insufficient_audio",
                "reason": "low_voiced_ratio", "profile": None, "flags": []}

    r = _post(monkeypatch, fake)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == KEYS
    assert body["profile"] is None
    assert body["reason"] == "low_voiced_ratio"


def test_baseline_insufficient_exception_path(monkeypatch):
    def fake(audio_path, *, vad_params):
        raise InsufficientAudio()

    r = _post(monkeypatch, fake)
    assert set(r.json()) == KEYS
    assert r.json()["profile"] is None
