import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Literal

import numpy as np
import parselmouth

from src.audio_processing.alignment import AlignedItem, AlignmentResult
from src.audio_processing.contracts import (
    BaselineProfile,
    ClassifiedPause,
    MasterAudio,
    PauseKind,
    SpeechSegment,
    WordTimestamp,
)
from src.audio_processing.text_norm import is_filler, split_sentences


def clamp(x: float) -> float:
    """Clamp the value to 0.0 - 100.0."""
    return max(0.0, min(100.0, x))


def _check_counts(**counts: int) -> None:
    for name, value in counts.items():
        if value < 0:
            raise ValueError(f"{name} must not be negative: {value}")


def score_accuracy(n_ref: int, n_sub: int, n_del: int, n_ins: int) -> float | None:
    """Score A = clamp(100 * (1 - (n_sub + n_del + n_ins) / n_ref)) (ADR-003, scoring_framework §4).

    Takes the counts from align(); alignment already keeps near_miss and fillers out of them.
    n_ref = 0 -> None (phase3_decision #1); pipeline/accuracy_scores sets "empty_script".
    Negative counts -> ValueError (a calling bug, not bad data).
    """
    _check_counts(n_ref=n_ref, n_sub=n_sub, n_del=n_del, n_ins=n_ins)
    if n_ref == 0:
        return None
    return clamp(100.0 * (1.0 - (n_sub + n_del + n_ins) / n_ref))


def speech_span(words: Sequence[WordTimestamp]) -> tuple[int, float | None]:
    """Measure (n_words, span_s) over the words that are NOT fillers (D4; §5.1, §8).

    span_s = end_s of the last word - start_s of the first (input already sorted by start_s).
    Shared by WPM and H so both use the same denominator (D3).
    n_words < 2 or span <= 0 -> span_s = None (undefined denominator, D18).
    """
    real = [w for w in words if not is_filler(w.word)]
    n_words = len(real)
    if n_words < 2:
        return n_words, None
    span_s = real[-1].end_s - real[0].start_s
    if span_s <= 0:
        return n_words, None
    return n_words, span_s


def compute_wpm(n_words: int, span_s: float | None) -> float | None:
    """WPM = n_words / (span_s / 60); span_s None -> None (§5.1)."""
    if span_s is None or span_s <= 0:
        return None
    return n_words / (span_s / 60.0)


def score_wpm(wpm: float | None) -> float | None:
    """F_wpm (§5.1): 130..160 -> 100; outside, minus 2.5 points per WPM from the nearest edge.

    None -> None.
    """
    if wpm is None:
        return None
    if 130 <= wpm <= 160:
        return 100.0
    boundary = 130 if wpm < 130 else 160
    return clamp(100.0 - 2.5 * abs(wpm - boundary))


def hesitations_per_min(
    classified: Sequence[ClassifiedPause], span_s: float | None
) -> tuple[int, int, float | None]:
    """Return (hesitation_count, forgot_word_count, H) (§5.2 step 4, D3, D17).

    hesitation_count includes both HESITATION and FORGOT_WORD (D17); PUNCTUATION and
    NATURAL are not counted. H = hesitation_count / (span_s / 60); span_s None -> H None.
    """
    n_forgot = sum(1 for cp in classified if cp.kind is PauseKind.FORGOT_WORD)
    n_hes = n_forgot + sum(1 for cp in classified if cp.kind is PauseKind.HESITATION)
    if span_s is None or span_s <= 0:
        return n_hes, n_forgot, None
    return n_hes, n_forgot, n_hes / (span_s / 60.0)


def score_hesitation(h: float | None) -> float | None:
    """F_pause = clamp(100 - 20 * max(0, H - 1)) (§5.2 step 4). None -> None."""
    if h is None:
        return None
    return clamp(100.0 - 20.0 * max(0.0, h - 1.0))


@dataclass(frozen=True)
class FillerEvent:
    """One filler found; same fields as FillerItem except after_ref_index (set by the pipeline)."""

    start_s: float
    end_s: float
    source: Literal["stt", "vad"]
    text: str | None  # text returned by STT; None when the source is VAD


def find_fillers(
    words: Sequence[WordTimestamp], segments: Sequence[SpeechSegment]
) -> list[FillerEvent]:
    """List every filler in time order (§5.3). The only logic behind count_fillers.

    source "stt": an STT word that is a filler (text_norm.is_filler). source "vad": a VAD
    segment that does not overlap in time with ANY STT word (filler or not); each segment
    counts at most once.
    A segment that overlaps an STT filler is therefore not counted again.
    Overlap = seg.start < w.end and w.start < seg.end (touching edges do not count).
    LIMIT (OUR CHOICE): a long VAD segment holding both real words and an "um"
    is still not counted.
    """
    events = [FillerEvent(w.start_s, w.end_s, "stt", w.word) for w in words if is_filler(w.word)]
    events += [
        FillerEvent(seg.start_s, seg.end_s, "vad", None)
        for seg in segments
        if not any(seg.start_s < w.end_s and w.start_s < seg.end_s for w in words)
    ]
    return sorted(events, key=lambda e: (e.start_s, e.end_s))


def count_fillers(
    words: Sequence[WordTimestamp], segments: Sequence[SpeechSegment]
) -> tuple[int, int]:
    """Return (n_stt, n_vad) (§5.3), counted from find_fillers so there is one logic only."""
    events = find_fillers(words, segments)
    n_stt = sum(1 for e in events if e.source == "stt")
    return n_stt, len(events) - n_stt


def filler_pct(n_filler: int, n_words: int) -> float | None:
    """R = n_filler / n_words * 100 (D5); n_words does NOT count fillers. 0 words -> None."""
    if n_words == 0:
        return None
    return n_filler / n_words * 100.0


def score_filler(r_pct: float | None) -> float | None:
    """F_filler = clamp(100 * (10 - R) / 8) (§5.3): R <= 2 -> 100, R >= 10 -> 0. None -> None."""
    if r_pct is None:
        return None
    return clamp(100.0 * (10.0 - r_pct) / 8.0)


def compute_fluency(
    f_wpm: float | None, f_pause: float | None, f_filler: float | None
) -> float | None:
    """F = mean of the 3 sub-scores (§5); any missing -> None (D18, §8)."""
    if f_wpm is None or f_pause is None or f_filler is None:
        return None
    return (f_wpm + f_pause + f_filler) / 3.0


def score_clarity(n_near_miss: int, n_ref: int) -> float | None:
    """P_clarity = clamp(100 * (1 - 5 * n_near_miss / n_ref)).

    Source: ADR-005 "Consequences", scoring_framework §6.1.

    n_ref = 0 -> None. Negative counts -> ValueError. The factor 5 is agreed, do not change it.
    """
    _check_counts(n_near_miss=n_near_miss, n_ref=n_ref)
    if n_ref == 0:
        return None
    return clamp(100.0 * (1.0 - 5.0 * n_near_miss / n_ref))


@dataclass(frozen=True)
class AccuracyScores:
    accuracy: float | None
    clarity: float | None
    # all 7 ADR-004 keys: n_ref, n_sub, n_del, n_ins, n_near_miss, n_homophone, n_oov
    accuracy_detail: dict
    flags: list[str]


def accuracy_scores(result: AlignmentResult) -> AccuracyScores:
    """Score A and P_clarity from an AlignmentResult; accuracy_detail is a copy of the counts.

    flags = copy of result.flags, plus "empty_script" when n_ref == 0 (phase3_decision #1).
    """
    c = result.counts
    flags = list(result.flags)
    if c["n_ref"] == 0:
        flags.append("empty_script")
    return AccuracyScores(
        accuracy=score_accuracy(c["n_ref"], c["n_sub"], c["n_del"], c["n_ins"]),
        clarity=score_clarity(c["n_near_miss"], c["n_ref"]),
        accuracy_detail=dict(c),
        flags=flags,
    )


def pitch_score_from_range(r_st: float | None) -> float | None:
    """Turn the pitch range R_st (semitones) into the score P_pitch (scoring_framework.md §6.2).

    R_st >= 6 -> 100; R_st <= 2 -> 0; in between 25 * (R_st - 2). None -> None
    (not measured means not scored, §8; never treated as 0).
    """
    if r_st is None:
        return None
    if r_st >= 6:
        return 100.0
    if r_st <= 2:
        return 0.0
    return 25.0 * (r_st - 2.0)


def pitch_range_st(f0_hz: Sequence[float], f0_ref_hz: float) -> float | None:
    """R_st = P90 - P10 of ST = 12 * log2(F0 / F0_ref) (§6.2). Pure function.

    Drops F0 <= 0 or NaN (Praat gives 0 for unvoiced frames). No sample left, or
    an invalid f0_ref (None, NaN, <= 0) -> None.

    ASSUMPTION (not in the spec): percentiles use the default numpy.percentile
    (linear interpolation). The effect of another interpolation on the score is not checked.
    Exactly 1 voiced sample -> P90 = P10, so R_st = 0.0 (not None).
    """
    if f0_ref_hz is None or not math.isfinite(f0_ref_hz) or f0_ref_hz <= 0:
        return None
    arr = np.asarray(f0_hz, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return None
    st = 12.0 * np.log2(arr / f0_ref_hz)
    return float(np.percentile(st, 90) - np.percentile(st, 10))


@dataclass(frozen=True)
class PitchResult:
    score: float | None
    range_semitones: float | None
    f0_ref_hz: float | None
    f0_ref_source: Literal["baseline", "session"] | None
    flags: list[str] = field(default_factory=list)
    contour_st: dict | None = None


def _extract_f0(master: MasterAudio) -> list[tuple[float, float]]:
    """Voiced F0 from the file with Parselmouth: [(time_s, f0_hz)], frames with hz > 0 only.

    Keeps the old settings (phase3 #19): default Sound(path).to_pitch().
    Kept separate so tests can monkeypatch it without real audio.
    """
    snd = parselmouth.Sound(str(master.path))
    pitch = snd.to_pitch()
    f0_values = pitch.selected_array["frequency"]
    times = pitch.xs()
    return [(float(t), float(v)) for t, v in zip(times, f0_values, strict=True) if v > 0]


def f0_contour_st(
    track: Sequence[tuple[float, float]],
    f0_ref_hz: float | None,
    duration_s: float,
    step_s: float = 0.1,
) -> dict | None:
    """Pitch contour Series in semitones relative to f0_ref (ADR-004 D10).

    Cell i covers [i*step, (i+1)*step); value = 12*log2(median(hz in the cell) / f0_ref); a cell
    with no voiced frame -> None. Never NaN/inf. Invalid ref/duration -> None.
    """
    if f0_ref_hz is None or not math.isfinite(f0_ref_hz) or f0_ref_hz <= 0:
        return None
    if not math.isfinite(duration_s) or duration_s <= 0:
        return None
    n = math.ceil(round(duration_s / step_s, 9))
    cells: list[list[float]] = [[] for _ in range(n)]
    for t, hz in track:
        if not (math.isfinite(t) and math.isfinite(hz)) or hz <= 0:
            continue
        i = math.floor(round(t / step_s, 9))  # same float guard as n
        if t >= 0 and i < n:
            cells[i].append(hz)
    values = [
        float(12.0 * math.log2(float(np.median(c)) / f0_ref_hz)) if c else None for c in cells
    ]
    return {"start_s": 0.0, "step_s": step_s, "values": values}


def compute_warnings(
    wpm: float | None, filler_pct: float | None, range_st: float | None
) -> list[str]:
    """Warnings that do not change the score (ADR-004 D7): wpm, filler, monotone; None skipped."""
    out: list[str] = []
    if wpm is not None:
        if wpm < 110:
            out.append("wpm_slow")
        elif wpm > 175:
            out.append("wpm_fast")
    if filler_pct is not None and filler_pct >= 4:
        out.append("filler_high")
    if range_st is not None and range_st < 4:
        out.append("monotone")
    return out


def score_pitch(master: MasterAudio, baseline: BaselineProfile | None) -> PitchResult:
    """P_pitch (§6.2): F0_ref from the baseline when valid, otherwise the session median F0.

    The no_baseline flag is not set here (the pipeline sets it). No voiced F0 or
    a Praat error -> score None + flags ["no_f0"], never 0.0 (§8, ADR-004 D18).
    """
    try:
        track = [(t, v) for t, v in _extract_f0(master) if math.isfinite(v) and v > 0]
    except Exception:
        track = []
    f0 = [v for _, v in track]
    if not f0:
        return PitchResult(None, None, None, None, ["no_f0"])

    base_f0 = baseline.median_f0_hz if baseline is not None else None
    if base_f0 is not None and math.isfinite(base_f0) and base_f0 > 0:
        f0_ref, source = float(base_f0), "baseline"
    else:
        f0_ref, source = float(np.median(f0)), "session"

    r_st = pitch_range_st(f0, f0_ref)
    if r_st is None:
        return PitchResult(None, None, None, None, ["no_f0"])
    contour = f0_contour_st(track, f0_ref, master.duration_s)
    return PitchResult(pitch_score_from_range(r_st), r_st, f0_ref, source, [], contour)


def combine_pronunciation(clarity: float | None, pitch: float | None) -> float | None:
    """P = 0.5 * P_clarity + 0.5 * P_pitch; either missing -> None (§8)."""
    if clarity is None or pitch is None:
        return None
    return 0.5 * clarity + 0.5 * pitch


SEMANTIC_THRESHOLD = 0.82  # ADR-003 §7, do not change

Encoder = Callable[[list[str]], np.ndarray]


@dataclass(frozen=True)
class SentenceResult:
    """One script sentence and its meaning check; same fields as SentenceItem (ADR-004)."""

    index: int
    ref_text: str
    ref_start: int  # half-open [ref_start, ref_end)
    ref_end: int
    hyp_text: str | None
    cosine: float | None
    passed: bool | None


def build_sentence_pairs(
    script: str, items: Sequence[AlignedItem]
) -> list[tuple[int, int, int, str, str | None]]:
    """Pair script sentences with the speech through the ALIGNMENT, not by index (ADR-004 D8, §7).

    Returns [(index, ref_start, ref_end, ref_text, hyp_text)]. hyp_text of sentence i = the hyp_word
    of items with sentence_index == i and status != "del", ins included (phase3 #2). Each hyp_index
    is taken once (one STT word such as "it's" can be shared by two items), sorted by
    hyp_index, joined with spaces. Empty -> None (phase3 #3). Empty script -> [].

    Known limit: AlignedItem keeps only the FIRST hyp_index and the joined hyp_word of a multi-word
    item, so an ins inside that item puts the words out of order (script "A 21 b.", STT "a twenty x
    one b" -> "a twenty one x b"). Small effect on the cosine; fixing it needs AlignedItem to
    store a list of hyp_index (not changed here).
    """
    by_sentence: dict[int, dict[int, str]] = {}
    for it in items:
        if it.status == "del" or it.hyp_index is None or it.hyp_word is None:
            continue
        by_sentence.setdefault(it.sentence_index, {}).setdefault(it.hyp_index, it.hyp_word)
    pairs: list[tuple[int, int, int, str, str | None]] = []
    for i, (start, end, text) in enumerate(split_sentences(script)):
        got = by_sentence.get(i, {})
        hyp = " ".join(got[k] for k in sorted(got)) or None
        pairs.append((i, start, end, text, hyp))
    return pairs


@lru_cache(maxsize=1)
def _get_encoder() -> Encoder:
    """Load all-MiniLM-L6-v2 lazily, exactly once per process (memoization).

    OUR CHOICE: sentence_transformers is imported here so `import scoring` does not load torch.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(texts: list[str]) -> np.ndarray:
        return np.asarray(model.encode(texts), dtype=float)

    return encode


def _cosine(a: np.ndarray, b: np.ndarray) -> float | None:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return None  # OUR CHOICE: a zero vector has no direction -> cannot be scored
    return float(np.dot(a, b) / (na * nb))


def score_sentences(
    pairs: Sequence[tuple[int, int, int, str, str | None]],
    *,
    encode: Encoder | None = None,
) -> list[SentenceResult]:
    """Cosine per sentence and passed = cosine >= 0.82 (§7).

    Only sentences with a hyp are encoded; when none has one the encoder is not called (not even
    _get_encoder). SentenceResult.cosine is the raw number, not rounded (ADR-004 D1).
    passed = cosine >= 0.82 - 1e-9. The 1e-9 epsilon only absorbs float64 noise from the division;
    a cosine more than 1e-9 below 0.82 still fails (e.g. 0.8199996 -> False). OUR CHOICE.
    A sentence without hyp (or with norm 0): cosine None, passed False, still in the list.
    """
    with_hyp = [p for p in pairs if p[4] is not None]
    cos_by_index: dict[int, float | None] = {}
    if with_hyp:
        enc = encode if encode is not None else _get_encoder()
        ref_emb = enc([p[3] for p in with_hyp])
        hyp_emb = enc([p[4] for p in with_hyp])
        for p, r, h in zip(with_hyp, ref_emb, hyp_emb, strict=True):
            c = _cosine(r, h)
            cos_by_index[p[0]] = None if c is None else float(c)
    results = []
    for idx, start, end, ref_text, hyp_text in pairs:
        c = cos_by_index.get(idx)
        passed = c is not None and c >= SEMANTIC_THRESHOLD - 1e-9
        results.append(SentenceResult(idx, ref_text, start, end, hyp_text, c, passed))
    return results


def score_semantic(sentences: Sequence[SentenceResult]) -> float | None:
    """S = 100 * (passed sentences) / (all script sentences) (§7). No sentence -> None (#1)."""
    if not sentences:
        return None
    return 100.0 * sum(1 for s in sentences if s.passed) / len(sentences)


def compute_overall(
    a: float | None, f: float | None, p: float | None, s: float | None
) -> float | None:
    """Overall score 0.4A + 0.3F + 0.2P + 0.1S (§3). Any component missing -> None.

    No interpolation, no 0 filled in (§8, ADR-004 D18).
    """
    if a is None or f is None or p is None or s is None:
        return None
    return 0.40 * a + 0.30 * f + 0.20 * p + 0.10 * s


def display_round(x: float | None) -> Decimal | None:
    """Round for DISPLAY: 1 decimal, half-up (§12, phase3 #15). None -> None.

    Why not round() or Decimal(x): the float 89.85 is really stored as
    89.8499999..., so round(89.85, 1) and Decimal(89.85).quantize(...) both give
    89.8. str(x) (Python repr since 3.1) gives the SHORTEST decimal that reads back
    as the same float, i.e. "89.85"; Decimal("89.85") is an exact decimal
    so half-up gives 89.9.
    But str(x) still carries accumulated noise: compute_overall(83.5, 98.5, 70, 80) gives
    84.94999999999999 (really 84.95), so half-up gives 84.9 and the label "Good" instead of
    "Excellent". So rounding takes TWO steps: (1) quantize to 1e-9 with HALF_EVEN to remove
    float noise (accumulated error after a few multiply-adds is about 1e-14, and scores in
    [0, 100] never need 1e-9 precision); (2) quantize to 0.1 half-up.
    Limit: values within ~1e-9 of an x.x5 edge are treated as exactly x.x5.
    ASSUMPTION: the number to round is the one "the reader sees", i.e. the shortest repr.
    ADR-004 D1 leaves rounding to the UI; the JS version with the same rule belongs to Phase 5b.
    """
    if x is None:
        return None
    denoised = Decimal(str(x)).quantize(Decimal("1e-9"), rounding=ROUND_HALF_EVEN)
    return denoised.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def get_label(overall: float | None) -> str | None:
    """Grade label (§11), computed on the display_round score (phase3 #14)."""
    r = display_round(overall)
    if r is None:
        return None
    if r >= 85:
        return "Excellent"
    if r >= 70:
        return "Good"
    if r >= 50:
        return "Need improvements"
    return "Need practice more"
