"""Tests for how POST /api/evaluate gets its baseline (server reads it from the DB, M6).

evaluate_session is monkeypatched: these tests only check which baseline main.py passes in.
Numbers in profiles are picked by hand for the tests (not measurements).
"""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.models import NewBaseline, StorageError
from src.app.deps import CurrentUser, get_current_user
from src.audio_processing.contracts import BaselineProfile
from src.audio_processing.result_schema import EvaluationResultV2

USER_A = uuid4()
USER_B = uuid4()


def _minimal_result() -> EvaluationResultV2:
    return EvaluationResultV2(
        schema_version="2.0", status="insufficient_audio", reason="low_voiced_ratio",
        overall=None, label=None, components={}, subscores={}, accuracy_detail={},
        fluency_detail={}, pitch_detail={}, audio={"duration_s": 1.0, "voiced_ratio": 0.0},
        baseline=None, alignment=[], pauses=[], fillers=[], sentences=[], stt=None,
        flags=["no_baseline"], warnings=[],
        display_only={"loudness_db": None, "loudness_ref_db": None},
    )


@pytest.fixture
def current():
    return {"id": USER_A}


@pytest.fixture
def repos(current):
    repos = build_memory_repos()
    main.app.dependency_overrides[get_repos] = lambda: repos
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=current["id"])
    yield repos
    main.app.dependency_overrides.clear()


def _store_baseline(repos, user_id, threshold: float = 0.9):
    repos.baselines.replace_current_baseline(
        user_id,
        NewBaseline(id=uuid4(), hesitation_threshold_s=threshold, median_pause_s=0.45,
                    median_f0_hz=110.0, mean_loudness_db=62.0, flags=["no_f0"]),
    )


def _post(monkeypatch, captured: dict, baseline_profile: str = ""):
    def fake(audio_path, script, baseline, *, vad_params):
        captured["baseline"] = baseline
        return _minimal_result()

    monkeypatch.setattr(main, "evaluate_session", fake)
    return TestClient(main.app).post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"x", "audio/wav")},
        data={"script": "Hello.", "baseline_profile": baseline_profile},
    )


def test_evaluate_uses_stored_baseline(monkeypatch, repos):
    _store_baseline(repos, USER_A)
    cap: dict = {}
    r = _post(monkeypatch, cap)
    assert r.status_code == 200
    assert cap["baseline"] == BaselineProfile(
        median_pause_s=0.45, hesitation_threshold_s=0.9, median_f0_hz=110.0,
        mean_loudness_db=62.0, flags=["no_f0"],
    )


def test_evaluate_without_baseline_passes_none(monkeypatch, repos):
    # evaluate_session turns baseline=None into the "no_baseline" flag
    cap: dict = {}
    assert _post(monkeypatch, cap).status_code == 200
    assert cap["baseline"] is None


def test_evaluate_ignores_client_baseline_profile(monkeypatch, repos):
    fake_profile = json.dumps({"median_pause_s": 0.5, "hesitation_threshold_s": 1.2,
                               "median_f0_hz": 300.0, "mean_loudness_db": 99.0, "flags": []})
    cap: dict = {}
    r = _post(monkeypatch, cap, baseline_profile=fake_profile)
    assert r.status_code == 200
    assert cap["baseline"] is None


def test_evaluate_ignores_invalid_client_baseline_profile(monkeypatch, repos):
    cap: dict = {}
    assert _post(monkeypatch, cap, baseline_profile="not json").status_code == 200


def test_evaluate_other_users_baseline_not_used(monkeypatch, repos, current):
    _store_baseline(repos, USER_B)
    cap: dict = {}
    _post(monkeypatch, cap)
    assert cap["baseline"] is None


def test_evaluate_baseline_storage_error_returns_503(monkeypatch, repos):
    def broken(user_id):
        raise StorageError("down")

    monkeypatch.setattr(repos.baselines, "get_current_baseline", broken)
    r = _post(monkeypatch, {})
    assert r.status_code == 503
    assert r.json()["error_code"] == "baseline_unavailable"
