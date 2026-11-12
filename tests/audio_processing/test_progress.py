from src.audio_processing.progress import compute_progress


def test_compute_progress_uses_last_three_minus_previous_three():
    assert compute_progress([70, 72, 71, 78, 80, 79]) == 8


def test_compute_progress_skips_null_scores():
    assert compute_progress([70, None, 72, 71, 78, 80, 79]) == 8


def test_compute_progress_uses_most_recent_six_scores():
    assert compute_progress([10, 20, 30, 70, 72, 71, 78, 80, 79]) == 8


def test_compute_progress_returns_none_with_fewer_than_six_scores():
    assert compute_progress([70, 72, None, 71, 78, 80]) is None


def test_compute_progress_returns_none_when_no_scores():
    assert compute_progress([None, None]) is None
