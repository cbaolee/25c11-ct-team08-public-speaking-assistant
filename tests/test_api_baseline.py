"""Tests for POST/GET /api/baseline with the in-memory repositories.

analyze_baseline and encode_opus are monkeypatched: no FFmpeg, no real audio.
Numbers in profiles are picked by hand for the tests (not measurements).
"""

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.app.main as main
import src.app.routes.baselines as baselines
from src.app.config import settings
from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.models import StorageError
from src.app.deps import CurrentUser, get_current_user
from src.audio_processing.contracts import BaselineProfile, InsufficientAudio

KEYS = {"schema_version", "status", "reason", "profile", "flags"}
USER_A = uuid4()
USER_B = uuid4()


def _profile(threshold: float = 1.0) -> BaselineProfile:
    return BaselineProfile(
        median_pause_s=0.5, hesitation_threshold_s=threshold, median_f0_hz=120.0,
        mean_loudness_db=65.0, flags=[],
    )


def _ok_payload(profile: BaselineProfile) -> dict:
    return {"schema_version": "2.0", "status": "ok", "reason": None,
            "profile": asdict(profile), "flags": list(profile.flags)}


def _fake_encode(src: Path, out: Path, timeout_s: float = 0) -> None:
    out.write_bytes(b"opus")


@pytest.fixture
def current():
    return {"id": USER_A}  # tests switch user by setting current["id"]


@pytest.fixture
def repos(monkeypatch, current):
    repos = build_memory_repos()
    main.app.dependency_overrides[get_repos] = lambda: repos
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=current["id"])
    monkeypatch.setattr(baselines, "encode_opus", _fake_encode)
    yield repos
    main.app.dependency_overrides.clear()


def _post(monkeypatch, fake):
    monkeypatch.setattr(baselines, "analyze_baseline", fake)
    return TestClient(main.app).post(
        "/api/baseline", files={"audio": ("b.wav", b"x", "audio/wav")}
    )


def _get():
    return TestClient(main.app).get("/api/baseline")


def test_create_baseline_ok_shape(monkeypatch, repos):
    r = _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile()))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == KEYS
    assert body["status"] == "ok"
    assert body["profile"]["mean_loudness_db"] == 65.0


def test_create_baseline_ok_saves_current(monkeypatch, repos):
    _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile()))
    body = _get().json()
    assert body["hesitation_threshold_s"] == 1.0
    assert body["is_current"] is True
    assert "user_id" not in body
    assert body["audio_path"] == f"{USER_A}/{body['id']}.webm"
    assert repos.files.download_file(USER_A, settings.baselines_bucket, body["audio_path"])


def test_create_baseline_insufficient_saves_nothing(monkeypatch, repos):
    def fake(audio_path, *, vad_params):
        return {"schema_version": "2.0", "status": "insufficient_audio",
                "reason": "low_voiced_ratio", "profile": None, "flags": []}

    r = _post(monkeypatch, fake)
    assert set(r.json()) == KEYS
    assert r.json()["profile"] is None
    assert _get().json() is None


def test_create_baseline_insufficient_exception_saves_nothing(monkeypatch, repos):
    def fake(audio_path, *, vad_params):
        raise InsufficientAudio()

    r = _post(monkeypatch, fake)
    assert set(r.json()) == KEYS
    assert r.json()["profile"] is None
    assert _get().json() is None


def test_create_baseline_replaces_old_and_deletes_old_audio(monkeypatch, repos):
    _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile(0.8)))
    old = _get().json()
    _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile(1.1)))
    new = _get().json()
    assert new["id"] != old["id"]
    assert new["hesitation_threshold_s"] == 1.1
    with pytest.raises(StorageError):
        repos.files.download_file(USER_A, settings.baselines_bucket, old["audio_path"])
    assert repos.files.download_file(USER_A, settings.baselines_bucket, new["audio_path"])


def test_create_baseline_storage_error_returns_503(monkeypatch, repos):
    def broken(*args, **kwargs):
        raise StorageError("down")

    uploaded: list[str] = []
    real_upload = repos.files.upload_file

    def recording_upload(user_id, bucket, path, *args, **kwargs):
        uploaded.append(path)
        real_upload(user_id, bucket, path, *args, **kwargs)

    monkeypatch.setattr(repos.files, "upload_file", recording_upload)
    monkeypatch.setattr(repos.baselines, "replace_current_baseline", broken)
    r = _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile()))
    assert r.status_code == 503
    assert r.json()["error_code"] == "baseline_not_saved"
    assert len(uploaded) == 1
    with pytest.raises(StorageError):  # the uploaded audio was removed again
        repos.files.download_file(USER_A, settings.baselines_bucket, uploaded[0])


def test_get_baseline_none_returns_null(repos):
    r = _get()
    assert r.status_code == 200
    assert r.json() is None


def test_get_baseline_other_user_returns_null(monkeypatch, repos, current):
    _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile()))
    current["id"] = USER_B
    assert _get().json() is None
