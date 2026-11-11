"""Test alignment tầng 1 (ADR-005 P8 bước 1-2, phase3_decision §4 #5, #8).

Mọi số kỳ vọng là SỐ TÍNH TAY (không phải số đo). Dùng stub pron, không tải CMU, không mạng.
jiwer chỉ dùng để ĐỐI CHIẾU, không phải đáp án.
"""

import jiwer

from src.audio_processing.alignment import (
    HypToken,
    TokenOp,
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
    # STT "I Um, think uh so": "Um," và "uh" là filler -> bị loại. Còn i, think, so
    # -> hyp_index 0, 1, 2 liên tục. Script "I think so" -> 3 equal, 0 ins.
    words = [_w("I"), _w("Um,"), _w("think"), _w("uh"), _w("so")]
    hyp = prepare_hyp(words)
    assert hyp == [HypToken(0, "i"), HypToken(1, "think"), HypToken(2, "so")]
    ref = indexed_subtokens(normalize_script("I think so"))
    result = align_tokens(ref, hyp, pron=stub_pron)
    assert _ops(result) == ["equal", "equal", "equal"]
    assert [t.hyp_index for t in result] == [0, 1, 2]


def test_hyp_expansion_shares_hyp_index():
    # STT "it's" -> contractions: "it", "is", cùng hyp_index 0 (phase3 #8).
    hyp = prepare_hyp([_w("it's")])
    assert hyp == [HypToken(0, "it"), HypToken(0, "is")]
    # Script "it is" -> 2 token con, ref_index 0 và 1 -> 2 equal.
    result = align_tokens(indexed_subtokens(normalize_script("it is")), hyp, pron=stub_pron)
    assert _ops(result) == ["equal", "equal"]
    assert [t.hyp_index for t in result] == [0, 0]


def test_prepare_hyp_empty_token_keeps_index():
    # "—" chuẩn hoá ra rỗng: không sinh HypToken nhưng vẫn chiếm hyp_index 1.
    hyp = prepare_hyp([_w("well"), _w("—"), _w("ok")])
    assert hyp == [HypToken(0, "well"), HypToken(2, "ok")]


# ---------- align_tokens ----------

def test_alignment_deterministic_tiebreak():
    # Ba ca có >= 2 đường đi cùng chi phí. Hàng = ref, cột = hyp, D[i][j] (không phải số đo).
    # Quy tắc (ADR-005 P8, làm rõ 11/11): mỗi ô lưu cost/n_eq, chọn theo (cost, -n_eq);
    # hoà nữa thì khi truy vết ưu tiên equal > sub > del > ins.
    #
    # Ca A: ref [a, b], hyp [c] (không có cặp khớp, n_eq luôn 0).
    #   Bảng cost/n_eq:   -     c
    #                -   0/0   1/0
    #                a   1/0   1/0
    #                b   2/0   2/0
    #   D[2][1]: sub D[1][0]+1 = 2/0; del D[1][1]+1 = 2/0; ins D[2][0]+1 = 3/0. Hoà sub vs del
    #   -> sub (b/c), rồi (1,0) chỉ còn del a. Tiến: del a, sub b/c. (Không đổi so với trước.)
    ref_a, hyp_a = _ref("a", "b"), _hyp("c")
    # Ca B: ref [a, a], hyp [a].
    #   Bảng cost/n_eq:   -     a
    #                -   0/0   1/0
    #                a   1/0   0/1
    #                a   2/0   1/1
    #   D[2][1]: equal D[1][0]+(0,1) = 1/1; del D[1][1]+1 = 1/1 (hoà); ins = 3/0.
    #   Hoà equal vs del -> equal. Rồi (1,0): del. Tiến: del ref0, equal ref1/hyp0. (Không đổi.)
    ref_b, hyp_b = _ref("a", "a"), _hyp("a")
    # Ca C: ref [a, b], hyp [b, c].
    #   Bảng cost/n_eq:   -     b     c
    #                -   0/0   1/0   2/0
    #                a   1/0   1/0   2/0
    #                b   2/0   1/1   2/1
    #   D[2][2]: sub D[1][1]+1 = 2/0; del D[1][2]+1 = 3/0; ins D[2][1]+1 = 2/1.
    #   Cùng cost 2 nhưng ins có n_eq = 1 > 0 -> chọn ins c. (2,1)=1/1: equal b/b
    #   (D[1][0]+(0,1) = 1/1). (1,0): del a. Tiến: del a, equal b, ins c. (ĐỔI so với "sub, sub".)
    ref_c, hyp_c = _ref("a", "b"), _hyp("b", "c")

    for _ in range(2):  # chạy hai lần: cùng kết quả
        assert _ops(align_tokens(ref_a, hyp_a, pron=stub_pron)) == ["del", "sub"]
        res_b = align_tokens(ref_b, hyp_b, pron=stub_pron)
        assert _ops(res_b) == ["del", "equal"]
        assert res_b[0].ref_index == 0
        assert res_b[1].ref_index == 1
        assert res_b[1].hyp_index == 0
        assert _ops(align_tokens(ref_c, hyp_c, pron=stub_pron)) == ["del", "equal", "ins"]


def test_tiebreak_prefers_more_equal():
    # Script "their cat sat", hyp ["there", "sat", "down"], their/there đồng âm.
    # Số tính tay, không phải số đo. Bảng cost/n_eq (hàng = ref, cột = hyp):
    #            -     there  sat    down
    #      -    0/0    1/0   2/0    3/0
    #   their   1/0    0/1   1/1    2/1
    #   cat     2/0    1/1   1/1    2/1
    #   sat     3/0    2/1   1/2    2/2
    # Ô (3,3): sub D[2][2]+1 = 2/1; del D[2][3]+1 = 3/1; ins D[3][2]+1 = 2/2 -> chọn ins (n_eq 2).
    # (3,2)=1/2: equal sat/sat (D[2][1]+(0,1) = 1/2). (2,1)=1/1: equal không khớp (cat/there);
    # sub D[1][0]+1 = 2/0 sai; del D[1][1]+1 = 1/1 đúng -> del cat. (1,1): equal their/there.
    # Đường cũ "equal, sub, sub" cũng cost 2 nhưng chỉ có 1 equal; đường mới có 2 equal.
    ref = indexed_subtokens(normalize_script("their cat sat"))
    res = align_tokens(ref, _hyp("there", "sat", "down"), pron=stub_pron)
    assert res == [
        TokenOp("equal", 0, "their", 0, "there", True),
        TokenOp("del", 1, "cat", None, None, False),
        TokenOp("equal", 2, "sat", 1, "sat", False),
        TokenOp("ins", None, None, 2, "down", False),
    ]


def test_tiebreak_del_vs_ins():
    # ref [a, b], hyp [b, a]. Số tính tay, không phải số đo. Bảng cost/n_eq:
    #            -     b     a
    #      -    0/0   1/0   2/0
    #      a    1/0   1/0   1/1
    #      b    2/0   1/1   2/1
    # D[1][2]: a/a khớp, diag D[0][1]+(0,1) = 1/1. D[2][1]: b/b khớp, diag D[1][0]+(0,1) = 1/1.
    # Ô (2,2): sub D[1][1]+1 = 2/0; del D[1][2]+1 = 2/1; ins D[2][1]+1 = 2/1.
    # del và ins hoà (cùng 2/1), cả hai hơn sub; truy vết ưu tiên del trước ins -> del b.
    # (1,2)=1/1: equal a/a (D[0][1]+(0,1)). (0,1): chỉ còn ins b. Tiến: ins b, equal a, del b.
    res = align_tokens(_ref("a", "b"), _hyp("b", "a"), pron=stub_pron)
    assert res == [
        TokenOp("ins", None, None, 0, "b", False),
        TokenOp("equal", 0, "a", 1, "a", False),
        TokenOp("del", 1, "b", None, None, False),
    ]


def _counts(res: list[TokenOp]) -> tuple[int, int, int]:
    return tuple(sum(t.op == k for t in res) for k in ("sub", "del", "ins"))  # type: ignore[return-value]


def test_matches_jiwer_without_homophones():
    # Tổng S+D+I phải bằng jiwer ở mọi ca (chi phí tối thiểu là duy nhất dù đường đi hoà).
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
    # Từng loại S, D, I chỉ ở các ca không hoà (đường cost thấp nhất duy nhất):
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
    # ref a b c, hyp a c: cost 1 duy nhất = del b (đường khác: sub b/c + del c = 2).
    res = align_tokens(_ref("a", "b", "c"), _hyp("a", "c"), pron=stub_pron)
    assert _ops(res) == ["equal", "del", "equal"]
    assert res[1] == TokenOp("del", 1, "b", None, None, False)


def test_ins_case():
    # ref a c, hyp a b c: cost 1 duy nhất = ins b.
    res = align_tokens(_ref("a", "c"), _hyp("a", "b", "c"), pron=stub_pron)
    assert _ops(res) == ["equal", "ins", "equal"]
    assert res[1] == TokenOp("ins", None, None, 1, "b", False)


def test_homophone_their_there():
    res = align_tokens(_ref("their"), _hyp("there"), pron=stub_pron)
    assert res == [TokenOp("equal", 0, "their", 0, "there", True)]
    # Cùng chuỗi: equal nhưng homophone False.
    res = align_tokens(_ref("their"), _hyp("their"), pron=stub_pron)
    assert res[0].op == "equal"
    assert res[0].homophone is False


def test_empty_inputs():
    assert align_tokens([], [], pron=stub_pron) == []
    # ref rỗng, hyp 2 token -> 2 ins; hyp rỗng, ref 2 token -> 2 del.
    res = align_tokens([], _hyp("x", "y"), pron=stub_pron)
    assert _ops(res) == ["ins", "ins"]
    assert [t.hyp_index for t in res] == [0, 1]
    res = align_tokens(_ref("x", "y"), [], pron=stub_pron)
    assert _ops(res) == ["del", "del"]
    assert [t.ref_index for t in res] == [0, 1]


def test_cost_equals_edit_distance():
    # ref a b c d, hyp b c x d: cost tối thiểu 2 (xoá a, chèn x); cost 1 là không thể vì
    # 3 vị trí lệch nhau. Số op khác equal = D[4][4] = 2.
    res = align_tokens(_ref("a", "b", "c", "d"), _hyp("b", "c", "x", "d"), pron=stub_pron)
    assert sum(t.op != "equal" for t in res) == 2
    assert _ops(res) == ["del", "equal", "equal", "ins", "equal"]


def test_punct_only_ref_token_not_in_dp():
    # "—" chuẩn hoá ra rỗng nên indexed_subtokens không sinh token con: 2 token vào DP,
    # ref_index 0 và 2 (ref_index 1 không xuất hiện).
    ref = indexed_subtokens(normalize_script("Hello — world"))
    assert ref == [(0, "hello"), (2, "world")]
    res = align_tokens(ref, _hyp("hello", "world"), pron=stub_pron)
    assert [t.ref_index for t in res] == [0, 2]
    assert _ops(res) == ["equal", "equal"]


# ---------- pron_keys (phonetic.py) ----------

def test_pron_keys_strips_stress_and_oov():
    # the: DH AH0 | DH AH1 | DH IY0 -> bỏ stress, gộp trùng: {(DH, AH), (DH, IY)}.
    assert pron_keys("the", pron=stub_pron) == frozenset({("DH", "AH"), ("DH", "IY")})
    assert pron_keys("covid", pron=stub_pron) == frozenset()
