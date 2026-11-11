import pytest
from dataclasses import dataclass

from src.audio_processing.contracts import Pause
from src.audio_processing.baseline import compute_baseline_pause_profile

def test_empty_pauses_uses_fixed_threshold_unreliable_not_no_baseline():
    """D13: 0 khoảng lặng -> ngưỡng 0.7, cờ unreliable, KHÔNG gắn no_baseline."""
    result = compute_baseline_pause_profile([])
    assert result["median_pause_s"] is None
    assert result["hesitation_threshold_s"] == 0.7
    assert "baseline_pause_unreliable" in result["flags"]
    assert "no_baseline" not in result["flags"]


def test_fewer_than_5_pauses_uses_fixed_threshold():
    """D13: < 5 khoảng lặng -> ngưỡng cố định 0.7 (không dùng 2 x median)."""
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
    """Kiểm tra ngưỡng tối đa không vượt quá 1.2s dù median lớn[cite: 1]."""
    # Tạo 5 khoảng lặng, mỗi khoảng 0.8s -> 2 * 0.8 = 1.6s
    pauses = [Pause(start_s=0.0, end_s=0.8)] * 5
    result = compute_baseline_pause_profile(pauses)
    
    assert "baseline_pause_unreliable" not in result["flags"]
    assert result["median_pause_s"] == 0.8
    assert result["hesitation_threshold_s"] == 1.2

def test_threshold_minimum_is_0_7s():
    """Kiểm tra ngưỡng tối thiểu luôn được giữ ở 0.7s[cite: 1]."""
    # Tạo 5 khoảng lặng, mỗi khoảng 0.35s -> 2 * 0.35 = 0.7s
    pauses = [Pause(start_s=0.0, end_s=0.35)] * 5
    result = compute_baseline_pause_profile(pauses)
    
    assert result["median_pause_s"] == 0.35
    assert result["hesitation_threshold_s"] == 0.7

def test_threshold_floor_survives_float_noise():
    """Bảo vệ max(0.7, ...): 1.15 - 0.8 = 0.34999999999999987 (nhiễu float, không phải số đo).

    median = 0.34999999999999987 -> 2 * median = 0.6999999999999997 < 0.7. Thiếu max thì
    ngưỡng trả 0.6999999999999997 != 0.7.
    """
    pauses = [Pause(start_s=0.8, end_s=1.15)] * 5
    assert pauses[0].end_s - pauses[0].start_s == 0.34999999999999987
    result = compute_baseline_pause_profile(pauses)
    assert result["hesitation_threshold_s"] == 0.7


def test_median_calculated_correctly():
    """Kiểm tra tính đúng trung vị với bộ dữ liệu phân tán[cite: 1]."""
    # Độ dài: 0.4, 0.5, 0.6, 0.8, 1.0 -> Trung vị (median) phải là 0.6
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
import math
from src.audio_processing.baseline import mean_loudness_db


def test_mean_loudness_db_hand_computed():
    assert mean_loudness_db([60.0, 70.0, 80.0]) == pytest.approx(70.0)


def test_mean_loudness_db_ignores_nan_and_inf():
    assert mean_loudness_db([60.0, math.nan, 80.0, math.inf, -math.inf]) == pytest.approx(70.0)


def test_mean_loudness_db_empty_or_all_invalid_is_none():
    assert mean_loudness_db([]) is None
    assert mean_loudness_db([math.nan, math.inf]) is None
