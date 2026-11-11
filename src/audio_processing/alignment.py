"""Alignment tầng 1: gióng token con của kịch bản với token con của STT (ADR-005 P8 bước 1-2).

Chưa làm: phân loại near_miss (P8 bước 3), gộp về ref_index (P5), hàm public align().
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from src.audio_processing.contracts import WordTimestamp
from src.audio_processing.phonetic import pron_keys, pronunciations
from src.audio_processing.text_norm import is_filler, normalize_token

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
