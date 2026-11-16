"""JSON contract of the v2 evaluation result (ADR-004), as Pydantic models.

Copied word for word from the ADR-004 schema: no defaults, validators or
``extra="forbid"`` (phase3_decision §3.2, §5 #7, §9). ``dict`` blocks stay
``dict``. A ``X | None`` field without a default MUST be passed
(``None`` is allowed). The only exception: ``AlignmentItem.homophone = False``
because ADR-004 itself says so.
"""

from typing import Literal

from pydantic import BaseModel


class AlignmentItem(BaseModel):
    status: Literal["equal", "near_miss", "sub", "del", "ins"]
    ref_index: int | None  # None for ins
    hyp_index: int | None  # None for del
    ref_word: str | None  # original token, punctuation kept
    hyp_word: str | None
    start_s: float | None  # None for del; never interpolated
    end_s: float | None  # the UI seeks to end_s of the nearest earlier item with timings
    sentence_index: int  # ins: sentence of the nearest earlier ref
    homophone: bool = False
    # Fillers are NOT in alignment.


class PauseItem(BaseModel):
    start_s: float
    end_s: float
    kind: Literal["punctuation", "natural", "hesitation", "forgot_word"]
    after_ref_index: int | None


class FillerItem(BaseModel):
    start_s: float
    end_s: float
    source: Literal["stt", "vad"]
    text: str | None
    after_ref_index: int | None


class SentenceItem(BaseModel):
    index: int
    ref_text: str
    ref_start: int  # ref_index, half-open [ref_start, ref_end)
    ref_end: int
    hyp_text: str | None
    cosine: float | None
    passed: bool | None


class Series(BaseModel):
    start_s: float
    step_s: float  # 0.1
    values: list[float | None]


class EvaluationResultV2(BaseModel):
    schema_version: Literal["2.1"]
    status: Literal["ok", "insufficient_audio"]
    reason: Literal["low_voiced_ratio", "empty_transcript"] | None
    overall: float | None  # null when any component is null (§8)
    label: Literal["Excellent", "Good", "Need improvements", "Need practice more"] | None
    components: dict  # {accuracy, fluency, pronunciation, semantic: float|None}
    subscores: dict  # {f_wpm, f_pause, f_filler, p_clarity, p_pitch: float|None}
    accuracy_detail: dict  # {n_ref, n_sub, n_del, n_ins, n_near_miss, n_homophone, n_oov}
    fluency_detail: dict  # {wpm, hesitations_per_min, hesitation_count, forgot_word_count,
    #  pause_threshold_s, filler_pct, filler_count}
    pitch_detail: dict  # {range_semitones, f0_ref_hz, f0_ref_source: "baseline"|"session",
    #  contour_st: Series|None}
    audio: dict  # {duration_s, voiced_ratio}
    baseline: dict | None  # {used, median_pause_s, hesitation_threshold_s}
    alignment: list[AlignmentItem]
    pauses: list[PauseItem]
    fillers: list[FillerItem]
    sentences: list[SentenceItem]
    stt: dict | None  # {provider, model}; None when rejected before STT
    flags: list[str]  # no_baseline, baseline_pause_unreliable, filler_from_vad_only, no_f0, cmu_oov
    warnings: list[str]
    display_only: dict  # {loudness_db: Series|None, loudness_ref_db: float|None}
    session_id: str | None = None
    saved: bool = False


class BaselineResponse(BaseModel):
    """`/api/baseline` response (ADR-004 D12): one JSON shape for both ok and insufficient_audio.

    OUR CHOICE: `profile` stays a dict (same rule as the dict blocks above);
    the ADR only says `profile | null`.
    """

    schema_version: Literal["2.0"]
    status: Literal["ok", "insufficient_audio"]
    reason: Literal["low_voiced_ratio", "empty_transcript"] | None
    profile: dict | None
    flags: list[str]
