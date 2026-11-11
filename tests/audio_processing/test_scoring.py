"""Test cho compute_overall / get_label (scoring_framework.md §3, §11, §12).

Các số liệu bên dưới là ví dụ tính tay tự đặt ở scoring_framework.md §12,
không phải số đo từ dữ liệu thật.

§12 ghi F = 89.17 là số đã làm tròn; test dùng giá trị chính xác
(100 + 80 + 87.5) / 3 = 89.1667, Overall vẫn 89.85.

Ghi chú: compute_overall / get_label sẽ đổi ở mục 3.9 để xử lý None. Nhãn sẽ
tính trên điểm làm tròn half-up 1 chữ số (phase3_decision #14), nên các biên
nhãn ở đây được chọn sao cho đúng cả trước và sau quyết định #14 (84.99/49.99
cố ý không dùng vì làm tròn half-up thành 85.0/50.0).
"""

import pytest

from src.audio_processing.scoring import compute_overall, get_label

S12_A = 94.0
S12_F_WPM = 100.0
S12_F_PAUSE = 80.0
S12_F_FILLER = 87.5
S12_P_CLARITY = 90.0
S12_P_PITCH = 75.0
S12_S = 90.0
S12_OVERALL = 89.85


def test_s12_overall():
    f = (S12_F_WPM + S12_F_PAUSE + S12_F_FILLER) / 3
    p = 0.5 * S12_P_CLARITY + 0.5 * S12_P_PITCH
    assert compute_overall(S12_A, f, p, S12_S) == pytest.approx(S12_OVERALL)


@pytest.mark.parametrize(
    ("overall", "expected"),
    [
        (85.0, "Excellent"),
        (84.9, "Good"),
        (70.0, "Good"),
        (69.9, "Need improvements"),
        (50.0, "Need improvements"),
        (49.9, "Need practice more"),
    ],
)
def test_get_label_boundaries(overall, expected):
    assert get_label(overall) == expected


@pytest.mark.parametrize(
    ("a", "f", "p", "s", "expected"),
    [
        (100, 0, 0, 0, 40),
        (0, 100, 0, 0, 30),
        (0, 0, 100, 0, 20),
        (0, 0, 0, 100, 10),
    ],
)
def test_overall_weights_independent(a, f, p, s, expected):
    assert compute_overall(a, f, p, s) == pytest.approx(expected)
