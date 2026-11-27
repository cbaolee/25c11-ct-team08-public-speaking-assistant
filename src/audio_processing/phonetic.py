"""Phonetic similarity, homophones, near-miss (ADR-005 P1, P2, P3, P7, P9, P11)."""

import functools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

Status = Literal["equal", "near_miss", "sub"]


@dataclass(frozen=True)
class PhoneticMatch:
    status: Status
    homophone: bool
    oov: bool  # ref or hyp is not in CMU (P3) -> a later step sets the cmu_oov flag


@functools.lru_cache(maxsize=1)
def _cmu_dict() -> dict[str, list[list[str]]]:
    """Load cmudict lazily, once (phase3_decision §4 #13). Not called at import time."""
    import cmudict

    return cmudict.dict()


def pronunciations(word: str) -> list[list[str]]:
    """CMU pronunciations of `word`; [] when OOV.

    Looks up the exact form (apostrophes kept, no lowercase/strip), stress kept. Returns a copy
    so callers cannot change the cached dict.
    """
    return [list(p) for p in _cmu_dict().get(word, [])]


def lev(a: Sequence[str], b: Sequence[str]) -> int:
    """Unweighted Levenshtein over phoneme lists (own DP, two rows)."""
    prev = list(range(len(b) + 1))  # row i=0: turning [] into b[:j] needs j insertions
    for i, x in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, start=1):
            cur[j] = min(
                prev[j] + 1,  # delete x
                cur[j - 1] + 1,  # insert y
                prev[j - 1] + (x != y),  # substitute (0 when equal)
            )
        prev = cur
    return prev[-1]


def _strip_stress(phones: Sequence[str]) -> list[str]:
    """Drop the stress digit 0/1/2 at the end of a phoneme (AH0 -> AH)."""
    return [p[:-1] if p and p[-1] in "012" else p for p in phones]


def _best_pair(
    ref: str, hyp: str, pron: Callable[[str], list[list[str]]]
) -> tuple[int, int] | None:
    """(dist, max_len) of the variant pair with the highest sim; None when one side is OOV.

    sim = (L - d) / L. Two sims are compared by integer cross-multiplication:
    (L1-d1)/L1 > (L2-d2)/L2  <=>  (L1-d1)*L2 > (L2-d2)*L1  (L > 0), no float.
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
                raise ValueError("empty pronunciation variant")
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
    """max over all variant pairs of 1 - Lev/max(len), stress removed; None when one side is OOV.

    Only for internal reports/display (P7: not in the JSON); classification uses classify_sim.
    """
    best = _best_pair(ref, hyp, pron)
    if best is None:
        return None
    dist, length = best
    return (length - dist) / length


def classify_sim(dist: int, max_len: int) -> tuple[Status, bool]:
    """Table P2 in integers on (dist, max_len) -> (status, homophone).

    sim = (max_len - dist) / max_len. With max_len > 0:
      sim > 0.90   <=> 10*(max_len - dist) > 9*max_len
      sim >= 0.65  <=> 20*(max_len - dist) >= 13*max_len
    """
    if max_len <= 0 or not 0 <= dist <= max_len:
        raise ValueError(f"need max_len > 0 and 0 <= dist <= max_len, got ({dist}, {max_len})")
    match = max_len - dist
    if dist == 0:
        return "equal", True  # sim = 1.0, homophone
    if 10 * match > 9 * max_len:
        return "equal", False  # sim in (0.90, 1.0)
    if 20 * match >= 13 * max_len:
        return "near_miss", False  # sim in [0.65, 0.90]
    return "sub", False


def classify_pair(
    ref: str,
    hyp: str,
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> PhoneticMatch:
    """Classify one pair of normalized words (P3, P11)."""
    oov = not pron(ref) or not pron(hyp)
    if ref == hyp:
        return PhoneticMatch("equal", False, oov)  # P11: the same string is not a homophone
    if oov:
        return PhoneticMatch("sub", False, True)  # P3: OOV is never a near-miss
    best = _best_pair(ref, hyp, pron)
    if best is None:
        raise RuntimeError("unreachable: OOV already returned above")
    status, homophone = classify_sim(*best)
    return PhoneticMatch(status, homophone, False)


def pron_keys(
    word: str,
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> frozenset[tuple[str, ...]]:
    """Set of stress-free phoneme strings of `word`; OOV gives an empty frozenset.

    Used by alignment: two words are homophones <=> their sets overlap (ADR-005 P8 step 2).
    """
    return frozenset(tuple(_strip_stress(p)) for p in pron(word))
