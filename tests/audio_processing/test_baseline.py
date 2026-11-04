import pytest
from dataclasses import dataclass

from src.audio_processing.contracts import Pause
from src.audio_processing.baseline import compute_baseline_pause_profile

def test_empty_pauses_returns_no_baseline_flag():
    """Kiểm tra khi không có khoảng lặng nào[cite: 1]."""
    result = compute_baseline_pause_profile([])
    assert result["median_pause_s"] is None
    assert result["hesitation_threshold_s"] == 0.7
    assert "no_baseline" in result["flags"]

def test_fewer_than_5_pauses_flags_unreliable():
    """Kiểm tra nếu có ít hơn 5 khoảng lặng, cờ unreliable bật lên[cite: 1]."""
    # Tạo 4 khoảng lặng, mỗi khoảng dài 0.5s
    pauses = [Pause(start_s=0.0, end_s=0.5)] * 4
    result = compute_baseline_pause_profile(pauses)
    
    assert "baseline_pause_unreliable" in result["flags"]
    assert result["median_pause_s"] == 0.5
    assert result["hesitation_threshold_s"] == 1.0

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