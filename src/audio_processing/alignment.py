"""Two-level alignment (ADR-005 P8): level 1 aligns sub-tokens (align_tokens), level 2 classifies
near_miss and merges back to ref_index (align, P5)."""

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
    hyp_index: int  # position in the STT word list AFTER fillers are removed (D15)
    text: str  # normalized sub-token


@dataclass(frozen=True)
class TokenOp:
    op: Op
    ref_index: int | None  # None for ins
    ref_sub: str | None
    hyp_index: int | None  # None for del
    hyp_sub: str | None
    homophone: bool  # equal because the pronunciations match while the spelling differs


AlignStatus = Literal["equal", "near_miss", "sub", "del", "ins"]


@dataclass(frozen=True)
class AlignedItem:
    """Same fields and types as AlignmentItem (ADR-004); made Pydantic when assembled."""

    status: AlignStatus
    ref_index: int | None  # None for ins
    hyp_index: int | None  # None for del
    ref_word: str | None  # original token, punctuation kept
    hyp_word: str | None
    start_s: float | None  # None for del; never interpolated
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
    """Align the script with STT, then merge back to ref_index (ADR-005 P5, P8 steps 3-4, P10, P11).

    Each original token of script.split() has exactly one item that is not ins (D2); ins is counted
    per heard word (D16). Items follow the alignment path. Counts and flags: see AlignmentResult.
    """
    ref_tokens = normalize_script(script)
    kept = [w for w in words if not is_filler(w.word)]  # same filter as prepare_hyp (D15)
    ops = align_tokens(indexed_subtokens(ref_tokens), prepare_hyp(words), pron=pron)

    sentence_of = [0] * len(ref_tokens)
    for s, (a, b, _) in enumerate(split_sentences(script)):
        sentence_of[a:b] = [s] * (b - a)

    # Step A: walk the ops, collect sub-token statuses per ref_index, record the order they appear.
    entries: list[tuple[str, int]] = []  # ("ref", ref_index) or ("ins", hyp_index)
    acc: dict[int, tuple[list[str], set[int], list[bool]]] = {}  # r -> (statuses, hyp, [homo])
    ins_seen: set[int] = set()
    flushed: set[int] = set()
    pair_oov = False

    def flush_empty(idx: int) -> None:
        # A punctuation-only token has no op: place it right after the previous non-ins op.
        while idx < len(ref_tokens) and not ref_tokens[idx].subtokens:
            if idx not in flushed:
                flushed.add(idx)
                entries.append(("ref", idx))
            idx += 1

    flush_empty(0)
    for op in ops:
        if op.op == "ins":
            if op.hyp_index not in ins_seen:  # one hyp_index makes only one ins (D16, phase3 #8)
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
            m = classify_pair(op.ref_sub, op.hyp_sub, pron=pron)  # P8 step 3
            statuses.append(m.status)
            homo[0] = homo[0] or (m.status == "equal" and m.homophone)
            pair_oov = pair_oov or m.oov
        else:
            statuses.append("del")
        if op.hyp_index is not None:
            hyp_set.add(op.hyp_index)
        flush_empty(r + 1)

    # Step B: build the items in the order of entries.
    items: list[AlignedItem] = []
    cur_sentence = 0  # sentence of the nearest earlier ref (phase3 #10: 0 when there is none)
    for kind, idx in entries:
        if kind == "ins":
            w = kept[idx]
            items.append(
                AlignedItem("ins", None, idx, None, w.word, w.start_s, w.end_s, cur_sentence)
            )
            continue
        cur_sentence = sentence_of[idx]
        raw = ref_tokens[idx].raw
        if idx not in acc:  # no sub-tokens: equal, no hyp (Q1)
            items.append(AlignedItem("equal", idx, None, raw, None, None, None, cur_sentence))
            continue
        statuses, hyp_set, homo = acc[idx]
        if all(s == "del" for s in statuses):
            status: AlignStatus = "del"
        elif "sub" in statuses or "del" in statuses:  # has a sub, or only part of it is del (P5)
            status = "sub"
        elif "near_miss" in statuses:
            status = "near_miss"
        else:
            status = "equal"
        hs = sorted(hyp_set)
        if hs:
            first, last = kept[hs[0]], kept[hs[-1]]
            items.append(
                AlignedItem(
                    status,
                    idx,
                    hs[0],
                    raw,
                    " ".join(kept[h].word for h in hs),
                    first.start_s,
                    last.end_s,
                    cur_sentence,
                    status == "equal" and homo[0],
                )
            )
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
    """Drop fillers, number hyp_index 0,1,2... over the remaining words, normalize each word.

    A word that expands into several sub-tokens gives them the same hyp_index (phase3 #8).
    A word that normalizes to nothing ("—") makes no HypToken but still uses one hyp_index,
    so the index matches the position in the STT word list without fillers (D15).
    """
    kept = [w for w in words if not is_filler(w.word)]
    return [HypToken(idx, sub) for idx, w in enumerate(kept) for sub in normalize_token(w.word)]


def align_tokens(
    ref: Sequence[tuple[int, str]],
    hyp: Sequence[HypToken],
    *,
    pron: Callable[[str], list[list[str]]] = pronunciations,
) -> list[TokenOp]:
    """Token-level Levenshtein; a match = equal strings or overlapping pron_keys.

    Cost: match 0; sub, del, ins 1 each. Among paths with the same minimum cost, choose the one
    with the most equal steps (ADR-005 P8, clarified 11/11); if still tied, backtrack from (n, m)
    preferring equal > sub > del > ins in each cell. The result runs from start to end.
    """
    n, m = len(ref), len(hyp)

    keys: dict[str, frozenset[tuple[str, ...]]] = {}  # pron_keys computed once per word

    def keys_of(word: str) -> frozenset[tuple[str, ...]]:
        if word not in keys:
            keys[word] = pron_keys(word, pron=pron)
        return keys[word]

    # match[i-1][j-1] = 1 if ref[i-1] matches hyp[j-1] (same string or homophone).
    match = [bytearray(m) for _ in range(n)]
    for i in range(n):
        r = ref[i][1]
        for j in range(m):
            h = hyp[j].text
            match[i][j] = 1 if r == h or (keys_of(r) & keys_of(h)) else 0

    # D[i][j] = fewest edits that turn the first i ref tokens into the first j hyp tokens.
    # E[i][j] = most equal steps among paths that reach cost D[i][j]. Order by (cost, -n_eq).
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

    # Backtrack from (n, m); try equal, sub, del, ins in that order and take the first step whose
    # previous cell's (cost, n_eq) plus that step gives exactly the current cell's pair.
    ops: list[TokenOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and match[i - 1][j - 1]
            and d[i - 1][j - 1] == d[i][j]
            and e[i - 1][j - 1] + 1 == e[i][j]
        ):
            r, h = ref[i - 1], hyp[j - 1]
            ops.append(TokenOp("equal", r[0], r[1], h.hyp_index, h.text, r[1] != h.text))
            i, j = i - 1, j - 1
        elif (
            i > 0
            and j > 0
            and not match[i - 1][j - 1]
            and d[i - 1][j - 1] + 1 == d[i][j]
            and e[i - 1][j - 1] == e[i][j]
        ):
            r, h = ref[i - 1], hyp[j - 1]
            ops.append(TokenOp("sub", r[0], r[1], h.hyp_index, h.text, False))
            i, j = i - 1, j - 1
        elif i > 0 and d[i - 1][j] + 1 == d[i][j] and e[i - 1][j] == e[i][j]:
            r = ref[i - 1]
            ops.append(TokenOp("del", r[0], r[1], None, None, False))
            i -= 1
        else:  # ins: none of the branches above fits, so only this one is left
            h = hyp[j - 1]
            ops.append(TokenOp("ins", None, None, h.hyp_index, h.text, False))
            j -= 1
    ops.reverse()
    return ops
