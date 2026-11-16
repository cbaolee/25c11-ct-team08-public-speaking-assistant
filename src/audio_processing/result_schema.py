"""Hợp đồng JSON kết quả đánh giá v2 (ADR-004), model Pydantic.

Chép nguyên văn schema ADR-004: không thêm default, validator hay
``extra="forbid"`` (phase3_decision §3.2, §5 #7, §9). Các khối ``dict`` giữ là
``dict``. Trường ``X | None`` không có default là trường BẮT BUỘC truyền
(có thể truyền ``None``). Ngoại lệ duy nhất: ``AlignmentItem.homophone = False``
vì chính ADR-004 viết như vậy.
"""

from typing import Literal

from pydantic import BaseModel


class AlignmentItem(BaseModel):
    status: Literal["equal", "near_miss", "sub", "del", "ins"]
    ref_index: int | None  # None nếu ins
    hyp_index: int | None  # None nếu del
    ref_word: str | None  # token gốc, giữ dấu câu
    hyp_word: str | None
    start_s: float | None  # None nếu del; không nội suy
    end_s: float | None  # UI tua tới end_s của item có mốc liền trước
    sentence_index: int  # ins: câu của ref gần nhất phía trước
    homophone: bool = False
    # Filler KHÔNG nằm trong alignment.


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
    ref_start: int  # ref_index, nửa mở [ref_start, ref_end)
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
    overall: float | None  # null nếu bất kỳ thành phần nào null (§8)
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
    stt: dict | None  # {provider, model}; None nếu bị loại trước STT
    flags: list[str]  # no_baseline, baseline_pause_unreliable, filler_from_vad_only, no_f0, cmu_oov
    warnings: list[str]
    display_only: dict  # {loudness_db: Series|None, loudness_ref_db: float|None}
    session_id: str | None = None
    saved: bool = False


class BaselineResponse(BaseModel):
    """Phản hồi `/api/baseline` (ADR-004 D12): một dạng JSON cho cả ok và insufficient_audio.

    TỰ CHỌN: `profile` để dạng dict (cùng nguyên tắc với các khối dict ở trên);
    ADR chỉ ghi `profile | null`.
    """

    schema_version: Literal["2.0"]
    status: Literal["ok", "insufficient_audio"]
    reason: Literal["low_voiced_ratio", "empty_transcript"] | None
    profile: dict | None
    flags: list[str]
