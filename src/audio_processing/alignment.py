"""Alignment hai tầng (ADR-005 P8): tầng 1 gióng token con (align_tokens), tầng 2 phân loại
near_miss và gộp về ref_index (align, P5)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from src.audio_processing.contracts import WordTimestamp
from src.audio_processing.phonetic import classify_pair, pron_keys, pronunciations
from src.audio_processing.text_norm import (
    indexed_subtokens,
    is_filler,
    normalize_script,
    normalize_token,
    split_sentences,
)

Op = Literal["equal", "sub", "del", "ins"]


@dataclass(frozen=True)
class HypToken:
    hyp_index: int  # vị trí trên danh sách từ STT ĐÃ loại filler (D15)
    text: str  # token con đã chuẩn hoá


@dataclass(frozen=True)
class TokenOp:
    op: Op
    ref_index: int | None  # None nếu ins
    ref_sub: str | None
    hyp_index: int | None  # None nếu del
    hyp_sub: str | None
    homophone: bool  # equal nhờ pron trùng mà chuỗi khác


AlignStatus = Literal["equal", "near_miss", "sub", "del", "ins"]


@dataclass(frozen=True)
class AlignedItem:
    """Cùng tên trường và kiểu với AlignmentItem (ADR-004); chuyển sang Pydantic ở bước ráp."""

    status: AlignStatus
    ref_index: int | None  # None nếu ins
    hyp_index: int | None  # None nếu del
    ref_word: str | None  # token gốc, giữ dấu câu
    hyp_word: str | None
    start_s: float | None  # None nếu del; không nội suy
    end_s: float | None
    sentence_index: int
    homophone: bool = False


@dataclass(frozen=True)
class AlignmentResult:
    items: list[AlignedItem]
    counts: dict[str, int]  # n_ref, n_sub, n_del, n_ins, n_near_miss, n_homophone, n_oov
    flags: list[str]


def align(
    script: str,
    words: Sequence[WordTimestamp],
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> AlignmentResult:
    """Gióng script với STT rồi gộp về ref_index (ADR-005 P5, P8 bước 3-4, P10, P11).

    Mỗi token gốc của script.split() có đúng một item không phải ins (D2); ins đếm theo từ nghe
    được (D16). Thứ tự items theo đường gióng. Số đếm và cờ: xem AlignmentResult.
    """
    ref_tokens = normalize_script(script)
    kept = [w for w in words if not is_filler(w.word)]  # cùng bộ lọc với prepare_hyp (D15)
    ops = align_tokens(indexed_subtokens(ref_tokens), prepare_hyp(words), pron=pron)

    sentence_of = [0] * len(ref_tokens)
    for s, (a, b, _) in enumerate(split_sentences(script)):
        sentence_of[a:b] = [s] * (b - a)

    # Bước A: duyệt ops, gom trạng thái các token con theo ref_index, ghi thứ tự xuất hiện.
    entries: list[tuple[str, int]] = []  # ("ref", ref_index) hoặc ("ins", hyp_index)
    acc: dict[int, tuple[list[str], set[int], list[bool]]] = {}  # r -> (statuses, hyp, [homo])
    ins_seen: set[int] = set()
    flushed: set[int] = set()
    pair_oov = False

    def flush_empty(idx: int) -> None:
        # Token chỉ dấu câu (không có token con) không có op: đặt ngay sau op không-ins trước nó.
        while idx < len(ref_tokens) and not ref_tokens[idx].subtokens:
            if idx not in flushed:
                flushed.add(idx)
                entries.append(("ref", idx))
            idx += 1

    flush_empty(0)
    for op in ops:
        if op.op == "ins":
            if op.hyp_index not in ins_seen:  # một hyp_index chỉ sinh một ins (D16, phase3 #8)
                ins_seen.add(op.hyp_index)
                entries.append(("ins", op.hyp_index))
            continue
        r = op.ref_index
        if r not in acc:
            acc[r] = ([], set(), [False])
            entries.append(("ref", r))
        statuses, hyp_set, homo = acc[r]
        if op.op == "equal":
            statuses.append("equal")
            homo[0] = homo[0] or op.homophone
            pair_oov = pair_oov or not pron(op.ref_sub) or not pron(op.hyp_sub)
        elif op.op == "sub":
            m = classify_pair(op.ref_sub, op.hyp_sub, pron=pron)  # P8 bước 3
            statuses.append(m.status)
            homo[0] = homo[0] or (m.status == "equal" and m.homophone)
            pair_oov = pair_oov or m.oov
        else:
            statuses.append("del")
        if op.hyp_index is not None:
            hyp_set.add(op.hyp_index)
        flush_empty(r + 1)

    # Bước B: dựng item theo thứ tự entries.
    items: list[AlignedItem] = []
    cur_sentence = 0  # câu của ref gần nhất phía trước (phase3 #10: chưa có thì 0)
    for kind, idx in entries:
        if kind == "ins":
            w = kept[idx]
            items.append(AlignedItem("ins", None, idx, None, w.word, w.start_s, w.end_s,
                                     cur_sentence))
            continue
        cur_sentence = sentence_of[idx]
        raw = ref_tokens[idx].raw
        if idx not in acc:  # không có token con: equal, không có hyp (Q1)
            items.append(AlignedItem("equal", idx, None, raw, None, None, None, cur_sentence))
            continue
        statuses, hyp_set, homo = acc[idx]
        if all(s == "del" for s in statuses):
            status: AlignStatus = "del"
        elif "sub" in statuses or "del" in statuses:  # có sub, hoặc chỉ một phần del (P5)
            status = "sub"
        elif "near_miss" in statuses:
            status = "near_miss"
        else:
            status = "equal"
        hs = sorted(hyp_set)
        if hs:
            first, last = kept[hs[0]], kept[hs[-1]]
            items.append(AlignedItem(
                status, idx, hs[0], raw, " ".join(kept[h].word for h in hs),
                first.start_s, last.end_s, cur_sentence, status == "equal" and homo[0]))
        else:
            items.append(AlignedItem(status, idx, None, raw, None, None, None, cur_sentence))

    n_oov = sum(any(not pron(s) for s in t.subtokens) for t in ref_tokens)  # P10
    counts = {
        "n_ref": len(ref_tokens),  # = len(script.split()) (D2)
        "n_sub": sum(it.status == "sub" for it in items),
        "n_del": sum(it.status == "del" for it in items),
        "n_ins": sum(it.status == "ins" for it in items),
        "n_near_miss": sum(it.status == "near_miss" for it in items),
        "n_homophone": sum(it.status == "equal" and it.homophone for it in items),  # P11
        "n_oov": n_oov,
    }
    return AlignmentResult(items, counts, ["cmu_oov"] if n_oov > 0 or pair_oov else [])


def prepare_hyp(words: Sequence[WordTimestamp]) -> list[HypToken]:
    """Loại filler, đánh hyp_index 0,1,2... trên các từ còn lại, chuẩn hoá từng từ.

    Từ bung thành nhiều token con thì các token con chung hyp_index (phase3 #8).
    Từ chuẩn hoá ra rỗng ("—") không sinh HypToken nhưng vẫn chiếm một hyp_index,
    để chỉ số khớp với vị trí trong danh sách từ STT đã loại filler (D15).
    """
    kept = [w for w in words if not is_filler(w.word)]
    return [
        HypToken(idx, sub)
        for idx, w in enumerate(kept)
        for sub in normalize_token(w.word)
    ]


def align_tokens(
    ref: Sequence[tuple[int, str]],
    hyp: Sequence[HypToken],
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> list[TokenOp]:
    """Levenshtein mức token; khớp = chuỗi bằng nhau hoặc pron_keys giao nhau.

    Chi phí: khớp 0; sub, del, ins mỗi loại 1. Giữa các đường cùng cost tối thiểu chọn đường
    nhiều equal nhất (ADR-005 P8, làm rõ 11/11); vẫn hoà thì truy vết ngược từ (n, m) ưu tiên
    equal > sub > del > ins ở từng ô. Kết quả theo thứ tự từ đầu đến cuối.
    """
    n, m = len(ref), len(hyp)

    keys: dict[str, frozenset[tuple[str, ...]]] = {}  # pron_keys tính một lần cho mỗi từ

    def keys_of(word: str) -> frozenset[tuple[str, ...]]:
        if word not in keys:
            keys[word] = pron_keys(word, pron=pron)
        return keys[word]

    # match[i-1][j-1] = 1 nếu ref[i-1] khớp hyp[j-1] (bằng chuỗi hoặc đồng âm).
    match = [bytearray(m) for _ in range(n)]
    for i in range(n):
        r = ref[i][1]
        for j in range(m):
            h = hyp[j].text
            match[i][j] = 1 if r == h or (keys_of(r) & keys_of(h)) else 0

    # D[i][j] = số phép sửa tối thiểu để biến i token ref đầu thành j token hyp đầu.
    # E[i][j] = số equal lớn nhất trong các đường đạt cost D[i][j]. Chọn theo (cost, -n_eq).
    d = [[0] * (m + 1) for _ in range(n + 1)]
    e = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            hit = match[i - 1][j - 1]
            best_c, best_e = d[i - 1][j - 1] + (0 if hit else 1), e[i - 1][j - 1] + hit
            for c, q in ((d[i - 1][j] + 1, e[i - 1][j]), (d[i][j - 1] + 1, e[i][j - 1])):
                if c < best_c or (c == best_c and q > best_e):
                    best_c, best_e = c, q
            d[i][j], e[i][j] = best_c, best_e

    # Truy vết ngược từ (n, m); thứ tự thử: equal, sub, del, ins; lấy bước đầu mà
    # (cost, n_eq) của ô trước cộng bước đó bằng đúng cặp của ô hiện tại.
    ops: list[TokenOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        if (i > 0 and j > 0 and match[i - 1][j - 1] and d[i - 1][j - 1] == d[i][j]
                and e[i - 1][j - 1] + 1 == e[i][j]):
            r, h = ref[i - 1], hyp[j - 1]
            ops.append(TokenOp("equal", r[0], r[1], h.hyp_index, h.text, r[1] != h.text))
            i, j = i - 1, j - 1
        elif (i > 0 and j > 0 and not match[i - 1][j - 1] and d[i - 1][j - 1] + 1 == d[i][j]
                and e[i - 1][j - 1] == e[i][j]):
            r, h = ref[i - 1], hyp[j - 1]
            ops.append(TokenOp("sub", r[0], r[1], h.hyp_index, h.text, False))
            i, j = i - 1, j - 1
        elif i > 0 and d[i - 1][j] + 1 == d[i][j] and e[i - 1][j] == e[i][j]:
            r = ref[i - 1]
            ops.append(TokenOp("del", r[0], r[1], None, None, False))
            i -= 1
        else:  # ins: các nhánh trên không thoả thì chỉ còn nhánh này
            h = hyp[j - 1]
            ops.append(TokenOp("ins", None, None, h.hyp_index, h.text, False))
            j -= 1
    ops.reverse()
    return ops
