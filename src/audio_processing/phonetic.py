"""Độ tương đồng âm vị, đồng âm, near-miss (ADR-005 P1, P2, P3, P7, P9, P11)."""

import functools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

Status = Literal["equal", "near_miss", "sub"]


@dataclass(frozen=True)
class PhoneticMatch:
    status: Status
    homophone: bool
    oov: bool  # ref hoặc hyp không có trong CMU (P3) -> bước sau gắn cờ cmu_oov


@functools.lru_cache(maxsize=1)
def _cmu_dict() -> dict[str, list[list[str]]]:
    """Nạp cmudict lười, một lần (phase3_decision §4 #13). Không gọi lúc import."""
    import cmudict

    return cmudict.dict()


def pronunciations(word: str) -> list[list[str]]:
    """Các cách phát âm CMU của `word`; [] nếu OOV.

    Tra nguyên dạng (giữ dấu nháy, không lowercase/strip), giữ stress. Trả bản sao
    để caller không sửa được dict đang cache.
    """
    return [list(p) for p in _cmu_dict().get(word, [])]


def lev(a: Sequence[str], b: Sequence[str]) -> int:
    """Levenshtein không trọng số trên danh sách phoneme (DP tự viết, hai hàng)."""
    prev = list(range(len(b) + 1))  # hàng i=0: biến [] thành b[:j] cần j phép chèn
    for i, x in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, start=1):
            cur[j] = min(
                prev[j] + 1,  # xoá x
                cur[j - 1] + 1,  # chèn y
                prev[j - 1] + (x != y),  # thay (0 nếu giống)
            )
        prev = cur
    return prev[-1]


def _strip_stress(phones: Sequence[str]) -> list[str]:
    """Bỏ chữ số stress 0/1/2 ở cuối phoneme (AH0 -> AH)."""
    return [p[:-1] if p and p[-1] in "012" else p for p in phones]


def _best_pair(
    ref: str, hyp: str, pron: Callable[[str], list[list[str]]]
) -> tuple[int, int] | None:
    """(dist, max_len) của cặp biến thể có sim lớn nhất; None nếu một bên OOV.

    sim = (L - d) / L. So hai sim bằng nhân chéo số nguyên:
    (L1-d1)/L1 > (L2-d2)/L2  <=>  (L1-d1)*L2 > (L2-d2)*L1  (L > 0), không dùng float.
    """
    prons_r = pron(ref)
    prons_h = pron(hyp)
    if not prons_r or not prons_h:
        return None
    best: tuple[int, int] | None = None
    for p in prons_r:
        pr = _strip_stress(p)
        for q in prons_h:
            qh = _strip_stress(q)
            length = max(len(pr), len(qh))
            if length == 0:
                raise ValueError("biến thể phát âm rỗng")
            cand = (lev(pr, qh), length)
            if best is None or (length - cand[0]) * best[1] > (best[1] - best[0]) * length:
                best = cand
    return best


def phonetic_sim(
    ref: str,
    hyp: str,
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> float | None:
    """max trên mọi cặp biến thể của 1 - Lev/max(len), đã bỏ stress; None nếu một bên OOV.

    Chỉ để báo/hiển thị nội bộ (P7: không xuất ra JSON); phân loại dùng classify_sim.
    """
    best = _best_pair(ref, hyp, pron)
    if best is None:
        return None
    dist, length = best
    return (length - dist) / length


def classify_sim(dist: int, max_len: int) -> tuple[Status, bool]:
    """Bảng P2 bằng số nguyên trên (dist, max_len) -> (status, homophone).

    sim = (max_len - dist) / max_len. Với max_len > 0:
      sim > 0.90   <=> 10*(max_len - dist) > 9*max_len
      sim >= 0.65  <=> 20*(max_len - dist) >= 13*max_len
    """
    if max_len <= 0 or not 0 <= dist <= max_len:
        raise ValueError(f"cần max_len > 0 và 0 <= dist <= max_len, nhận ({dist}, {max_len})")
    match = max_len - dist
    if dist == 0:
        return "equal", True  # sim = 1.0, đồng âm
    if 10 * match > 9 * max_len:
        return "equal", False  # sim thuộc (0.90, 1.0)
    if 20 * match >= 13 * max_len:
        return "near_miss", False  # sim thuộc [0.65, 0.90]
    return "sub", False


def classify_pair(
    ref: str,
    hyp: str,
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> PhoneticMatch:
    """Phân loại một cặp từ chuẩn hoá (P3, P11)."""
    oov = not pron(ref) or not pron(hyp)
    if ref == hyp:
        return PhoneticMatch("equal", False, oov)  # P11: cùng chuỗi không phải đồng âm
    if oov:
        return PhoneticMatch("sub", False, True)  # P3: OOV không xét near-miss
    best = _best_pair(ref, hyp, pron)
    if best is None:
        raise RuntimeError("không thể xảy ra: OOV đã return ở trên")
    status, homophone = classify_sim(*best)
    return PhoneticMatch(status, homophone, False)


def pron_keys(
    word: str,
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> frozenset[tuple[str, ...]]:
    """Tập chuỗi phoneme đã bỏ stress của `word`; OOV trả frozenset rỗng.

    Dùng cho alignment: hai từ đồng âm <=> hai tập có giao khác rỗng (ADR-005 P8 bước 2).
    """
    return frozenset(tuple(_strip_stress(p)) for p in pron(word))
