from src.audio_processing.contracts import Pause, SpeechSegment
from src.audio_processing.vad import find_pauses

MIN_PAUSE = 0.35


def seg(start: float, end: float) -> SpeechSegment:
    return SpeechSegment(start_s=start, end_s=end)


def test_no_segments_has_no_pauses():
    assert find_pauses([], min_pause_s=MIN_PAUSE) == []


def test_single_segment_has_no_pauses():
    assert find_pauses([seg(0.0, 2.0)], min_pause_s=MIN_PAUSE) == []


def test_gap_exactly_at_threshold_is_kept():
    segments = [seg(0.0, 1.0), seg(1.35, 2.0)]          
    assert find_pauses(segments, min_pause_s=MIN_PAUSE) == [Pause(1.0, 1.35)]


def test_gap_just_below_threshold_is_dropped():
    segments = [seg(0.0, 1.0), seg(1.34, 2.0)]         
    assert find_pauses(segments, min_pause_s=MIN_PAUSE) == []


def test_only_long_gaps_are_kept_in_order():
    segments = [seg(0.0, 1.0), seg(1.5, 2.0), seg(2.1, 3.0), seg(4.0, 5.0)]
    # các khoảng: 0.5 (giữ), 0.1 (bỏ), 1.0 (giữ)
    assert find_pauses(segments, min_pause_s=MIN_PAUSE) == [
        Pause(1.0, 1.5),
        Pause(3.0, 4.0),
    ]


def test_touching_segments_have_no_pause():
    segments = [seg(0.0, 1.0), seg(1.0, 2.0)]          
    assert find_pauses(segments, min_pause_s=MIN_PAUSE) == []


def test_leading_silence_is_not_a_pause():
    segments = [seg(5.0, 6.0), seg(6.5, 7.0)]       
    assert find_pauses(segments, min_pause_s=MIN_PAUSE) == [Pause(6.0, 6.5)]


def test_pause_duration_matches_gap():
    segments = [seg(0.0, 1.0), seg(1.75, 2.0)]
    (pause,) = find_pauses(segments, min_pause_s=MIN_PAUSE)
    assert pause.duration_s == 0.75

# ==========================================
# Lỗi float ở biên min_pause 0.35 s
# ==========================================

def test_float_boundary_0_80_to_1_15_is_kept():
    # 1.15 - 0.8 = 0.34999999999999987 trong float nhưng danh nghĩa là 0.35.
    # (Cặp 0.68 -> 1.03 thực tế cho đúng 0.35, không tái hiện lỗi.)
    segments = [seg(0.0, 0.8), seg(1.15, 2.0)]
    assert find_pauses(segments, min_pause_s=MIN_PAUSE) == [Pause(0.8, 1.15)]


def test_float_boundary_sweep_nominal_0_35_always_kept():
    from decimal import Decimal

    missed = []
    for i in range(0, 1001):
        end = Decimal(i) / Decimal(100)
        start = end + Decimal("0.35")
        got = find_pauses([seg(0.0, float(end)), seg(float(start), float(start) + 1.0)],
                          min_pause_s=MIN_PAUSE)
        if len(got) != 1:
            missed.append(float(end))
    assert missed == []
