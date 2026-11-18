import math

import pytest

from src.audio_processing.baseline import (
    compute_baseline_pause_profile,
    mean_loudness_db,
)
from src.audio_processing.contracts import Pause


def test_empty_pauses_uses_fixed_threshold_unreliable_not_no_baseline():
    """D13: 0 silences -> threshold 0.7, unreliable flag, NO no_baseline tag."""
    result = compute_baseline_pause_profile([])
    assert result["median_pause_s"] is None
    assert result["hesitation_threshold_s"] == 0.7
    assert "baseline_pause_unreliable" in result["flags"]
    assert "no_baseline" not in result["flags"]


def test_fewer_than_5_pauses_uses_fixed_threshold():
    """D13: < 5 silences -> fixed threshold 0.7 (2 x median not used)."""
    pauses = [Pause(start_s=0.0, end_s=0.5)] * 4
    result = compute_baseline_pause_profile(pauses)

    assert "baseline_pause_unreliable" in result["flags"]
    assert "no_baseline" not in result["flags"]
    assert result["median_pause_s"] == 0.5
    assert result["hesitation_threshold_s"] == 0.7


def test_five_pauses_median_0_4_gives_0_8():
    pauses = [Pause(start_s=0.0, end_s=0.4)] * 5
    result = compute_baseline_pause_profile(pauses)
    assert result["flags"] == []
    assert result["hesitation_threshold_s"] == pytest.approx(0.8)


def test_threshold_capped_at_1_2s():
    """Check the max threshold never exceeds 1.2s even with a large median[cite: 1]."""
    # Create 5 silences, 0.8s each -> 2 * 0.8 = 1.6s
    pauses = [Pause(start_s=0.0, end_s=0.8)] * 5
    result = compute_baseline_pause_profile(pauses)

    assert "baseline_pause_unreliable" not in result["flags"]
    assert result["median_pause_s"] == 0.8
    assert result["hesitation_threshold_s"] == 1.2


def test_threshold_minimum_is_0_7s():
    """Check the min threshold always stays at 0.7s[cite: 1]."""
    # Create 5 silences, 0.35s each -> 2 * 0.35 = 0.7s
    pauses = [Pause(start_s=0.0, end_s=0.35)] * 5
    result = compute_baseline_pause_profile(pauses)

    assert result["median_pause_s"] == 0.35
    assert result["hesitation_threshold_s"] == 0.7


def test_threshold_floor_survives_float_noise():
    """Guards max(0.7, ...): 1.15 - 0.8 = 0.34999999999999987 (float noise, not a measurement).

    median = 0.34999999999999987 -> 2 * median = 0.6999999999999997 < 0.7. Without max the
    threshold would be 0.6999999999999997 != 0.7.
    """
    pauses = [Pause(start_s=0.8, end_s=1.15)] * 5
    assert pauses[0].end_s - pauses[0].start_s == 0.34999999999999987
    result = compute_baseline_pause_profile(pauses)
    assert result["hesitation_threshold_s"] == 0.7


def test_median_calculated_correctly():
    """Check the median is correct on a scattered data set[cite: 1]."""
    # Lengths: 0.4, 0.5, 0.6, 0.8, 1.0 -> the median must be 0.6
    pauses = [
        Pause(start_s=0.0, end_s=0.4),
        Pause(start_s=0.0, end_s=0.5),
        Pause(start_s=0.0, end_s=0.6),
        Pause(start_s=0.0, end_s=0.8),
        Pause(start_s=0.0, end_s=1.0),
    ]
    result = compute_baseline_pause_profile(pauses)

    assert result["median_pause_s"] == 0.6
    assert result["hesitation_threshold_s"] == 1.2  # 0.6 * 2.0 = 1.2


# --- mean_loudness_db (D11) ---
def test_mean_loudness_db_hand_computed():
    assert mean_loudness_db([60.0, 70.0, 80.0]) == pytest.approx(70.0)


def test_mean_loudness_db_ignores_nan_and_inf():
    assert mean_loudness_db([60.0, math.nan, 80.0, math.inf, -math.inf]) == pytest.approx(70.0)


def test_mean_loudness_db_empty_or_all_invalid_is_none():
    assert mean_loudness_db([]) is None
    assert mean_loudness_db([math.nan, math.inf]) is None


def test_build_baseline_profile_uses_min_pause_s_from_config(monkeypatch):
    # Baseline and Evaluate must cut pauses at the same length (MIN_PAUSE_S), not a copy of 0.35
    from src.app.config import MIN_PAUSE_S
    from src.audio_processing import baseline as baseline_module

    seen: dict = {}

    class _StopError(Exception):
        pass

    def fake_find_pauses(segments, *, min_pause_s):
        seen["min_pause_s"] = min_pause_s
        raise _StopError

    monkeypatch.setattr(baseline_module, "detect_speech", lambda master, params: [])
    monkeypatch.setattr(baseline_module, "check_audio_quality", lambda segments, duration: None)
    monkeypatch.setattr(baseline_module, "find_pauses", fake_find_pauses)
    master = type("Master", (), {"duration_s": 30.0})()
    try:
        baseline_module.build_baseline_profile(master, vad_params=None)
    except _StopError:
        pass
    assert seen["min_pause_s"] == MIN_PAUSE_S
