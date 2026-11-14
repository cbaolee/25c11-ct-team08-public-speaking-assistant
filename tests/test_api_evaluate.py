"""Test kiểm đầu vào baseline_profile của POST /api/evaluate (CLAUDE.md 1.9.2 #23).

evaluate_session bị monkeypatch: chỉ kiểm lớp parse/validate ở main.py.
Mọi số trong test là số tự chọn để chạm biên (không phải số đo).
"""

import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.app.main as main
from src.audio_processing.baseline import compute_baseline_pause_profile
from src.audio_processing.contracts import BaselineProfile, Pause
from src.audio_processing.result_schema import EvaluationResultV2


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
    user_id=None,
    save_handler=None,
):
    def fake(audio_path, script, baseline, *, vad_params):
        if captured is not None:
            captured["baseline"] = baseline
        return _minimal_result()

    monkeypatch.setattr(main, "evaluate_session", fake)
    monkeypatch.setattr(main, "_current_user_id", lambda: user_id)
    if save_handler is not None:
        monkeypatch.setattr(main, "_save_result_to_history", save_handler)
    return TestClient(main.app).post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"x", "audio/wav")},
        data={"script": "Hello.", "baseline_profile": raw},
    )


def _body(**over) -> str:
    base = {"median_pause_s": 0.5, "hesitation_threshold_s": 1.0, "median_f0_hz": 120.0,
            "mean_loudness_db": 60.0, "flags": []}
    base.update(over)
    return json.dumps(base)


def _assert_invalid(r):
    assert r.status_code == 422
    assert r.json()["error_code"] == "invalid_baseline"


# ---- Việc 1: số nguyên khổng lồ -> OverflowError phải thành 422, không phải 500 ----

@pytest.mark.parametrize("field", ["hesitation_threshold_s", "median_pause_s", "median_f0_hz",
                                   "mean_loudness_db"])
def test_huge_integer_is_422_not_500(monkeypatch, field):
    raw = _body(**{field: 123456789}).replace("123456789", "9" * 400)
    assert "9" * 400 in raw
    _assert_invalid(_post(monkeypatch, raw))


# ---- Việc 2: miền giá trị ----

@pytest.mark.parametrize("bad", [0.69, 1.21, 0.0, -1.0])
def test_threshold_out_of_range_rejected(monkeypatch, bad):
    _assert_invalid(_post(monkeypatch, _body(hesitation_threshold_s=bad)))


@pytest.mark.parametrize("ok", [0.7, 1.2])
def test_threshold_at_bounds_accepted(monkeypatch, ok):
    cap: dict = {}
    r = _post(monkeypatch, _body(hesitation_threshold_s=ok), cap)
    assert r.status_code == 200
    assert cap["baseline"].hesitation_threshold_s == ok


def test_threshold_float_noise_below_0_7_accepted(monkeypatch):
    # 0.6999999999999997 = 2 * 0.34999999999999987 (nhiễu float); round(.,6) -> 0.7 -> hợp lệ
    assert _post(monkeypatch, _body(hesitation_threshold_s=0.6999999999999997)).status_code == 200


@pytest.mark.parametrize("bad", [0.34, 0.0, -0.5])
def test_median_pause_below_min_pause_rejected(monkeypatch, bad):
    _assert_invalid(_post(monkeypatch, _body(median_pause_s=bad)))


def test_median_pause_null_and_boundary_accepted(monkeypatch):
    assert _post(monkeypatch, _body(median_pause_s=None)).status_code == 200
    assert _post(monkeypatch, _body(median_pause_s=0.35)).status_code == 200
    # 0.34999999999999987 -> round 6 -> 0.35
    assert _post(monkeypatch, _body(median_pause_s=0.34999999999999987)).status_code == 200


@pytest.mark.parametrize("bad", [0.0, -100.0])
def test_median_f0_not_positive_rejected(monkeypatch, bad):
    _assert_invalid(_post(monkeypatch, _body(median_f0_hz=bad)))


def test_median_f0_null_accepted(monkeypatch):
    assert _post(monkeypatch, _body(median_f0_hz=None)).status_code == 200


def test_loudness_any_finite_or_null_accepted(monkeypatch):
    assert _post(monkeypatch, _body(mean_loudness_db=-20.0)).status_code == 200
    assert _post(monkeypatch, _body(mean_loudness_db=None)).status_code == 200


@pytest.mark.parametrize("bad", ['"x"', "true", "NaN", "Infinity"])
def test_loudness_not_finite_number_rejected(monkeypatch, bad):
    raw = _body().replace("60.0", bad)
    _assert_invalid(_post(monkeypatch, raw))


@pytest.mark.parametrize("flags", [["no_baseline"], ["bogus"], ["no_f0", "filler_from_vad_only"]])
def test_unknown_flag_rejected(monkeypatch, flags):
    _assert_invalid(_post(monkeypatch, _body(flags=flags)))


def test_allowed_flags_accepted(monkeypatch):
    r = _post(monkeypatch, _body(flags=["baseline_pause_unreliable", "no_f0"]))
    assert r.status_code == 200


# ---- round-trip: profile đúng dạng analyze_baseline sinh ra phải được nhận lại ----

def test_round_trip_profile_from_analyze_baseline_shape(monkeypatch):
    pauses = [Pause(start_s=0.0, end_s=0.4)] * 5  # median 0.4 -> ngưỡng 0.8, flags []
    pp = compute_baseline_pause_profile(pauses)
    profile = BaselineProfile(
        median_pause_s=pp["median_pause_s"], hesitation_threshold_s=pp["hesitation_threshold_s"],
        median_f0_hz=118.5, mean_loudness_db=61.0, flags=pp["flags"],
    )
    cap: dict = {}
    r = _post(monkeypatch, json.dumps(asdict(profile)), cap)
    assert r.status_code == 200
    assert cap["baseline"] == profile


def test_round_trip_profile_with_nulls_and_flags(monkeypatch):
    pp = compute_baseline_pause_profile([])  # median None, ngưỡng 0.7, unreliable
    profile = BaselineProfile(
        median_pause_s=pp["median_pause_s"], hesitation_threshold_s=pp["hesitation_threshold_s"],
        median_f0_hz=None, mean_loudness_db=None, flags=pp["flags"] + ["no_f0"],
    )
    cap: dict = {}
    assert _post(monkeypatch, json.dumps(asdict(profile)), cap).status_code == 200
    assert cap["baseline"] == profile


def test_evaluate_returns_saved_session_id(monkeypatch):
    session_id = uuid4()
    saved: dict = {}

    def fake_save(**kwargs):
        saved.update(kwargs)
        return str(session_id)

    response = _post(
        monkeypatch,
        "",
        user_id=uuid4(),
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
    monkeypatch.setattr(main, "_current_user_id", lambda: uuid4())
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
