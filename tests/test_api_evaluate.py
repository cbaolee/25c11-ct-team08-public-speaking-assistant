"""Test POST /api/evaluate: baseline comes from the DB per user, the session is saved.

evaluate_session is monkeypatched: the real Evaluate Pipeline does not run.
All numbers in these tests are chosen by hand (not measured).
"""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.config import settings
from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.models import NewBaseline, StorageError
from src.app.deps import CurrentUser, get_current_user
from src.audio_processing.contracts import BaselineProfile
from src.audio_processing.result_schema import EvaluationResultV2

FIXTURES = Path(__file__).parent / "fixtures"
USER_A = uuid4()
USER_B = uuid4()


def _store_baseline(repos, user_id, threshold: float = 0.9):
    row, _ = repos.baselines.replace_current_baseline(
        user_id,
        NewBaseline(id=uuid4(), hesitation_threshold_s=threshold, median_pause_s=0.45,
                    median_f0_hz=110.0, mean_loudness_db=62.0, flags=["no_f0"]),
    )
    return row


@pytest.fixture
def current():
    return {"id": USER_A}  # a test switches user with current["id"] = ...


@pytest.fixture
def repos(current):
    return build_memory_repos()


@pytest.fixture(autouse=True)
def _signed_in_user(repos, current):
    """USER_A is signed in and has a baseline (the baseline is required)."""
    _store_baseline(repos, USER_A)
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=current["id"])
    main.app.dependency_overrides[get_repos] = lambda: repos
    yield
    main.app.dependency_overrides.clear()


def _minimal_result() -> EvaluationResultV2:
    return EvaluationResultV2(
        schema_version="2.1", status="insufficient_audio", reason="low_voiced_ratio",
        overall=None, label=None, components={}, subscores={}, accuracy_detail={},
        fluency_detail={}, pitch_detail={}, audio={"duration_s": 1.0, "voiced_ratio": 0.0},
        baseline=None, alignment=[], pauses=[], fillers=[], sentences=[], stt=None,
        flags=["no_baseline"], warnings=[],
        display_only={"loudness_db": None, "loudness_ref_db": None},
    )


def _post(
    monkeypatch,
    raw: str,
    captured: dict | None = None,
    *,
    save_handler=None,
):
    def fake(audio_path, script, baseline, *, vad_params):
        if captured is not None:
            captured["baseline"] = baseline
        return _minimal_result()

    monkeypatch.setattr(main, "evaluate_session", fake)
    if save_handler is not None:
        monkeypatch.setattr(main, "_save_result_to_history", save_handler)
    return TestClient(main.app).post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"x", "audio/wav")},
        data={"script": "Hello.", "baseline_profile": raw},
    )


def test_evaluate_uses_stored_baseline(monkeypatch):
    cap: dict = {}
    assert _post(monkeypatch, "", cap).status_code == 200
    assert cap["baseline"] == BaselineProfile(
        median_pause_s=0.45, hesitation_threshold_s=0.9, median_f0_hz=110.0,
        mean_loudness_db=62.0, flags=["no_f0"],
    )


def test_evaluate_ignores_client_baseline_profile(monkeypatch):
    fake_profile = json.dumps({"median_pause_s": 0.5, "hesitation_threshold_s": 1.2,
                               "median_f0_hz": 300.0, "mean_loudness_db": 99.0, "flags": []})
    cap: dict = {}
    assert _post(monkeypatch, fake_profile, cap).status_code == 200
    assert cap["baseline"].hesitation_threshold_s == 0.9
    assert _post(monkeypatch, "not json", cap).status_code == 200


def test_evaluate_without_baseline_returns_409(monkeypatch, current):
    current["id"] = USER_B  # USER_B has no baseline
    cap: dict = {}
    r = _post(monkeypatch, "", cap)
    assert r.status_code == 409
    assert r.json()["error_code"] == "baseline_required"
    assert cap == {}  # Evaluate Pipeline is not called


def test_evaluate_without_baseline_allowed_when_not_required(monkeypatch, current):
    monkeypatch.setattr(settings, "baseline_required", False)
    current["id"] = USER_B
    cap: dict = {}
    assert _post(monkeypatch, "", cap).status_code == 200
    assert cap["baseline"] is None


def test_evaluate_other_users_baseline_not_used(monkeypatch, repos, current):
    _store_baseline(repos, USER_B, threshold=1.1)
    cap: dict = {}
    _post(monkeypatch, "", cap)
    assert cap["baseline"].hesitation_threshold_s == 0.9  # USER_A's baseline, not USER_B's


def test_evaluate_baseline_storage_error_returns_503(monkeypatch, repos):
    def broken(user_id):
        raise StorageError("down")

    monkeypatch.setattr(repos.baselines, "get_current_baseline", broken)
    r = _post(monkeypatch, "")
    assert r.status_code == 503
    assert r.json()["error_code"] == "baseline_unavailable"


def test_evaluate_saves_current_baseline_id(monkeypatch, repos):
    saved: dict = {}

    def fake_save(**kwargs):
        saved.update(kwargs)
        return str(uuid4())

    _post(monkeypatch, "", save_handler=fake_save)
    assert saved["baseline_id"] == repos.baselines.get_current_baseline(USER_A).id


def test_evaluate_returns_saved_session_id(monkeypatch):
    session_id = uuid4()
    saved: dict = {}

    def fake_save(**kwargs):
        saved.update(kwargs)
        return str(session_id)

    response = _post(
        monkeypatch,
        "",
        save_handler=fake_save,
    )

    assert response.status_code == 200
    assert response.json()["saved"] is True
    assert response.json()["session_id"] == str(session_id)
    assert saved["script"] == "Hello."


def test_evaluate_save_failure_keeps_result_and_logs_without_script(
    monkeypatch, caplog
):
    script = "Private practice script"

    def fail_save(**kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(
        main,
        "evaluate_session",
        lambda audio_path, script, baseline, *, vad_params: _minimal_result(),
    )
    monkeypatch.setattr(main, "_save_result_to_history", fail_save)

    response = TestClient(main.app).post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"x", "audio/wav")},
        data={"script": script},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_audio"
    assert response.json()["saved"] is False
    assert response.json()["session_id"] is None
    assert "Failed to save evaluation result to session history" in caplog.text
    assert script not in caplog.text


def _ok_result() -> EvaluationResultV2:
    return EvaluationResultV2.model_validate_json(
        (FIXTURES / "evaluation_ok.json").read_text(encoding="utf-8")
    )


def _fake_encode(source, out):
    assert source != out  # FFmpeg refuses to overwrite its own input
    out.write_bytes(b"opus")


def test_save_webm_upload_stores_audio_and_series(monkeypatch, tmp_path):
    repos = build_memory_repos()
    monkeypatch.setattr(main, "encode_opus", _fake_encode)
    upload = tmp_path / "recording.webm"
    upload.write_bytes(b"raw")
    user_id = uuid4()

    session_id = main._save_result_to_history(
        repos=repos,
        user_id=user_id, script="Hello.", result=_ok_result(), source_audio_path=upload
    )

    row = repos.sessions.get_session(user_id, UUID(session_id))
    assert row.audio_path == f"{user_id}/{session_id}.webm"
    assert row.series_path == f"{user_id}/{session_id}.series.json"
    assert row.result["pitch_detail"]["contour_st"] is None
    assert repos.files._state.files[("audio", row.audio_path)] == b"opus"


def test_save_insufficient_audio_stores_row_without_files(monkeypatch):
    repos = build_memory_repos()
    user_id = uuid4()

    session_id = main._save_result_to_history(
        repos=repos,
        user_id=user_id, script="Hello.", result=_minimal_result(), source_audio_path=None
    )

    row = repos.sessions.get_session(user_id, UUID(session_id))
    assert row.status == "insufficient_audio"
    assert row.audio_path is None and row.series_path is None
    assert repos.files._state.files == {}


def test_save_insert_failure_removes_uploaded_files(monkeypatch, tmp_path):
    repos = build_memory_repos()
    monkeypatch.setattr(main, "encode_opus", _fake_encode)

    def fail_insert(*args, **kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(repos.sessions, "create_session", fail_insert)
    upload = tmp_path / "recording.webm"
    upload.write_bytes(b"raw")

    with pytest.raises(RuntimeError):
        main._save_result_to_history(
            repos=repos,
            user_id=uuid4(), script="Hello.", result=_ok_result(), source_audio_path=upload
        )
    assert repos.files._state.files == {}
