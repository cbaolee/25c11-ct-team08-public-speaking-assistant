import pytest
from dataclasses import dataclass

from src.audio_processing.contracts import (
    Pause,
    SpeechSegment,
    WordTimestamp,
    PauseKind,
    InsufficientAudio
)
from src.audio_processing.alignment import AlignedItem, align
from src.audio_processing.vad import classify_pauses, check_audio_quality


# ==========================================
# TESTS CHO HÀM check_audio_quality
# ==========================================

def test_check_audio_quality_empty_segments_raises_insufficient_audio():
    with pytest.raises(InsufficientAudio, match="Speech < 30%"):
        check_audio_quality(segments=[], duration_s=10.0)

def test_check_audio_quality_below_30_percent_raises_insufficient_audio():
    # 2.5s tiếng nói trên tổng 10.0s (25%) -> Raise
    segments = [SpeechSegment(start_s=0.0, end_s=2.5)]
    with pytest.raises(InsufficientAudio, match="Speech < 30%"):
        check_audio_quality(segments=segments, duration_s=10.0)

def test_check_audio_quality_above_30_percent_passes():
    # 3.5s tiếng nói trên tổng 10.0s (35%) -> Pass
    segments = [SpeechSegment(start_s=0.0, end_s=3.5)]
    try:
        check_audio_quality(segments=segments, duration_s=10.0)
    except InsufficientAudio:
        pytest.fail("Unexpected InsufficientAudio raised for speech >= 30%")


# ==========================================
# TESTS CHO HÀM classify_pauses (ADR-004 D6, phase3 #2/#11/#12/#16/#21)
# ==========================================
# Mọi mốc thời gian dưới đây là số tự đặt cho test, KHÔNG phải số đo.


def _no_pron(word: str) -> list[list[str]]:
    # Stub CMU: không gọi từ điển thật; khớp chỉ theo chuỗi bằng nhau.
    return []


def _items(script: str, spoken: list[tuple[str, float, float]]) -> list[AlignedItem]:
    words = [WordTimestamp(word=w, start_s=a, end_s=b) for w, a, b in spoken]
    return align(script, words, pron=_no_pron).items


def _kind(script, spoken, pause, **kw):
    kw.setdefault("hesitation_threshold_s", 0.7)
    out = classify_pauses([pause], _items(script, spoken), script, **kw)
    assert len(out) == 1
    return out[0]


def test_empty_pauses_returns_empty():
    # Giữ ý nghĩa cũ; đổi cách gọi sang items (chữ ký mới).
    script = "Hello world"
    items = _items(script, [("hello", 0.0, 0.5)])
    assert classify_pauses([], items, script, hesitation_threshold_s=0.7) == []


def test_pause_at_period_is_punctuation():
    # Cũ: is_rhetorical (RHETORICAL -> PUNCTUATION theo D6).
    r = _kind("Hello world. How are you?", [("world", 0.5, 1.0)], Pause(1.0, 1.8))
    assert r.kind == PauseKind.PUNCTUATION
    assert r.after_ref_index == 1


def test_pause_at_comma_is_punctuation():
    r = _kind("Well, that is good.", [("well", 0.0, 0.5)], Pause(0.5, 1.1))
    assert r.kind == PauseKind.PUNCTUATION
    assert r.after_ref_index == 0


def test_long_pause_mid_sentence_is_forgot_word():
    r = _kind("Hello world and welcome.", [("world", 0.5, 1.0)], Pause(1.0, 2.5))
    assert r.kind == PauseKind.FORGOT_WORD


def test_pause_above_threshold_mid_sentence_is_hesitation():
    r = _kind("Hello world and welcome.", [("world", 0.5, 1.0)], Pause(1.0, 1.9))
    assert r.kind == PauseKind.HESITATION


def test_punctuation_pause_not_hesitation_even_if_long():
    # Cũ: rhetorical_not_counted_as_hesitation. Pause 2.5 s tại "." vẫn là punctuation (#11).
    r = _kind("Hello world. How are you?", [("world", 0.5, 1.0)], Pause(1.0, 3.5))
    assert r.kind == PauseKind.PUNCTUATION


def test_natural_pause_is_returned_not_dropped():
    r = _kind("Hello world and welcome.", [("world", 0.5, 1.0)], Pause(1.0, 1.5))
    assert r.kind == PauseKind.NATURAL


def test_word_with_and_without_punct_is_distinguished():
    # Lỗi 1.9.2 #26: "now" vừa có vừa không có dấu phẩy.
    script = "go now, go now please"
    spoken = [("go", 0.0, 0.3), ("now", 0.3, 0.6), ("go", 2.0, 2.3), ("now", 2.3, 2.6),
              ("please", 3.4, 3.8)]
    pauses = [Pause(0.6, 1.4), Pause(2.6, 3.4)]
    out = classify_pauses(pauses, _items(script, spoken), script, hesitation_threshold_s=0.7)
    assert [c.kind for c in out] == [PauseKind.PUNCTUATION, PauseKind.HESITATION]
    assert [c.after_ref_index for c in out] == [1, 3]


def test_boundary_hesitation_threshold_inclusive_exact():
    # 0.5 và 1.0 biểu diễn chính xác trong float nên biên đúng tuyệt đối.
    kw = dict(hesitation_threshold_s=0.5, forgot_word_s=1.0)
    sp = [("world", 0.0, 1.0)]
    s = "Hello world and welcome."
    assert _kind(s, sp, Pause(1.0, 1.5), **kw).kind == PauseKind.HESITATION
    assert _kind(s, sp, Pause(1.0, 1.4999), **kw).kind == PauseKind.NATURAL
    assert _kind(s, sp, Pause(1.0, 2.0), **kw).kind == PauseKind.FORGOT_WORD
    assert _kind(s, sp, Pause(1.0, 1.9999), **kw).kind == PauseKind.HESITATION


def test_boundary_default_values_0_7_and_1_2():
    s = "Hello world and welcome."
    sp = [("world", 0.0, 1.0)]
    assert _kind(s, sp, Pause(1.0, 1.7)).kind == PauseKind.HESITATION   # đúng 0.7
    assert _kind(s, sp, Pause(1.0, 1.69)).kind == PauseKind.NATURAL     # 0.69
    assert _kind(s, sp, Pause(1.0, 2.2)).kind == PauseKind.FORGOT_WORD  # đúng 1.2


def test_exactly_1_2s_at_comma_is_punctuation():
    r = _kind("Well, that is good.", [("well", 0.0, 1.0)], Pause(1.0, 2.2))
    assert r.kind == PauseKind.PUNCTUATION


def test_word_before_pause_is_ins_uses_previous_ref():
    # Script "a, b c": nói "a x b" (x là ins, không có ref_index). Pause sau x:
    # after_ref_index = ref phía trước (a = 0), dấu phẩy của "a," -> punctuation (phase3 #2).
    script = "a, b c"
    items = _items(script, [("a", 0.0, 0.5), ("x", 0.5, 1.0), ("b", 2.0, 2.5)])
    ins = [i for i in items if i.status == "ins"]
    assert len(ins) == 1 and ins[0].ref_index is None
    out = classify_pauses([Pause(1.0, 1.9)], items, script, hesitation_threshold_s=0.7)
    assert out[0].after_ref_index == 0
    assert out[0].kind == PauseKind.PUNCTUATION


def test_ins_after_unpunctuated_ref_is_not_punctuation():
    script = "a b, c"
    items = _items(script, [("a", 0.0, 0.5), ("x", 0.5, 1.0), ("b", 2.0, 2.5)])
    out = classify_pauses([Pause(1.0, 1.9)], items, script, hesitation_threshold_s=0.7)
    assert out[0].after_ref_index == 0
    assert out[0].kind == PauseKind.HESITATION


def test_pause_before_any_word_has_none_ref_index():
    script = "hello world"
    items = _items(script, [("hello", 1.0, 1.5)])
    out = classify_pauses([Pause(0.0, 0.8)], items, script, hesitation_threshold_s=0.7)
    assert out[0].after_ref_index is None
    assert out[0].kind == PauseKind.HESITATION


def test_del_item_is_never_chosen_as_preceding_word():
    # "b," bị bỏ (del, không có thời gian). Từ nghe được ngay trước pause là "a" (không dấu).
    script = "a b, c"
    items = _items(script, [("a", 0.0, 0.5), ("c", 0.6, 1.0)])
    assert any(i.status == "del" for i in items)
    out = classify_pauses([Pause(0.5, 0.6)], items, script, hesitation_threshold_s=0.7)
    assert out[0].after_ref_index == 0
    assert out[0].kind == PauseKind.NATURAL


def test_all_pauses_returned_in_input_order():
    script = "Hello world. How are you today"
    spoken = [("hello", 0.0, 0.4), ("world", 0.4, 0.8), ("how", 2.0, 2.3),
              ("are", 2.3, 2.6), ("you", 3.2, 3.5), ("today", 3.5, 3.9)]
    pauses = [Pause(0.8, 2.0), Pause(2.6, 3.2), Pause(0.4, 0.45), Pause(3.5, 5.0)]
    out = classify_pauses(pauses, _items(script, spoken), script, hesitation_threshold_s=0.7)
    assert [c.pause for c in out] == pauses


# ==========================================
# Lỗi float ở biên 0.7 s / 1.2 s (review 3.8, lỗi 1)
# ==========================================

def test_float_boundary_0_68_to_1_38_is_hesitation():
    # 1.38 - 0.68 = 0.6999999999999998 trong float nhưng danh nghĩa là 0.7.
    s = "Hello world and welcome."
    assert _kind(s, [("world", 0.0, 0.68)], Pause(0.68, 1.38)).kind == PauseKind.HESITATION


def test_float_boundary_0_68_to_1_88_is_forgot_word():
    # 1.88 - 0.68 = 1.1999999999999997 trong float nhưng danh nghĩa là 1.2.
    s = "Hello world and welcome."
    assert _kind(s, [("world", 0.0, 0.68)], Pause(0.68, 1.88)).kind == PauseKind.FORGOT_WORD


def test_float_boundary_sweep_no_misclassification():
    from decimal import Decimal

    s = "Hello world and welcome."
    wrong = []
    for i in range(0, 1001):
        start = Decimal(i) / Decimal(100)
        for nominal, expected in ((Decimal("0.7"), PauseKind.HESITATION),
                                  (Decimal("1.2"), PauseKind.FORGOT_WORD)):
            p = Pause(float(start), float(start + nominal))
            items = _items(s, [("world", 0.0, float(start))]) if start > 0 else _items(s, [])
            out = classify_pauses([p], items, s, hesitation_threshold_s=0.7)
            if out[0].kind != expected:
                wrong.append((float(start), float(nominal), out[0].kind))
    assert wrong == []


# ==========================================
# Token chỉ có dấu câu chặn ins tìm ref (review 3.8, lỗi 2)
# ==========================================

def _item(status, ref_index, hyp_index, ref_word, hyp_word, start_s, end_s):
    return AlignedItem(status=status, ref_index=ref_index, hyp_index=hyp_index,
                       ref_word=ref_word, hyp_word=hyp_word, start_s=start_s,
                       end_s=end_s, sentence_index=0)


def test_ins_after_punct_only_token_skips_to_real_ref():
    script = "a, — b"
    items = [
        _item("equal", 0, 0, "a,", "a", 0.0, 0.5),
        _item("equal", 1, None, "—", None, None, None),
        _item("ins", None, 1, None, "x", 0.5, 1.0),
    ]
    out = classify_pauses([Pause(1.0, 1.3)], items, script, hesitation_threshold_s=0.7)
    assert out[0].after_ref_index == 0
    assert out[0].kind == PauseKind.PUNCTUATION


def test_ins_after_del_uses_del_ref_index():
    # Ghim hành vi hiện tại (phase3 #2): del có từ thật nên vẫn được chọn.
    script = "a b, c"
    items = [
        _item("equal", 0, 0, "a", "a", 0.0, 0.5),
        _item("del", 1, None, "b,", None, None, None),
        _item("ins", None, 1, None, "x", 0.5, 1.0),
    ]
    out = classify_pauses([Pause(1.0, 1.3)], items, script, hesitation_threshold_s=0.7)
    assert out[0].after_ref_index == 1
    assert out[0].kind == PauseKind.PUNCTUATION


# ==========================================
# Dung sai đồng bộ VAD/STT (WORD_PAUSE_TOLERANCE_S = 0.1)
# ==========================================

def test_stt_end_slightly_after_pause_start_still_counts_as_preceding_word():
    # "world" kết thúc 1.00 nhưng VAD báo pause bắt đầu 0.97 (lệch 0.03 s, trong dung sai).
    r = _kind("Hello world. How are you", [("hello", 0.0, 0.4), ("world", 0.5, 1.0)],
              Pause(0.97, 1.8))
    assert r.kind == PauseKind.PUNCTUATION
    assert r.after_ref_index == 1


def test_stt_end_beyond_tolerance_falls_back_to_previous_word():
    # Pause bắt đầu 0.85, "world" end 1.00 (lệch 0.15 s > 0.1): "world" bị loại,
    # từ trước pause là "hello" (không dấu câu) -> HESITATION, after_ref_index == 0.
    r = _kind("Hello world. How are you", [("hello", 0.0, 0.4), ("world", 0.5, 1.0)],
              Pause(0.85, 1.8))
    assert r.after_ref_index == 0
    assert r.kind == PauseKind.HESITATION
