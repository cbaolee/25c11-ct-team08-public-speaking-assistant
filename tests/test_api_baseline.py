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
from src.app.db.models import NewBaseline, StorageError
from src.app.deps import CurrentUser, get_current_user
from src.audio_processing.contracts import BaselineProfile, InsufficientAudio

KEYS = {"schema_version", "status", "reason", "profile", "flags"}
USER_A = uuid4()
USER_B = uuid4()


def _profile(threshold: float = 1.0) -> BaselineProfile:
    return BaselineProfile(
        median_pause_s=0.5,
        hesitation_threshold_s=threshold,
        median_f0_hz=120.0,
        mean_loudness_db=65.0,
        flags=[],
    )


def _ok_payload(profile: BaselineProfile) -> dict:
    return {
        "schema_version": "2.0",
        "status": "ok",
        "reason": None,
        "profile": asdict(profile),
        "flags": list(profile.flags),
    }


def _fake_encode(src: Path, out: Path, timeout_s: float = 0) -> None:
    assert src != out  # FFmpeg refuses to overwrite its own input
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


def _post(monkeypatch, fake, filename: str = "b.wav", mime: str = "audio/wav"):
    monkeypatch.setattr(baselines, "analyze_baseline", fake)
    return TestClient(main.app).post("/api/baseline", files={"audio": (filename, b"x", mime)})


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
    assert "audio_path" not in body  # internal bucket path stays on the server
    row = repos.baselines.get_current_baseline(USER_A)
    assert row.audio_path == f"{USER_A}/{body['id']}.webm"
    assert repos.files.download_file(USER_A, settings.baselines_bucket, row.audio_path)


def test_create_baseline_webm_upload_from_ui_is_saved(monkeypatch, repos):
    # the UI (modals/baseline_gate.js) sends the recording as "baseline.webm"
    r = _post(
        monkeypatch,
        lambda audio_path, *, vad_params: _ok_payload(_profile()),
        filename="baseline.webm",
        mime="audio/webm",
    )
    assert r.status_code == 200
    assert _get().json()["is_current"] is True


def test_create_baseline_insufficient_saves_nothing(monkeypatch, repos):
    def fake(audio_path, *, vad_params):
        return {
            "schema_version": "2.0",
            "status": "insufficient_audio",
            "reason": "low_voiced_ratio",
            "profile": None,
            "flags": [],
        }

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
    old = repos.baselines.get_current_baseline(USER_A)
    _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile(1.1)))
    new = repos.baselines.get_current_baseline(USER_A)
    assert new.id != old.id
    assert _get().json()["hesitation_threshold_s"] == 1.1
    with pytest.raises(StorageError):
        repos.files.download_file(USER_A, settings.baselines_bucket, old.audio_path)
    assert repos.files.download_file(USER_A, settings.baselines_bucket, new.audio_path)


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


def test_get_baseline_storage_error_returns_503(monkeypatch, repos):
    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.baselines, "get_current_baseline", broken)
    r = _get()
    assert r.status_code == 503
    assert r.json()["error_code"] == "baseline_unavailable"


def _get_audio():
    return TestClient(main.app).get("/api/baseline/audio")


def _save(monkeypatch):
    _post(monkeypatch, lambda audio_path, *, vad_params: _ok_payload(_profile()))


def test_baseline_audio_ok(monkeypatch, repos):
    _save(monkeypatch)
    r = _get_audio()
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"url", "expires_in"}
    assert body["expires_in"] == settings.signed_url_ttl_s
    assert body["url"]
    assert r.headers["cache-control"] == "no-store"


def test_baseline_audio_none_returns_404(repos):
    r = _get_audio()
    assert r.status_code == 404
    assert r.json()["error_code"] == "baseline_not_found"


def test_baseline_audio_only_own_user(monkeypatch, repos, current):
    _save(monkeypatch)  # A has a baseline
    current["id"] = USER_B
    assert _get_audio().status_code == 404  # B must not reach A's file
    _save(monkeypatch)  # B saves its own
    row_b = repos.baselines.get_current_baseline(USER_B)
    url = _get_audio().json()["url"]
    assert str(USER_B) in url and str(row_b.id) in url
    assert str(USER_A) not in url


def test_baseline_audio_signing_storage_error_returns_503(monkeypatch, repos):
    _save(monkeypatch)

    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.files, "create_signed_url", broken)
    r = _get_audio()
    assert r.status_code == 503
    assert r.json()["error_code"] == "baseline_audio_unavailable"


def test_baseline_audio_lookup_storage_error_returns_503(monkeypatch, repos):
    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.baselines, "get_current_baseline", broken)
    r = _get_audio()
    assert r.status_code == 503
    assert r.json()["error_code"] == "baseline_audio_unavailable"


def test_baseline_audio_response_has_no_internal_keys(monkeypatch, repos):
    _save(monkeypatch)
    body = _get_audio().json()
    assert "audio_path" not in body and "user_id" not in body


def test_baseline_audio_row_without_audio_path_returns_404(repos):
    repos.baselines.replace_current_baseline(
        USER_A, NewBaseline(id=uuid4(), hesitation_threshold_s=1.0, audio_path=None)
    )
    assert repos.baselines.get_current_baseline(USER_A) is not None
    r = _get_audio()
    assert r.status_code == 404
    assert r.json()["error_code"] == "baseline_not_found"
