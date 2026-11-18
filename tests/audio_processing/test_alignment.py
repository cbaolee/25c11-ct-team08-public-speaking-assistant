"""Tests for alignment level 1 (ADR-005 P8 steps 1-2, phase3_decision §4 #5, #8).

Every expected number is HAND-COMPUTED (not measured). Uses a pron stub, no CMU load, no network.
jiwer is only used to CROSS-CHECK, not as the answer key.
"""

import jiwer
import pytest

from src.audio_processing.alignment import (
    AlignedItem,
    HypToken,
    TokenOp,
    align,
    align_tokens,
    prepare_hyp,
)
from src.audio_processing.contracts import WordTimestamp
from src.audio_processing.phonetic import pron_keys
from src.audio_processing.text_norm import indexed_subtokens, normalize_script

STUB: dict[str, list[list[str]]] = {
    "their": [["DH", "EH1", "R"]],
    "there": [["DH", "EH1", "R"]],
    "the": [["DH", "AH0"], ["DH", "AH1"], ["DH", "IY0"]],
}


def stub_pron(word: str) -> list[list[str]]:
    return STUB.get(word, [])


def _ref(*words: str) -> list[tuple[int, str]]:
    return list(enumerate(words))


def _hyp(*words: str) -> list[HypToken]:
    return [HypToken(i, w) for i, w in enumerate(words)]


def _ops(result: list[TokenOp]) -> list[str]:
    return [t.op for t in result]


def _w(word: str, i: int = 0) -> WordTimestamp:
    return WordTimestamp(word=word, start_s=float(i), end_s=float(i) + 0.5)


# ---------- prepare_hyp ----------

def test_filler_not_ins():
    # STT "I Um, think uh so": "Um," and "uh" are fillers -> dropped. Left: i, think, so
    # -> hyp_index 0, 1, 2 in a row. Script "I think so" -> 3 equal, 0 ins.
    words = [_w("I"), _w("Um,"), _w("think"), _w("uh"), _w("so")]
    hyp = prepare_hyp(words)
    assert hyp == [HypToken(0, "i"), HypToken(1, "think"), HypToken(2, "so")]
    ref = indexed_subtokens(normalize_script("I think so"))
    result = align_tokens(ref, hyp, pron=stub_pron)
    assert _ops(result) == ["equal", "equal", "equal"]
    assert [t.hyp_index for t in result] == [0, 1, 2]


def test_hyp_expansion_shares_hyp_index():
    # STT "it's" -> contractions: "it", "is", same hyp_index 0 (phase3 #8).
    hyp = prepare_hyp([_w("it's")])
    assert hyp == [HypToken(0, "it"), HypToken(0, "is")]
    # Script "it is" -> 2 sub-tokens, ref_index 0 and 1 -> 2 equal.
    result = align_tokens(indexed_subtokens(normalize_script("it is")), hyp, pron=stub_pron)
    assert _ops(result) == ["equal", "equal"]
    assert [t.hyp_index for t in result] == [0, 0]


def test_prepare_hyp_empty_token_keeps_index():
    # "—" normalizes to empty: no HypToken made but it still takes hyp_index 1.
    hyp = prepare_hyp([_w("well"), _w("—"), _w("ok")])
    assert hyp == [HypToken(0, "well"), HypToken(2, "ok")]


# ---------- align_tokens ----------

def test_alignment_deterministic_tiebreak():
    # Three cases with >= 2 equal-cost paths. Row = ref, column = hyp, D[i][j] (not measured).
    # Rule (ADR-005 P8, clarified 11/11): each cell stores cost/n_eq, pick by (cost, -n_eq);
    # if still tied, the traceback prefers equal > sub > del > ins.
    #
    # Case A: ref [a, b], hyp [c] (no matching pair, n_eq always 0).
    #   Grid cost/n_eq:   -     c
    #                -   0/0   1/0
    #                a   1/0   1/0
    #                b   2/0   2/0
    #   D[2][1]: sub D[1][0]+1 = 2/0; del D[1][1]+1 = 2/0; ins D[2][0]+1 = 3/0. Tie sub vs del
    #   -> sub (b/c), then (1,0) only has del a. Forward: del a, sub b/c. (Unchanged from before.)
    ref_a, hyp_a = _ref("a", "b"), _hyp("c")
    # Ca B: ref [a, a], hyp [a].
    #   Grid cost/n_eq:   -     a
    #                -   0/0   1/0
    #                a   1/0   0/1
    #                a   2/0   1/1
    #   D[2][1]: equal D[1][0]+(0,1) = 1/1; del D[1][1]+1 = 1/1 (tie); ins = 3/0.
    #   Tie equal vs del -> equal. Then (1,0): del. Forward: del ref0, equal ref1/hyp0. (Unchanged.)
    ref_b, hyp_b = _ref("a", "a"), _hyp("a")
    # Ca C: ref [a, b], hyp [b, c].
    #   Grid cost/n_eq:   -     b     c
    #                -   0/0   1/0   2/0
    #                a   1/0   1/0   2/0
    #                b   2/0   1/1   2/1
    #   D[2][2]: sub D[1][1]+1 = 2/0; del D[1][2]+1 = 3/0; ins D[2][1]+1 = 2/1.
    #   Same cost 2 but ins has n_eq = 1 > 0 -> pick ins c. (2,1)=1/1: equal b/b
    #   (D[1][0]+(0,1) = 1/1). (1,0): del a. Forward: del a, equal b, ins c.
    #   (CHANGED from "sub, sub".)
    ref_c, hyp_c = _ref("a", "b"), _hyp("b", "c")

    for _ in range(2):  # run twice: same result
        assert _ops(align_tokens(ref_a, hyp_a, pron=stub_pron)) == ["del", "sub"]
        res_b = align_tokens(ref_b, hyp_b, pron=stub_pron)
        assert _ops(res_b) == ["del", "equal"]
        assert res_b[0].ref_index == 0
        assert res_b[1].ref_index == 1
        assert res_b[1].hyp_index == 0
        assert _ops(align_tokens(ref_c, hyp_c, pron=stub_pron)) == ["del", "equal", "ins"]


def test_tiebreak_prefers_more_equal():
    # Script "their cat sat", hyp ["there", "sat", "down"], their/there are homophones.
    # Hand-computed, not measured. Grid cost/n_eq (row = ref, column = hyp):
    #            -     there  sat    down
    #      -    0/0    1/0   2/0    3/0
    #   their   1/0    0/1   1/1    2/1
    #   cat     2/0    1/1   1/1    2/1
    #   sat     3/0    2/1   1/2    2/2
    # Cell (3,3): sub D[2][2]+1 = 2/1; del D[2][3]+1 = 3/1; ins D[3][2]+1 = 2/2
    #   -> pick ins (n_eq 2).
    # (3,2)=1/2: equal sat/sat (D[2][1]+(0,1) = 1/2). (2,1)=1/1: equal does not match (cat/there);
    # sub D[1][0]+1 = 2/0 wrong; del D[1][1]+1 = 1/1 right -> del cat. (1,1): equal their/there.
    # The old path "equal, sub, sub" also costs 2 but has only 1 equal; the new path has 2 equal.
    ref = indexed_subtokens(normalize_script("their cat sat"))
    res = align_tokens(ref, _hyp("there", "sat", "down"), pron=stub_pron)
    assert res == [
        TokenOp("equal", 0, "their", 0, "there", True),
        TokenOp("del", 1, "cat", None, None, False),
        TokenOp("equal", 2, "sat", 1, "sat", False),
        TokenOp("ins", None, None, 2, "down", False),
    ]


def test_tiebreak_del_vs_ins():
    # ref [a, b], hyp [b, a]. Hand-computed, not measured. Grid cost/n_eq:
    #            -     b     a
    #      -    0/0   1/0   2/0
    #      a    1/0   1/0   1/1
    #      b    2/0   1/1   2/1
    # D[1][2]: a/a match, diag D[0][1]+(0,1) = 1/1. D[2][1]: b/b match, diag D[1][0]+(0,1) = 1/1.
    # Ô (2,2): sub D[1][1]+1 = 2/0; del D[1][2]+1 = 2/1; ins D[2][1]+1 = 2/1.
    # del and ins tie (both 2/1), both beat sub; traceback prefers del over ins -> del b.
    # (1,2)=1/1: equal a/a (D[0][1]+(0,1)). (0,1): only ins b left. Forward: ins b, equal a, del b.
    res = align_tokens(_ref("a", "b"), _hyp("b", "a"), pron=stub_pron)
    assert res == [
        TokenOp("ins", None, None, 0, "b", False),
        TokenOp("equal", 0, "a", 1, "a", False),
        TokenOp("del", 1, "b", None, None, False),
    ]


def _counts(res: list[TokenOp]) -> tuple[int, int, int]:
    return tuple(sum(t.op == k for t in res) for k in ("sub", "del", "ins"))  # type: ignore[return-value]


def test_matches_jiwer_without_homophones():
    # Total S+D+I must equal jiwer in every case (min cost is unique even when paths tie).
    totals = [
        ("a b c", "a x c"),
        ("a b c", "a c"),
        ("the cat sat", "the cat sat on"),
        ("quick brown fox jumps", "brown fox leaps over"),
    ]
    for ref_s, hyp_s in totals:
        out = jiwer.process_words(ref_s, hyp_s)
        res = align_tokens(_ref(*ref_s.split()), _hyp(*hyp_s.split()), pron=stub_pron)
        assert sum(_counts(res)) == out.substitutions + out.deletions + out.insertions
    # Each of S, D, I only in cases without ties (unique lowest-cost path):
    # "a b c"/"a x c": S=1. "a b c"/"a c": D=1. "the cat sat"/"... on": I=1.
    uniques = [
        ("a b c", "a x c", (1, 0, 0)),
        ("a b c", "a c", (0, 1, 0)),
        ("the cat sat", "the cat sat on", (0, 0, 1)),
    ]
    for ref_s, hyp_s, want in uniques:
        out = jiwer.process_words(ref_s, hyp_s)
        res = align_tokens(_ref(*ref_s.split()), _hyp(*hyp_s.split()), pron=stub_pron)
        assert _counts(res) == want
        assert want == (out.substitutions, out.deletions, out.insertions)


def test_del_case():
    # ref a b c, hyp a c: unique cost 1 = del b (other path: sub b/c + del c = 2).
    res = align_tokens(_ref("a", "b", "c"), _hyp("a", "c"), pron=stub_pron)
    assert _ops(res) == ["equal", "del", "equal"]
    assert res[1] == TokenOp("del", 1, "b", None, None, False)


def test_ins_case():
    # ref a c, hyp a b c: unique cost 1 = ins b.
    res = align_tokens(_ref("a", "c"), _hyp("a", "b", "c"), pron=stub_pron)
    assert _ops(res) == ["equal", "ins", "equal"]
    assert res[1] == TokenOp("ins", None, None, 1, "b", False)


def test_homophone_their_there():
    res = align_tokens(_ref("their"), _hyp("there"), pron=stub_pron)
    assert res == [TokenOp("equal", 0, "their", 0, "there", True)]
    # Same string: equal but homophone False.
    res = align_tokens(_ref("their"), _hyp("their"), pron=stub_pron)
    assert res[0].op == "equal"
    assert res[0].homophone is False


def test_empty_inputs():
    assert align_tokens([], [], pron=stub_pron) == []
    # empty ref, hyp 2 tokens -> 2 ins; empty hyp, ref 2 tokens -> 2 del.
    res = align_tokens([], _hyp("x", "y"), pron=stub_pron)
    assert _ops(res) == ["ins", "ins"]
    assert [t.hyp_index for t in res] == [0, 1]
    res = align_tokens(_ref("x", "y"), [], pron=stub_pron)
    assert _ops(res) == ["del", "del"]
    assert [t.ref_index for t in res] == [0, 1]


def test_cost_equals_edit_distance():
    # ref a b c d, hyp b c x d: min cost 2 (delete a, insert x); cost 1 is impossible because
    # 3 positions are shifted. Non-equal op count = D[4][4] = 2.
    res = align_tokens(_ref("a", "b", "c", "d"), _hyp("b", "c", "x", "d"), pron=stub_pron)
    assert sum(t.op != "equal" for t in res) == 2
    assert _ops(res) == ["del", "equal", "equal", "ins", "equal"]


def test_punct_only_ref_token_not_in_dp():
    # "—" normalizes to empty so indexed_subtokens makes no sub-token: 2 tokens enter DP,
    # ref_index 0 and 2 (ref_index 1 does not appear).
    ref = indexed_subtokens(normalize_script("Hello — world"))
    assert ref == [(0, "hello"), (2, "world")]
    res = align_tokens(ref, _hyp("hello", "world"), pron=stub_pron)
    assert [t.ref_index for t in res] == [0, 2]
    assert _ops(res) == ["equal", "equal"]


# ---------- pron_keys (phonetic.py) ----------

def test_pron_keys_strips_stress_and_oov():
    # the: DH AH0 | DH AH1 | DH IY0 -> stress removed, duplicates merged: {(DH, AH), (DH, IY)}.
    assert pron_keys("the", pron=stub_pron) == frozenset({("DH", "AH"), ("DH", "IY")})
    assert pron_keys("covid", pron=stub_pron) == frozenset()


# ---------- align() : level 2, merge back to ref_index (ADR-005 P5, P8 steps 3-4, P10, P11) ---
# Every expected number below is HAND-COMPUTED, not measured.

_PH12_A = [f"P{i}" for i in range(12)]
_PH12_B = [*_PH12_A[:11], "PX"]  # exactly 1 phoneme off: sim = 11/12 ~ 0.917 in (0.90, 1.0)

ALIGN_STUB: dict[str, list[list[str]]] = {
    **STUB,
    "think": [["TH", "IH1", "NG", "K"]],
    "sink": [["S", "IH1", "NG", "K"]],  # Lev 1/4 -> sim 0.75 -> near_miss
    "do": [["D", "UW1"]],
    "dew": [["D", "Y", "UW1"]],  # Lev 1/3 -> sim 0.667 -> near_miss
    "not": [["N", "AA1", "T"]],
    "zzz": [["Z"]],  # vs "not": Lev 3/3 -> sim 0 -> sub
    "alpha": [_PH12_A],
    "alphb": [_PH12_B],
    "is": [["IH1", "Z"]],
    "here": [["HH", "IY1", "R"]],
    "i": [["AY1"]],
    "so": [["S", "OW1"]],
    # "covid": OOV on purpose (not in the stub)
}


def alias_pron(word: str) -> list[list[str]]:
    return ALIGN_STUB.get(word, [])


def _words(*ws: str) -> list[WordTimestamp]:
    # Words are 0.5 s apart: word i starts at i*0.5, ends at i*0.5 + 0.4 (fake, not measured).
    return [WordTimestamp(word=w, start_s=i * 0.5, end_s=i * 0.5 + 0.4) for i, w in enumerate(ws)]


def _status(res) -> list[str]:
    return [it.status for it in res.items]


def test_contraction_one_ref_index():
    # "I don't know" -> ref (0,i) (1,do) (1,not) (2,know); hyp i, do, know.
    # Cheapest path: equal, equal, del not, equal (cost 1). "don't" has 1 equal child + 1 del child
    # -> P5: only partly del -> EXACTLY ONE sub. n_ref = 3 original tokens.
    res = align("I don't know", _words("I", "do", "know"), pron=alias_pron)
    assert _status(res) == ["equal", "sub", "equal"]
    assert res.counts["n_ref"] == 3
    assert res.counts["n_sub"] == 1
    assert res.counts["n_del"] == 0
    assert res.items[1].ref_word == "don't"
    assert res.items[1].hyp_index == 1  # smallest hyp_index among children with a hyp


def test_ref_index_sub_beats_near_miss():
    # "don't" -> do, not. hyp "dew zzz": do/dew near_miss (0.667), not/zzz sub (0).
    # Error wins over near_miss -> item is sub, and near_miss is NOT counted (n_near_miss = 0).
    res = align("don't", _words("dew", "zzz"), pron=alias_pron)
    assert _status(res) == ["sub"]
    assert res.counts["n_near_miss"] == 0
    assert res.counts["n_sub"] == 1


def test_gap_not_counted_as_homophone():
    # sim = 11/12 in (0.90, 1.0): P2 -> equal, homophone False; P11 -> not in n_homophone.
    res = align("alpha", _words("alphb"), pron=alias_pron)
    assert _status(res) == ["equal"]
    assert res.items[0].homophone is False
    assert res.counts["n_homophone"] == 0


def test_homophone_counted():
    # their/there have the same phoneme string: equal at level 1, homophone True -> n_homophone = 1.
    res = align("their", _words("there"), pron=alias_pron)
    assert _status(res) == ["equal"]
    assert res.items[0].homophone is True
    assert res.counts["n_homophone"] == 1


def test_n_oov_counts_equal_items():
    # "covid" is OOV in the stub; identical hyp -> equal,
    # but P10: still counts n_oov = 1 and flags it.
    res = align("covid is here", _words("covid", "is", "here"), pron=alias_pron)
    assert _status(res) == ["equal", "equal", "equal"]
    assert res.counts["n_oov"] == 1
    assert "cmu_oov" in res.flags


def test_no_oov_no_flag():
    res = align("is here", _words("is", "here"), pron=alias_pron)
    assert res.counts["n_oov"] == 0
    assert res.flags == []


def test_contraction_symmetric_match():
    # script "it's fine" -> it, is, fine; STT "it", "is", "fine": 2 equal items, no ins.
    res = align("it's fine", _words("it", "is", "fine"), pron=alias_pron)
    assert _status(res) == ["equal", "equal"]
    first = res.items[0]
    assert first.ref_index == 0
    assert first.hyp_index == 0
    assert first.start_s == pytest.approx(0.0)  # start of "it"
    assert first.end_s == pytest.approx(0.9)  # end of "is" = 1*0.5 + 0.4
    assert first.hyp_word == "it is"
    assert res.counts["n_ins"] == 0


def test_raw_match_before_expand():
    # "he's" on both sides: both expand to "he is" -> all equal.
    res = align("he's here", _words("he's", "here"), pron=alias_pron)
    assert _status(res) == ["equal", "equal"]


def test_known_limit_he_s_vs_he_has():
    # KNOWN LIMIT, ADR-005 P12 point 3: "he's" -> he is, STT "he has" -> is/has is sub.
    res = align("he's here", _words("he", "has", "here"), pron=alias_pron)
    assert _status(res) == ["sub", "equal"]
    assert res.items[0].ref_word == "he's"
    assert res.items[0].hyp_word == "he has"


def test_del_has_no_times():
    # ref a b c, hyp a c: del b, no time interpolation.
    res = align("a b c", _words("a", "c"), pron=alias_pron)
    assert _status(res) == ["equal", "del", "equal"]
    d = res.items[1]
    assert (d.hyp_index, d.hyp_word, d.start_s, d.end_s) == (None, None, None, None)
    assert res.counts["n_del"] == 1


def test_ins_sentence_index_follows_previous_ref():
    # Script "Hello world. Next one." -> sentence 0 = hello world, sentence 1 = next one.
    # Insert "really" after "world" -> sentence 0; insert after "next" -> sentence 1.
    res = align("Hello world. Next one.", _words("hello", "world", "really", "next", "one"),
                pron=alias_pron)
    ins = [it for it in res.items if it.status == "ins"]
    assert [it.sentence_index for it in ins] == [0]
    res = align("Hello world. Next one.", _words("hello", "world", "next", "really", "one"),
                pron=alias_pron)
    ins = [it for it in res.items if it.status == "ins"]
    assert [it.sentence_index for it in ins] == [1]
    assert ins[0].ref_index is None
    assert ins[0].hyp_word == "really"
    assert ins[0].start_s == pytest.approx(1.5)  # STT word index 3 -> 3*0.5


def test_ins_before_first_ref_is_sentence_zero():
    res = align("hello world", _words("well", "hello", "world"), pron=alias_pron)
    assert _status(res) == ["ins", "equal", "equal"]
    assert res.items[0].sentence_index == 0


def test_punct_only_token_is_equal_item_with_no_hyp():
    # "Hello — world": 3 original tokens -> 3 items; "—" has no sub-token -> equal, hyp/time None.
    res = align("Hello — world", _words("hello", "world"), pron=alias_pron)
    assert _status(res) == ["equal", "equal", "equal"]
    mid = res.items[1]
    assert mid.ref_index == 1
    assert mid.ref_word == "—"
    assert (mid.hyp_index, mid.hyp_word, mid.start_s, mid.end_s) == (None, None, None, None)
    assert res.counts["n_ref"] == 3


def test_near_miss_think_sink():
    # think/sink sim 0.75 -> near_miss. Not counted in n_sub (near_miss is not an A error).
    res = align("I think so", _words("I", "sink", "so"), pron=alias_pron)
    assert _status(res) == ["equal", "near_miss", "equal"]
    assert res.counts["n_near_miss"] == 1
    assert res.counts["n_sub"] == 0


def test_filler_in_middle_is_not_ins():
    # "Um" is dropped before aligning; hyp_index of "world" is 1 (D15), start comes from "world".
    res = align("hello world", _words("hello", "Um", "world"), pron=alias_pron)
    assert _status(res) == ["equal", "equal"]
    assert res.counts["n_ins"] == 0
    assert res.items[1].hyp_index == 1
    assert res.items[1].start_s == pytest.approx(1.0)  # "world" is STT word index 2 -> 2*0.5


def test_partial_hyp_expansion_gives_equal_plus_ins():
    # script "it", STT "it's" (-> it, is with same hyp_index 0): "it" equal, "is" extra.
    # The extra part becomes 1 ins with the same hyp_index 0 (phase3 #8).
    res = align("it", _words("it's"), pron=alias_pron)
    assert _status(res) == ["equal", "ins"]
    assert res.items[0].hyp_index == 0
    assert res.items[1].hyp_index == 0
    assert res.counts["n_ins"] == 1


def test_total_items_non_ins_equals_n_ref():
    script = "I don't know — it's fine, really."
    res = align(script, _words("I", "do", "know", "well", "it", "is", "fine", "so"),
                pron=alias_pron)
    non_ins = [it for it in res.items if it.status != "ins"]
    assert len(non_ins) == res.counts["n_ref"] == len(script.split())
    assert sorted(it.ref_index for it in non_ins) == list(range(len(script.split())))
    assert isinstance(res.items[0], AlignedItem)
    assert set(res.counts) == {
        "n_ref", "n_sub", "n_del", "n_ins", "n_near_miss", "n_homophone", "n_oov",
    }
