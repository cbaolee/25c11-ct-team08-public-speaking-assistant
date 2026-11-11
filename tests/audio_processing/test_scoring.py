"""Test cho compute_overall / get_label (scoring_framework.md §3, §11, §12).

Các số liệu bên dưới là ví dụ tính tay tự đặt ở scoring_framework.md §12,
không phải số đo từ dữ liệu thật.

§12 ghi F = 89.17 là số đã làm tròn; test dùng giá trị chính xác
(100 + 80 + 87.5) / 3 = 89.1667, Overall vẫn 89.85.

Mục 3.9 (Pha 3): compute_overall / get_label xử lý None; nhãn tính trên điểm
làm tròn half-up 1 chữ số (phase3_decision #14), nên các biên nhãn ở đây tránh
84.99/49.99 (làm tròn thành 85.0/50.0); có test riêng cho ca đó bên dưới.
Mọi số bên dưới là số tính tay, không phải số đo.
"""

import math
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.audio_processing import scoring
from src.audio_processing.contracts import BaselineProfile
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


# ---------------------------------------------------------------- pitch ----


@pytest.mark.parametrize(
    ("r_st", "expected"),
    [(5, 75.0), (6, 100.0), (2, 0.0), (1, 0.0), (8, 100.0), (None, None)],
)
def test_pitch_score_from_range(r_st, expected):
    # §6.2: 25 * (5 - 2) = 75. Số tính tay, không phải số đo.
    assert scoring.pitch_score_from_range(r_st) == expected


def _f0_from_st(st_values, f0_ref=100.0):
    return [f0_ref * 2 ** (st / 12) for st in st_values]


def test_pitch_range_st_hand_computed():
    # ST = 0..10 (11 mẫu). Phân vị linear: P90 ở chỉ số 0.9*10 = 9 -> 9;
    # P10 ở chỉ số 1 -> 1. R_st = 9 - 1 = 8 (tính tay).
    f0 = _f0_from_st(range(11))
    assert scoring.pitch_range_st(f0, 100.0) == pytest.approx(8.0)


def test_pitch_range_st_step_0625():
    # ST = k * 0.625, k = 0..10: P90 = 5.625, P10 = 0.625 -> R_st = 5.0 (tính tay).
    f0 = _f0_from_st([k * 0.625 for k in range(11)])
    assert scoring.pitch_range_st(f0, 100.0) == pytest.approx(5.0)


def test_pitch_range_st_ignores_zero_nan_negative():
    f0 = _f0_from_st(range(11)) + [0.0, math.nan, -5.0]
    assert scoring.pitch_range_st(f0, 100.0) == pytest.approx(8.0)


def test_pitch_range_st_empty_or_bad_ref():
    assert scoring.pitch_range_st([], 100.0) is None
    assert scoring.pitch_range_st([0.0, math.nan], 100.0) is None
    assert scoring.pitch_range_st([100.0, 200.0], 0.0) is None
    assert scoring.pitch_range_st([100.0, 200.0], math.nan) is None


def _baseline(f0):
    return BaselineProfile(
        median_pause_s=0.5, hesitation_threshold_s=1.0, median_f0_hz=f0,
        mean_loudness_db=None, flags=[]
    )


def _fake_master():
    return SimpleNamespace(path="khong_ton_tai.wav")


def test_score_pitch_with_baseline(monkeypatch):
    f0 = _f0_from_st([k * 0.625 for k in range(11)])
    monkeypatch.setattr(scoring, "_extract_f0", lambda master: f0)
    res = scoring.score_pitch(_fake_master(), _baseline(120.0))
    assert res.f0_ref_source == "baseline"
    assert res.f0_ref_hz == 120.0
    assert res.range_semitones == pytest.approx(5.0)  # R_st không đổi khi đổi F0_ref
    assert res.score == pytest.approx(75.0)
    assert res.flags == []


def test_score_pitch_without_baseline_uses_session_median(monkeypatch):
    f0 = _f0_from_st([k * 0.625 for k in range(11)])
    monkeypatch.setattr(scoring, "_extract_f0", lambda master: f0)
    res = scoring.score_pitch(_fake_master(), None)
    assert res.f0_ref_source == "session"
    # 11 mẫu: median là phần tử thứ 6 (k = 5) -> ST 3.125
    assert res.f0_ref_hz == pytest.approx(100.0 * 2 ** (3.125 / 12))
    assert res.score == pytest.approx(75.0)
    assert "no_baseline" not in res.flags  # cờ do pipeline gắn


def test_score_pitch_baseline_f0_none_falls_back_to_session(monkeypatch):
    monkeypatch.setattr(scoring, "_extract_f0", lambda master: [100.0, 110.0, 120.0])
    res = scoring.score_pitch(_fake_master(), _baseline(None))
    assert res.f0_ref_source == "session"
    assert res.f0_ref_hz == pytest.approx(110.0)


def test_score_pitch_no_voiced_f0(monkeypatch):
    monkeypatch.setattr(scoring, "_extract_f0", lambda master: [])
    res = scoring.score_pitch(_fake_master(), _baseline(120.0))
    assert res.score is None
    assert res.range_semitones is None
    assert res.f0_ref_source is None
    assert res.flags == ["no_f0"]


def test_score_pitch_praat_error(monkeypatch):
    def boom(master):
        raise RuntimeError("praat loi")

    monkeypatch.setattr(scoring, "_extract_f0", boom)
    res = scoring.score_pitch(_fake_master(), None)
    assert res.score is None
    assert res.flags == ["no_f0"]


def test_pitch_result_is_frozen():
    res = scoring.PitchResult(None, None, None, None, [])
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
        res.score = 1.0


# -------------------------------------------------------- pronunciation ----


def test_combine_pronunciation_s12():
    # §12: 0.5 * 90 + 0.5 * 75 = 82.5
    assert scoring.combine_pronunciation(90.0, 75.0) == pytest.approx(82.5)


def test_combine_pronunciation_missing_is_none():
    assert scoring.combine_pronunciation(None, 75.0) is None
    assert scoring.combine_pronunciation(90.0, None) is None
    assert scoring.combine_pronunciation(None, None) is None


# --------------------------------------------------------------- overall ----


@pytest.mark.parametrize("idx", [0, 1, 2, 3])
def test_compute_overall_none_in_any_position(idx):
    parts = [90.0, 90.0, 90.0, 90.0]
    parts[idx] = None
    assert compute_overall(*parts) is None


def test_compute_overall_zero_is_not_none():
    assert compute_overall(0.0, 0.0, 0.0, 0.0) == 0.0


def test_s12_total_rounds_to_899_excellent():
    # §12 dùng F = 89.17 (đã làm tròn); thử cả F chính xác (100+80+87.5)/3.
    p = scoring.combine_pronunciation(90.0, 75.0)
    for f in (89.17, (100.0 + 80.0 + 87.5) / 3):
        total = compute_overall(S12_A, f, p, S12_S)
        assert scoring.display_round(total) == Decimal("89.9"), total
        assert get_label(total) == "Excellent"


def test_display_round_89_85_half_up():
    # float 89.85 thực chất là 89.8499999...: round() cho 89.8, Decimal(str) cho 89.9
    assert round(89.85, 1) == 89.8
    assert scoring.display_round(89.85) == Decimal("89.9")


def test_display_round_misc():
    assert scoring.display_round(None) is None
    assert scoring.display_round(0.0) == Decimal("0.0")
    assert scoring.display_round(100.0) == Decimal("100.0")
    assert scoring.display_round(70.04) == Decimal("70.0")


def test_display_round_float_noise_overall_85():
    # 0.4*83.5 + 0.3*98.5 + 0.2*70 + 0.1*80 = 33.4 + 29.55 + 14 + 8 = 84.95 chính xác,
    # nhưng float cho 84.94999999999999 -> trước khi sửa ra 84.9 / "Good".
    total = compute_overall(83.5, 98.5, 70, 80)
    assert scoring.display_round(total) == Decimal("85.0")
    assert get_label(total) == "Excellent"


@pytest.mark.parametrize(
    ("a", "expected"),
    [(83.5, "85.0"), (88.5, "87.0"), (93.5, "89.0")],
)
def test_display_round_reviewer_three_combos(a, expected):
    # F = 98.5, P = 70, S = 80. Tính tay: 0.4a + 29.55 + 14 + 8
    # a=83.5 -> 84.95 -> 85.0; a=88.5 -> 86.95 -> 87.0; a=93.5 -> 88.95 -> 89.0
    total = compute_overall(a, 98.5, 70, 80)
    assert scoring.display_round(total) == Decimal(expected)


def test_display_round_below_half_not_pushed_up():
    assert scoring.display_round(84.9499) == Decimal("84.9")


def test_display_round_scan_x_x5():
    # Mọi x.x5 từ 0.05 đến 99.95: half-up trên số thập phân chính xác = (n+1)/10.
    for n in range(0, 1000):  # x = (10n + 5)/100 = n/10 + 0.05
        x = (10 * n + 5) / 100
        expected = (Decimal(n) + 1) / 10
        assert scoring.display_round(x) == expected.quantize(Decimal("0.1")), x


def test_get_label_none():
    assert get_label(None) is None


@pytest.mark.parametrize(
    ("overall", "expected"),
    [
        (84.96, "Excellent"),  # display_round = 85.0 (phase3 #14)
        (84.94, "Good"),
        (69.95, "Good"),
        (69.94, "Need improvements"),
        (49.95, "Need improvements"),
        (49.94, "Need practice more"),
    ],
)
def test_get_label_uses_rounded_value(overall, expected):
    assert get_label(overall) == expected


# ---------- Mục 3.6 Pha 3: score_accuracy, score_clarity, accuracy_scores ----------
# Mọi số bên dưới là số tính tay (scoring_framework.md §12 và tự đặt), không phải số đo.

import dataclasses  # noqa: E402

import jiwer  # noqa: E402

from src.audio_processing.alignment import align  # noqa: E402
from src.audio_processing.contracts import WordTimestamp  # noqa: E402
from src.audio_processing.scoring import (  # noqa: E402
    AccuracyScores,
    accuracy_scores,
    score_accuracy,
    score_clarity,
)

_PRON = {
    "their": [["DH", "EH1", "R"]],
    "there": [["DH", "EH1", "R"]],
    "think": [["TH", "IH1", "NG", "K"]],
    "sink": [["S", "IH1", "NG", "K"]],  # 1 sub / 4 phoneme -> sim 0.75 -> near_miss
}


def _stub_pron(word: str) -> list[list[str]]:
    return _PRON.get(word, [])


def _hyp_words(*ws: str) -> list[WordTimestamp]:
    return [WordTimestamp(word=w, start_s=float(i), end_s=float(i) + 0.5) for i, w in enumerate(ws)]


def _align(script: str, *ws: str):
    return align(script, _hyp_words(*ws), pron=_stub_pron)


def test_s12_accuracy_example():
    # 100 * (1 - (6+4+2)/200) = 94
    assert score_accuracy(200, 6, 4, 2) == pytest.approx(94.0)


def test_p_clarity_example_s12():
    # 100 * (1 - 5*4/200) = 90
    assert score_clarity(4, 200) == pytest.approx(90.0)


def test_accuracy_clamps_to_zero():
    # (2+1+5)/3 = 2.67 -> 100*(1-2.67) < 0 -> 0
    assert score_accuracy(3, 2, 1, 5) == 0.0


def test_clarity_clamps_to_zero():
    # 5*1/4 = 1.25 -> 100*(1-1.25) < 0 -> 0
    assert score_clarity(1, 4) == 0.0


def test_n_ref_zero_returns_none():
    assert score_accuracy(0, 0, 0, 0) is None
    assert score_clarity(0, 0) is None


def test_negative_counts_raise():
    with pytest.raises(ValueError):
        score_accuracy(10, -1, 0, 0)
    with pytest.raises(ValueError):
        score_clarity(-1, 10)
    with pytest.raises(ValueError):
        score_accuracy(-1, 0, 0, 0)


def test_accuracy_scores_empty_script_flag():
    res = accuracy_scores(_align("", "hello"))
    assert res.accuracy is None and res.clarity is None
    assert "empty_script" in res.flags
    assert res.accuracy_detail["n_ref"] == 0
    assert res.accuracy_detail["n_ins"] == 1


def test_near_miss_not_in_accuracy():
    # "think"->"sink" là near_miss: A không trừ (100); clarity = 100*(1 - 5*1/3) < 0 -> 0.
    res = accuracy_scores(_align("I think so", "I", "sink", "so"))
    assert res.accuracy_detail["n_near_miss"] == 1
    assert res.accuracy_detail["n_sub"] == 0
    assert res.accuracy == pytest.approx(100.0)
    assert res.clarity == 0.0
    # "I", "so" không có trong stub -> OOV -> cờ cmu_oov (ADR-005).
    assert "cmu_oov" in res.flags


def test_no_oov_flag_when_all_words_known():
    res = accuracy_scores(_align("their think", "there", "think"))
    assert res.accuracy_detail["n_oov"] == 0
    assert "cmu_oov" not in res.flags


def test_adr005_consequence_sub_040_near_miss_050():
    # ADR-005 "Hệ quả": N_ref = 100, F = 100, S = 100, P_pitch = 100 cố định.
    # Baseline: A = 100, clarity = 100 -> P = 100 -> Overall = 100.
    def overall(n_sub, n_nm):
        a = score_accuracy(100, n_sub, 0, 0)
        p = scoring.combine_pronunciation(score_clarity(n_nm, 100), 100.0)
        return compute_overall(a, 100.0, p, 100.0)

    base = overall(0, 0)
    assert base == pytest.approx(100.0)
    # 1 sub: A = 99 -> 0.4 * 1 = 0.40
    assert base - overall(1, 0) == pytest.approx(0.40)
    # 1 near_miss: clarity = 100*(1 - 5/100) = 95 -> P = 97.5 -> 0.2 * 2.5 = 0.50
    assert base - overall(0, 1) == pytest.approx(0.50)


def test_filler_not_in_ins():
    res = accuracy_scores(_align("I think so", "I", "um", "think", "so"))
    assert res.accuracy_detail["n_ins"] == 0
    assert res.accuracy == pytest.approx(100.0)


def test_homophone_counts_as_correct():
    res = accuracy_scores(_align("their", "there"))
    assert res.accuracy == pytest.approx(100.0)
    assert res.accuracy_detail["n_homophone"] == 1


def test_accuracy_detail_has_seven_keys_matching_counts():
    result = _align("I think so now", "I", "sink", "so", "uh", "extra")
    res = accuracy_scores(result)
    assert set(res.accuracy_detail) == {
        "n_ref", "n_sub", "n_del", "n_ins", "n_near_miss", "n_homophone", "n_oov",
    }
    assert res.accuracy_detail == result.counts
    assert res.accuracy_detail is not result.counts  # bản sao
    res.accuracy_detail["n_ref"] = 999
    assert result.counts["n_ref"] == 4


def test_accuracy_scores_is_frozen_and_flags_copied():
    result = _align("their", "there")
    res = accuracy_scores(result)
    assert isinstance(res, AccuracyScores)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.accuracy = 0.0  # type: ignore[misc]
    assert res.flags == result.flags
    assert res.flags is not result.flags


@pytest.mark.parametrize(
    "ref, hyp",
    [
        ("the cat sat on mat", "the dog sat mat"),  # 1 sub + 1 del
        ("a b c", "a b x c y"),  # 2 ins
        ("one two three four", "one two three four"),  # 0 lỗi
    ],
)
def test_matches_jiwer_when_no_homophone_or_near_miss(ref, hyp):
    # Mỗi token chuẩn hoá ra đúng một token con nên N_ref khớp jiwer.
    res = accuracy_scores(_align(ref, *hyp.split()))
    d = res.accuracy_detail
    assert d["n_near_miss"] == 0 and d["n_homophone"] == 0
    ours = 1 - (d["n_sub"] + d["n_del"] + d["n_ins"]) / d["n_ref"]
    assert ours == pytest.approx(1 - jiwer.wer(ref, hyp))


# ---------- Mục 3.7 Pha 3: speech_span, WPM, H, filler, compute_fluency ----------
# Mọi số bên dưới là số tính tay (scoring_framework.md §12 và tự đặt), không phải số đo.
# Import đặt ở cấp module; test gọi hàm qua `scoring.<tên>` nên thiếu hàm thì đỏ vì AttributeError.

from src.audio_processing.contracts import (  # noqa: E402
    ClassifiedPause,
    Pause,
    PauseKind,
    SpeechSegment,
)


def _w(word: str, start: float, end: float) -> WordTimestamp:
    return WordTimestamp(word=word, start_s=start, end_s=end)


def _cp(kind: PauseKind) -> ClassifiedPause:
    return ClassifiedPause(pause=Pause(0.0, 1.0), kind=kind)


def test_s12_f_components():
    # §12: tốc độ 142 -> 100; H = 2 -> 80; R = 3% -> 87.5.
    assert scoring.score_wpm(142) == pytest.approx(100.0)
    assert scoring.score_wpm(120) == pytest.approx(75.0)  # 100 - 2.5 * 10
    assert scoring.score_hesitation(2) == pytest.approx(80.0)
    assert scoring.score_filler(3) == pytest.approx(87.5)  # 100 * (10 - 3) / 8


def test_s12_compute_fluency():
    assert scoring.compute_fluency(100.0, 80.0, 87.5) == pytest.approx((100 + 80 + 87.5) / 3)


@pytest.mark.parametrize(
    ("wpm", "expected"),
    [(130, 100.0), (160, 100.0), (110, 50.0), (200, 0.0), (175, 62.5), (None, None)],
)
def test_score_wpm_boundaries(wpm, expected):
    # 110: 100 - 2.5*20 = 50. 175: 100 - 2.5*15 = 62.5. 200: 100 - 100 = 0.
    # Dòng dưới: 300 -> 100 - 2.5*140 = -250 (âm) -> clamp về 0.
    assert scoring.score_wpm(wpm) == expected
    assert scoring.score_wpm(300) == 0.0


def test_score_hesitation_boundaries():
    assert scoring.score_hesitation(1) == 100.0
    assert scoring.score_hesitation(0) == 100.0
    assert scoring.score_hesitation(6) == 0.0  # 100 - 20*5
    assert scoring.score_hesitation(10) == 0.0  # clamp
    assert scoring.score_hesitation(None) is None


def test_score_filler_boundaries():
    assert scoring.score_filler(2) == 100.0
    assert scoring.score_filler(0) == 100.0  # clamp trên
    assert scoring.score_filler(10) == 0.0
    assert scoring.score_filler(15) == 0.0  # clamp dưới
    assert scoring.score_filler(None) is None


def test_speech_span_basic():
    # 3 từ thật: start đầu = 1.0, end cuối = 3.5 -> span 2.5
    words = [_w("a", 1.0, 1.5), _w("b", 2.0, 2.5), _w("c", 3.0, 3.5)]
    assert scoring.speech_span(words) == (3, pytest.approx(2.5))


def test_speech_span_ignores_filler_at_edges_and_middle():
    base = [_w("a", 1.0, 1.5), _w("b", 2.0, 2.5), _w("c", 3.0, 3.5)]
    with_um = [
        _w("um", 0.0, 0.5),  # đầu, ngoài khoảng từ thật
        base[0],
        _w("Um,", 1.6, 1.9),  # giữa (có hoa/dấu câu: is_filler dùng make_raw_key)
        base[1],
        base[2],
        _w("uh", 4.0, 4.5),  # cuối
    ]
    assert scoring.speech_span(with_um) == scoring.speech_span(base)
    assert scoring.speech_span(with_um) == (3, pytest.approx(2.5))


def test_speech_span_under_two_words_is_none():
    assert scoring.speech_span([]) == (0, None)
    assert scoring.speech_span([_w("hi", 0.0, 0.5)]) == (1, None)
    # 2 từ nhưng một là filler -> 1 từ thật
    assert scoring.speech_span([_w("hi", 0.0, 0.5), _w("um", 1.0, 1.5)]) == (1, None)


def test_speech_span_nonpositive_span_is_none():
    # 2 từ thật nhưng end cuối <= start đầu (dữ liệu lỗi) -> span None
    assert scoring.speech_span([_w("a", 1.0, 1.2), _w("b", 0.5, 1.0)]) == (2, None)


def test_compute_wpm():
    assert scoring.compute_wpm(150, 60.0) == pytest.approx(150.0)
    assert scoring.compute_wpm(20, 10.0) == pytest.approx(120.0)  # 20 / (10/60)
    assert scoring.compute_wpm(1, None) is None


def test_hesitations_per_min_counts_forgot_word_and_ignores_others():
    # span 60 s: 2 hesitation + 1 forgot_word -> count 3, forgot 1, H = 3 (D3, D17)
    cps = [
        _cp(PauseKind.HESITATION),
        _cp(PauseKind.HESITATION),
        _cp(PauseKind.FORGOT_WORD),
        _cp(PauseKind.PUNCTUATION),
        _cp(PauseKind.NATURAL),
    ]
    n_h, n_fw, h = scoring.hesitations_per_min(cps, 60.0)
    assert (n_h, n_fw) == (3, 1)
    assert h == pytest.approx(3.0)


def test_hesitations_per_min_uses_span_not_file_duration():
    # Cùng 3 lần, span 30 s -> H = 6 (không phụ thuộc thời lượng file)
    cps = [_cp(PauseKind.HESITATION)] * 3
    assert scoring.hesitations_per_min(cps, 30.0)[2] == pytest.approx(6.0)


def test_hesitations_per_min_span_none():
    cps = [_cp(PauseKind.HESITATION)]
    assert scoring.hesitations_per_min(cps, None) == (1, 0, None)


@pytest.mark.parametrize("span", [0.0, -1.0])
def test_nonpositive_span_gives_none(span):
    assert scoring.compute_wpm(5, span) is None
    # số đếm vẫn trả, chỉ H là None
    assert scoring.hesitations_per_min([_cp(PauseKind.FORGOT_WORD)], span) == (1, 1, None)


def test_under_two_words_none_propagates():
    n, span = scoring.speech_span([_w("hi", 0.0, 0.5)])
    wpm = scoring.compute_wpm(n, span)
    _, _, h = scoring.hesitations_per_min([], span)
    assert wpm is None and h is None
    f_wpm = scoring.score_wpm(wpm)
    f_pause = scoring.score_hesitation(h)
    assert f_wpm is None and f_pause is None
    assert scoring.compute_fluency(f_wpm, f_pause, 100.0) is None


@pytest.mark.parametrize("idx", [0, 1, 2])
def test_compute_fluency_none_in_any_position(idx):
    parts = [90.0, 90.0, 90.0]
    parts[idx] = None
    assert scoring.compute_fluency(*parts) is None


def test_compute_fluency_zero_is_not_none():
    assert scoring.compute_fluency(0.0, 0.0, 0.0) == 0.0


def test_count_fillers_vad_segment_without_words():
    words = [_w("hello", 0.0, 1.0), _w("world", 4.0, 5.0)]
    segs = [SpeechSegment(0.0, 1.0), SpeechSegment(6.0, 6.5)]
    # đoạn (0,1) trùng "hello"; đoạn (6,6.5) không trùng từ nào -> n_vad = 1
    assert scoring.count_fillers(words, segs) == (0, 1)


def test_count_fillers_segment_on_stt_filler_not_double_counted():
    words = [_w("hello", 0.0, 1.0), _w("um", 2.0, 2.5)]
    segs = [SpeechSegment(1.9, 2.6)]
    assert scoring.count_fillers(words, segs) == (1, 0)


def test_count_fillers_segment_on_real_word_not_counted():
    words = [_w("hello", 0.0, 1.0), _w("world", 1.5, 2.5)]
    # đoạn dài phủ cả hai từ thật -> không đếm
    assert scoring.count_fillers(words, [SpeechSegment(0.0, 3.0)]) == (0, 0)


def test_count_fillers_touching_boundary_is_not_overlap():
    # đoạn bắt đầu đúng lúc từ kết thúc: bất đẳng thức chặt -> không chồng lấn -> đếm
    words = [_w("hello", 0.0, 1.0)]
    assert scoring.count_fillers(words, [SpeechSegment(1.0, 1.5)]) == (0, 1)


def test_count_fillers_each_segment_counted_once():
    # 2 đoạn rời nhau, không từ nào -> 2 (mỗi đoạn một lần)
    segs = [SpeechSegment(0.0, 0.5), SpeechSegment(1.0, 1.5)]
    assert scoring.count_fillers([], segs) == (0, 2)


def test_find_fillers_lists_stt_and_vad_sorted_by_time():
    words = [_w("hello", 0.0, 1.0), _w("Um", 2.0, 2.5)]
    segs = [SpeechSegment(0.0, 1.0), SpeechSegment(1.9, 2.6), SpeechSegment(6.0, 6.5)]
    events = scoring.find_fillers(words, segs)
    assert [(e.source, e.text, e.start_s, e.end_s) for e in events] == [
        ("stt", "Um", 2.0, 2.5),
        ("vad", None, 6.0, 6.5),
    ]


def test_filler_pct_shared_r_s12():
    # 3 filler / 100 từ -> R = 3 -> điểm 87.5 (cùng một R cho hiển thị và chấm, D5)
    r = scoring.filler_pct(3, 100)
    assert r == pytest.approx(3.0)
    assert scoring.score_filler(r) == pytest.approx(87.5)


def test_filler_pct_zero_words_is_none():
    assert scoring.filler_pct(0, 0) is None
    assert scoring.filler_pct(2, 0) is None


def test_you_know_and_like_are_not_fillers():
    from src.audio_processing.text_norm import is_filler

    assert not is_filler("like")
    assert not is_filler("you know")
    assert not is_filler("basically")
    assert not is_filler("literally")
    # và speech_span coi chúng là từ thật
    words = [_w("like", 0.0, 0.5), _w("basically", 1.0, 1.5)]
    assert scoring.speech_span(words) == (2, pytest.approx(1.5))


# ---------------------------------------------------------------------------
# Mục 3.10: S theo alignment (ADR-004 D8, phase3 #1/#2/#3). Số tính tay, không phải số đo.
# Test không tải model: luôn truyền encode giả.
# ---------------------------------------------------------------------------
import numpy as np  # noqa: E402


def _words(*tokens: str) -> list[WordTimestamp]:
    return [WordTimestamp(t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(tokens)]


def _no_pron(_w: str) -> list[list[str]]:
    return []


def _table_encoder(table: dict[str, list[float]]):
    def encode(texts):
        return np.array([table[t] for t in texts], dtype=float)

    return encode


def _forbidden_encoder(_texts):
    raise AssertionError("encode không được gọi")


def _cos_case(c: float):
    """Cặp vector 2 chiều có cosine đúng bằng c (tính tay)."""
    return {"R": [1.0, 0.0], "H": [c, math.sqrt(1 - c * c)]}


@pytest.mark.parametrize(
    ("c", "expected"), [(0.82, True), (0.81, False), (0.83, True)]
)
def test_score_sentences_cosine_threshold_boundary(c, expected):
    enc = _table_encoder(_cos_case(c))
    res = scoring.score_sentences([(0, 0, 2, "R", "H")], encode=enc)
    assert res[0].cosine == pytest.approx(c, abs=1e-6)
    assert res[0].passed is expected


def test_score_semantic_18_of_20_is_90():
    sentences = [
        scoring.SentenceResult(i, f"r{i}", i, i + 1, f"h{i}", 0.9, i < 18)
        for i in range(20)
    ]
    assert scoring.score_semantic(sentences) == pytest.approx(90.0)


def test_score_semantic_empty_is_none():
    assert scoring.score_semantic([]) is None


def test_build_pairs_two_sentences_full_hyp():
    script = "Hello world. How are you?"
    res = align(script, _words("hello", "world", "how", "are", "you"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs == [
        (0, 0, 2, "Hello world.", "hello world"),
        (1, 2, 5, "How are you?", "how are you"),
    ]


def test_build_pairs_ins_goes_to_preceding_sentence():
    script = "Hello world. How are you?"
    # "well" chen sau "world" (cuối câu 1) -> thuộc câu 1 (phase3 #2)
    res = align(script, _words("hello", "world", "well", "how", "are", "you"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs[0][4] == "hello world well"
    assert pairs[1][4] == "how are you"


def test_build_pairs_all_deleted_sentence_is_none_and_counts_in_denominator():
    script = "Hello world. How are you?"
    res = align(script, _words("hello", "world"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs[1][4] is None
    enc = _table_encoder({"Hello world.": [1.0, 0.0], "hello world": [1.0, 0.0],
                          "How are you?": [0.0, 1.0]})
    sents = scoring.score_sentences(pairs, encode=enc)
    assert sents[0].passed is True
    assert sents[1].hyp_text is None
    assert sents[1].cosine is None
    assert sents[1].passed is False
    assert scoring.score_semantic(sents) == pytest.approx(50.0)  # 1/2


def test_build_pairs_shared_hyp_word_not_duplicated():
    # "it's" của STT bung thành "it is" khớp hai ref -> hyp_word "it's" chỉ xuất hiện một lần
    script = "It is fine."
    res = align(script, _words("it's", "fine"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs[0][4] == "it's fine"


def test_empty_script_gives_none():
    pairs = scoring.build_sentence_pairs("", [])
    assert pairs == []
    sents = scoring.score_sentences(pairs, encode=_forbidden_encoder)
    assert scoring.score_semantic(sents) is None


def test_no_hyp_does_not_call_encode():
    pairs = [(0, 0, 2, "Hello world.", None), (1, 2, 4, "Bye now.", None)]
    sents = scoring.score_sentences(pairs, encode=_forbidden_encoder)
    assert [s.passed for s in sents] == [False, False]
    assert scoring.score_semantic(sents) == 0.0


def test_injected_encode_never_loads_default_encoder(monkeypatch):
    def boom():
        raise AssertionError("_get_encoder không được gọi")

    monkeypatch.setattr(scoring, "_get_encoder", boom)
    enc = _table_encoder(_cos_case(0.9))
    res = scoring.score_sentences([(0, 0, 2, "R", "H")], encode=enc)
    assert res[0].passed is True


def test_zero_norm_vector_gives_none_cosine():
    enc = _table_encoder({"R": [0.0, 0.0], "H": [1.0, 0.0]})
    res = scoring.score_sentences([(0, 0, 2, "R", "H")], encode=enc)
    assert res[0].cosine is None
    assert res[0].passed is False


# ---------------------------------------------------------------------------
# Review 3.10: cosine thô (ADR-004 D1) và ghim hành vi alignment -> câu.
# ---------------------------------------------------------------------------
def test_cosine_raw_not_rounded_below_threshold():
    c = 0.8199996  # round(c, 6) = 0.82 sẽ sai thành passed
    res = scoring.score_sentences([(0, 0, 2, "R", "H")], encode=_table_encoder(_cos_case(c)))
    assert res[0].cosine == pytest.approx(c, abs=1e-12)
    assert res[0].passed is False


def test_cosine_exactly_threshold_passes():
    res = scoring.score_sentences([(0, 0, 2, "R", "H")], encode=_table_encoder(_cos_case(0.82)))
    assert res[0].passed is True


def test_cosine_within_epsilon_below_threshold_passes():
    c = 0.82 - 1e-12  # nằm trong epsilon 1e-9 (chỉ hấp thụ nhiễu float64)
    res = scoring.score_sentences([(0, 0, 2, "R", "H")], encode=_table_encoder(_cos_case(c)))
    assert res[0].passed is True


def test_known_limit_word_order_with_interleaved_ins():
    # Giới hạn đã biết, ảnh hưởng nhỏ tới cosine; muốn sửa thì AlignedItem cần lưu
    # danh sách hyp_index. Đúng ra phải là "a twenty x one b".
    script = "A 21 b."
    res = align(script, _words("a", "twenty", "x", "one", "b"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs[0][4] == "a twenty one x b"


def test_pairs_sentence_without_hyp_is_none_in_middle():
    script = "Hello world. How are you? Fine."
    res = align(script, _words("hello", "world", "fine"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert [p[4] for p in pairs] == ["hello world", None, "fine"]


def test_pairs_leading_ins_goes_to_first_sentence():
    script = "Hello world. Bye now."
    res = align(script, _words("well", "hello", "world", "bye", "now"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs[0][4] == "well hello world"
    assert pairs[1][4] == "bye now"


def test_pairs_punctuation_only_token_stays_in_sentence_span():
    script = "Really? ... Next one."
    res = align(script, _words("really", "next", "one"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert [(p[1], p[2], p[4]) for p in pairs] == [(0, 2, "really"), (2, 4, "next one")]


def test_pairs_expanded_hyp_word_shared_across_two_sentences():
    # Hệ quả chấp nhận của D8: "it's" bung thành "it is" dùng chung cho hai ref ở hai câu.
    script = "Say it. Is fine."
    res = align(script, _words("say", "it's", "fine"), pron=_no_pron)
    pairs = scoring.build_sentence_pairs(script, res.items)
    assert pairs[0][4] == "say it's"
    assert pairs[1][4] == "it's fine"


def test_all_sentences_without_hyp_gives_zero_not_none():
    script = "Hello world. Bye now."
    pairs = scoring.build_sentence_pairs(script, align(script, [], pron=_no_pron).items)
    assert [p[4] for p in pairs] == [None, None]
    sents = scoring.score_sentences(pairs, encode=_forbidden_encoder)
    assert scoring.score_semantic(sents) == 0.0
