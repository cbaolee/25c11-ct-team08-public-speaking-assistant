"""Test phonetic.py (ADR-005 P1, P2, P3, P7, P11).

Mọi con số kỳ vọng là SỐ TÍNH TAY theo ADR-005 (mục "Ví dụ tính tay"), KHÔNG phải số đo.
Stub phoneme lấy từ mục "Thông tin gói đã kiểm chứng" (có stress digit để test việc bỏ stress).
"""

import pytest

from src.audio_processing.phonetic import (
    PhoneticMatch,
    classify_pair,
    classify_sim,
    lev,
    phonetic_sim,
    pronunciations,
)

# 20 phoneme cho test biên: 12/20 hay 13/20 được tạo bằng cách thay k phoneme đầu bằng "Y".
_BASE20 = [
    "P", "R", "OW1", "N", "AH0", "S", "IY0", "EY1", "SH", "AH0",
    "N", "T", "K", "L", "M", "F", "V", "Z", "ZH", "W",
]


def _mutate(base: list[str], k: int) -> list[str]:
    """Thay k phoneme đầu bằng 'Y' (không phoneme nào trong _BASE20 là 'Y') -> Lev = k."""
    return ["Y"] * k + base[k:]


STUB: dict[str, list[list[str]]] = {
    "think": [["TH", "IH1", "NG", "K"]],
    "sink": [["S", "IH1", "NG", "K"]],
    "their": [["DH", "EH1", "R"]],
    "there": [["DH", "EH1", "R"]],
    "ship": [["SH", "IH1", "P"]],
    "sheep": [["SH", "IY1", "P"]],
    "a": [["AH0"], ["EY1"]],
    "the": [["DH", "AH0"], ["DH", "AH1"], ["DH", "IY0"]],
    "dh_ah0": [["DH", "AH0"]],
    "dh_ah1": [["DH", "AH1"]],
    # 12 phoneme, lệch 1 (minh hoạ "pronunciation sai 1 phoneme").
    "pron12a": [["P", "R", "OW0", "N", "AH2", "N", "S", "IY0", "EY1", "SH", "AH0", "N"]],
    "pron12b": [["P", "R", "OW0", "N", "AH2", "N", "S", "IY0", "EY1", "SH", "AH0", "M"]],
    "long20": [_BASE20],
    "long20_d7": [_mutate(_BASE20, 7)],
    "long20_d8": [_mutate(_BASE20, 8)],
    "ten10": [_BASE20[:10]],
    "ten10_d1": [_mutate(_BASE20[:10], 1)],
    "ah_only": [["AH0"]],
    # Test nhân chéo: ref có 2 biến thể (A: 2 phoneme, B: 6 phoneme), hyp cũng 2 biến thể.
    "xref": [["P", "R"], ["B", "D", "G", "K", "L", "M"]],
    "xhyp": [["P", "Z"], ["B", "D", "G", "K", "S", "T"]],
}


def stub_pron(word: str) -> list[list[str]]:
    return STUB.get(word, [])


# ---------- lev ----------

def test_lev_phonemes_basic():
    # TH IH NG K vs S IH NG K: thay 1 phoneme -> 1.
    assert lev(["TH", "IH", "NG", "K"], ["S", "IH", "NG", "K"]) == 1
    # giống nhau -> 0.
    assert lev(["DH", "EH", "R"], ["DH", "EH", "R"]) == 0
    # kitten/sitting kiểu kinh điển: k->s, e->i, thêm g = 3.
    assert lev(list("kitten"), list("sitting")) == 3


def test_lev_phonemes_empty():
    assert lev([], ["A", "B", "C"]) == 3
    assert lev(["A", "B", "C"], []) == 3
    assert lev([], []) == 0


# ---------- phonetic_sim ----------

def test_sim_strips_stress():
    # DH AH0 vs DH AH1: sau khi bỏ stress giống hệt -> 1.0.
    assert phonetic_sim("dh_ah0", "dh_ah1", pron=stub_pron) == pytest.approx(1.0)


def test_sim_max_over_pronunciations():
    # a: [AH],[EY]; the: [DH AH],[DH AH],[DH IY] (sau bỏ stress).
    # (AH, DH AH): Lev 1 / max 2 -> 0.5. (EY, DH *): Lev 2 / 2 -> 0. Max = 0.5.
    assert phonetic_sim("a", "the", pron=stub_pron) == pytest.approx(0.5)


def test_sim_oov_is_none():
    assert phonetic_sim("covid", "think", pron=stub_pron) is None
    assert phonetic_sim("think", "covid", pron=stub_pron) is None


# ---------- classify_pair: bảng P2 ----------

def test_homophone_equal():
    # their/there: DH EH R == DH EH R, sim 1.0, chuỗi chuẩn hoá khác nhau.
    m = classify_pair("their", "there", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=True, oov=False)


def test_near_miss_think_sink():
    # Lev 1 / max 4 -> sim 0.75 -> near_miss.
    m = classify_pair("think", "sink", pron=stub_pron)
    assert m == PhoneticMatch(status="near_miss", homophone=False, oov=False)
    assert phonetic_sim("think", "sink", pron=stub_pron) == pytest.approx(0.75)


def test_near_miss_lower_bound():
    # ship/sheep: SH IH P vs SH IY P -> Lev 1 / 3 -> sim 2/3 ~ 0.667 (>= 0.65) -> near_miss.
    m = classify_pair("ship", "sheep", pron=stub_pron)
    assert m.status == "near_miss"
    assert phonetic_sim("ship", "sheep", pron=stub_pron) == pytest.approx(2 / 3)


def test_sub_below_065():
    # a/the: sim 0.5 < 0.65 -> sub.
    m = classify_pair("a", "the", pron=stub_pron)
    assert m == PhoneticMatch(status="sub", homophone=False, oov=False)


def test_gap_090_100_is_equal():
    # 12 phoneme lệch 1: sim = 11/12 ~ 0.917 thuộc (0.90, 1.0) -> equal, KHÔNG homophone (P11).
    m = classify_pair("pron12a", "pron12b", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=False, oov=False)
    assert phonetic_sim("pron12a", "pron12b", pron=stub_pron) == pytest.approx(11 / 12)


def test_boundary_065_is_near_miss():
    # 20 phoneme lệch 7: sim = 13/20 = 0.65 đúng biên -> near_miss (biên dưới đóng).
    assert classify_sim(7, 20) == ("near_miss", False)
    m = classify_pair("long20", "long20_d7", pron=stub_pron)
    assert m.status == "near_miss"


def test_just_below_065_is_sub():
    # 20 phoneme lệch 8: sim = 12/20 = 0.60 < 0.65 -> sub.
    assert classify_sim(8, 20) == ("sub", False)
    m = classify_pair("long20", "long20_d8", pron=stub_pron)
    assert m.status == "sub"


def test_boundary_090_is_near_miss():
    # 10 phoneme lệch 1: sim = 9/10 = 0.90 đúng biên -> near_miss (biên trên đóng).
    # Chỉ sim trong (0.90, 1.0) mới là equal.
    assert classify_sim(1, 10) == ("near_miss", False)
    m = classify_pair("ten10", "ten10_d1", pron=stub_pron)
    assert m.status == "near_miss"


def test_classify_sim_table():
    assert classify_sim(0, 3) == ("equal", True)  # sim 1.0
    assert classify_sim(1, 12) == ("equal", False)  # 11/12 trong (0.90, 1.0)
    assert classify_sim(1, 3) == ("near_miss", False)  # 2/3


# ---------- P11, P3 ----------

def test_same_string_not_homophone():
    # ref == hyp (chuỗi) -> equal nhưng homophone=False (P11), dù phoneme trùng.
    m = classify_pair("their", "their", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=False, oov=False)


def test_oov_exact_equal():
    m = classify_pair("covid", "covid", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=False, oov=True)


def test_oov_mismatch_sub():
    # covid/kovid: chuỗi gần nhau nhưng OOV -> sub, KHÔNG near_miss (P3).
    m = classify_pair("covid", "kovid", pron=stub_pron)
    assert m == PhoneticMatch(status="sub", homophone=False, oov=True)


def test_oov_one_side_only_is_sub():
    # chỉ một bên OOV cũng là oov=True, chuỗi khác -> sub.
    m = classify_pair("think", "covid", pron=stub_pron)
    assert m == PhoneticMatch(status="sub", homophone=False, oov=True)


# ---------- Tích hợp cmudict thật (không stub) ----------

def test_cmudict_think_sink():
    # CMU thật: think TH IH1 NG K, sink S IH1 NG K -> 0.75 -> near_miss.
    m = classify_pair("think", "sink")
    assert m.status == "near_miss"
    assert m.oov is False


def test_cmudict_their_there():
    m = classify_pair("their", "there")
    assert m.status == "equal"
    assert m.homophone is True


# ---------- Bổ sung sau review (số kỳ vọng là số tính tay, KHÔNG phải số đo) ----------

def test_apostrophe_lookup():
    # ADR-005 "Thông tin gói": john's -> JH AA1 N Z; bỏ stress -> JH AA N Z.
    prons = pronunciations("john's")
    assert prons != []
    assert [p[:-1] if p[-1] in "012" else p for p in prons[0]] == ["JH", "AA", "N", "Z"]


def test_short_word_never_near_miss():
    # ADR-005 không định nghĩa "short word"; ở đây hiểu là <= 2 phoneme, nhóm duy nhất
    # về toán học không thể rơi vào [0.65, 0.90]: sim = (L-d)/L với L<=2 chỉ là 0, 0.5, 1.
    for max_len in (1, 2):
        for dist in range(max_len + 1):
            assert classify_sim(dist, max_len)[0] != "near_miss"
    # Ca stub: AH vs DH AH -> Lev 1 / max 2 = 0.5 -> sub.
    assert classify_pair("ah_only", "dh_ah0", pron=stub_pron).status == "sub"


def test_pronunciations_returns_copy():
    first = pronunciations("their")
    expected = [list(p) for p in first]
    first[0].append("XX")
    first.append(["YY"])
    assert pronunciations("their") == expected


def test_pronunciations_oov_empty():
    assert pronunciations("covid") == []


def test_pronunciations_case_sensitive():
    # Hợp đồng: đầu vào phải được text_norm chuẩn hoá (lowercase) trước khi tra.
    assert pronunciations("The") == []
    assert pronunciations("the") != []


def test_best_pair_cross_multiplication():
    # ref: A = P R (2), B = B D G K L M (6). hyp: hA = P Z (2), hB = B D G K S T (6).
    # (A, hA): dist 1, L 2 -> sim 1/2. (B, hB): dist 2, L 6 -> sim 4/6.
    # Cặp chéo không chung phoneme nào -> dist = L -> sim 0.
    # Biến thể dist NHỎ nhất (1) có sim THẤP hơn (0.5 < 0.667); chọn theo dist sẽ ra
    # classify_sim(1, 2) = sub (sai). Chọn đúng theo sim (nhân chéo): near_miss.
    # Kiểm nhân chéo: (6-2)*2 = 8 > (2-1)*6 = 6.
    assert classify_pair("xref", "xhyp", pron=stub_pron).status == "near_miss"
    assert phonetic_sim("xref", "xhyp", pron=stub_pron) == pytest.approx(2 / 3)
