"""Test phonetic.py (ADR-005 P1, P2, P3, P7, P11).

Every expected number is HAND-COMPUTED per ADR-005 ("Hand-computed examples"), NOT measured.
Phoneme stubs come from the "Verified package info" section
(with stress digits to test stress removal).
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

# 20 phonemes for boundary tests: 12/20 or 13/20 is made by replacing the first k phonemes with "Y".
_BASE20 = [
    "P",
    "R",
    "OW1",
    "N",
    "AH0",
    "S",
    "IY0",
    "EY1",
    "SH",
    "AH0",
    "N",
    "T",
    "K",
    "L",
    "M",
    "F",
    "V",
    "Z",
    "ZH",
    "W",
]


def _mutate(base: list[str], k: int) -> list[str]:
    """Replace the first k phonemes with 'Y' (no phoneme in _BASE20 is 'Y') -> Lev = k."""
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
    # 12 phonemes, 1 off (illustrates "pronunciation wrong by 1 phoneme").
    "pron12a": [["P", "R", "OW0", "N", "AH2", "N", "S", "IY0", "EY1", "SH", "AH0", "N"]],
    "pron12b": [["P", "R", "OW0", "N", "AH2", "N", "S", "IY0", "EY1", "SH", "AH0", "M"]],
    "long20": [_BASE20],
    "long20_d7": [_mutate(_BASE20, 7)],
    "long20_d8": [_mutate(_BASE20, 8)],
    "ten10": [_BASE20[:10]],
    "ten10_d1": [_mutate(_BASE20[:10], 1)],
    "ah_only": [["AH0"]],
    # Cross-multiply test: ref has 2 variants (A: 2 phonemes, B: 6 phonemes), hyp has 2 too.
    "xref": [["P", "R"], ["B", "D", "G", "K", "L", "M"]],
    "xhyp": [["P", "Z"], ["B", "D", "G", "K", "S", "T"]],
}


def stub_pron(word: str) -> list[list[str]]:
    return STUB.get(word, [])


# ---------- lev ----------


def test_lev_phonemes_basic():
    # TH IH NG K vs S IH NG K: thay 1 phoneme -> 1.
    assert lev(["TH", "IH", "NG", "K"], ["S", "IH", "NG", "K"]) == 1
    # identical -> 0.
    assert lev(["DH", "EH", "R"], ["DH", "EH", "R"]) == 0
    # classic kitten/sitting: k->s, e->i, add g = 3.
    assert lev(list("kitten"), list("sitting")) == 3


def test_lev_phonemes_empty():
    assert lev([], ["A", "B", "C"]) == 3
    assert lev(["A", "B", "C"], []) == 3
    assert lev([], []) == 0


# ---------- phonetic_sim ----------


def test_sim_strips_stress():
    # DH AH0 vs DH AH1: identical after stress removal -> 1.0.
    assert phonetic_sim("dh_ah0", "dh_ah1", pron=stub_pron) == pytest.approx(1.0)


def test_sim_max_over_pronunciations():
    # a: [AH],[EY]; the: [DH AH],[DH AH],[DH IY] (after stress removal).
    # (AH, DH AH): Lev 1 / max 2 -> 0.5. (EY, DH *): Lev 2 / 2 -> 0. Max = 0.5.
    assert phonetic_sim("a", "the", pron=stub_pron) == pytest.approx(0.5)


def test_sim_oov_is_none():
    assert phonetic_sim("covid", "think", pron=stub_pron) is None
    assert phonetic_sim("think", "covid", pron=stub_pron) is None


# ---------- classify_pair: table P2 ----------


def test_homophone_equal():
    # their/there: DH EH R == DH EH R, sim 1.0, normalized strings differ.
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
    # 12 phonemes 1 off: sim = 11/12 ~ 0.917 in (0.90, 1.0) -> equal, NOT homophone (P11).
    m = classify_pair("pron12a", "pron12b", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=False, oov=False)
    assert phonetic_sim("pron12a", "pron12b", pron=stub_pron) == pytest.approx(11 / 12)


def test_boundary_065_is_near_miss():
    # 20 phonemes 7 off: sim = 13/20 = 0.65 exactly at boundary -> near_miss (lower bound closed).
    assert classify_sim(7, 20) == ("near_miss", False)
    m = classify_pair("long20", "long20_d7", pron=stub_pron)
    assert m.status == "near_miss"


def test_just_below_065_is_sub():
    # 20 phonemes 8 off: sim = 12/20 = 0.60 < 0.65 -> sub.
    assert classify_sim(8, 20) == ("sub", False)
    m = classify_pair("long20", "long20_d8", pron=stub_pron)
    assert m.status == "sub"


def test_boundary_090_is_near_miss():
    # 10 phonemes 1 off: sim = 9/10 = 0.90 exactly at boundary -> near_miss (upper bound closed).
    # Only sim in (0.90, 1.0) is equal.
    assert classify_sim(1, 10) == ("near_miss", False)
    m = classify_pair("ten10", "ten10_d1", pron=stub_pron)
    assert m.status == "near_miss"


def test_classify_sim_table():
    assert classify_sim(0, 3) == ("equal", True)  # sim 1.0
    assert classify_sim(1, 12) == ("equal", False)  # 11/12 trong (0.90, 1.0)
    assert classify_sim(1, 3) == ("near_miss", False)  # 2/3


# ---------- P11, P3 ----------


def test_same_string_not_homophone():
    # ref == hyp (string) -> equal but homophone=False (P11), even though phonemes match.
    m = classify_pair("their", "their", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=False, oov=False)


def test_oov_exact_equal():
    m = classify_pair("covid", "covid", pron=stub_pron)
    assert m == PhoneticMatch(status="equal", homophone=False, oov=True)


def test_oov_mismatch_sub():
    # covid/kovid: strings are close but OOV -> sub, NOT near_miss (P3).
    m = classify_pair("covid", "kovid", pron=stub_pron)
    assert m == PhoneticMatch(status="sub", homophone=False, oov=True)


def test_oov_one_side_only_is_sub():
    # only one side OOV is also oov=True, different strings -> sub.
    m = classify_pair("think", "covid", pron=stub_pron)
    assert m == PhoneticMatch(status="sub", homophone=False, oov=True)


# ---------- Real cmudict integration (no stub) ----------


def test_cmudict_think_sink():
    # Real CMU: think TH IH1 NG K, sink S IH1 NG K -> 0.75 -> near_miss.
    m = classify_pair("think", "sink")
    assert m.status == "near_miss"
    assert m.oov is False


def test_cmudict_their_there():
    m = classify_pair("their", "there")
    assert m.status == "equal"
    assert m.homophone is True


# ---------- Added after review (expected numbers are hand-computed, NOT measured) ----------


def test_apostrophe_lookup():
    # ADR-005 "Package info": john's -> JH AA1 N Z; stress removed -> JH AA N Z.
    prons = pronunciations("john's")
    assert prons != []
    assert [p[:-1] if p[-1] in "012" else p for p in prons[0]] == ["JH", "AA", "N", "Z"]


def test_short_word_never_near_miss():
    # ADR-005 does not define "short word"; here it means <= 2 phonemes, the only group
    # that mathematically cannot fall in [0.65, 0.90]: sim = (L-d)/L with L<=2 is only 0, 0.5, 1.
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
    # Contract: input must be normalized by text_norm (lowercase) before lookup.
    assert pronunciations("The") == []
    assert pronunciations("the") != []


def test_best_pair_cross_multiplication():
    # ref: A = P R (2), B = B D G K L M (6). hyp: hA = P Z (2), hB = B D G K S T (6).
    # (A, hA): dist 1, L 2 -> sim 1/2. (B, hB): dist 2, L 6 -> sim 4/6.
    # Cross pair sharing no phoneme -> dist = L -> sim 0.
    # The variant with the SMALLEST dist (1) has a LOWER sim (0.5 < 0.667); choosing by dist gives
    # classify_sim(1, 2) = sub (wrong). Choosing by sim (cross-multiply) is right: near_miss.
    # Cross-multiply check: (6-2)*2 = 8 > (2-1)*6 = 6.
    assert classify_pair("xref", "xhyp", pron=stub_pron).status == "near_miss"
    assert phonetic_sim("xref", "xhyp", pron=stub_pron) == pytest.approx(2 / 3)
