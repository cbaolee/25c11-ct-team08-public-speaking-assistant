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
    WordTimestamp,
    ClassifiedPause,
    PauseKind,
    SpeechSegment,
    MasterAudio,
    BaselineProfile
)
from src.audio_processing.text_norm import is_filler, split_sentences

def clamp(x: float) -> float:
    """Ép kết quả về khoảng 0.0 - 100.0[cite: 1, 2]."""
    return max(0.0, min(100.0, x))

def _check_counts(**counts: int) -> None:
    for name, value in counts.items():
        if value < 0:
            raise ValueError(f"{name} không được âm: {value}")


def score_accuracy(n_ref: int, n_sub: int, n_del: int, n_ins: int) -> float | None:
    """Điểm A = clamp(100 * (1 - (n_sub + n_del + n_ins) / n_ref)) (ADR-003, scoring_framework §4).

    Nhận số đếm từ align(); near_miss và filler đã được alignment loại khỏi ba số này.
    n_ref = 0 -> None (phase3_decision #1); cờ "empty_script" do pipeline/accuracy_scores gắn.
    Số đếm âm -> ValueError (lỗi gọi hàm, không phải dữ liệu).
    """
    _check_counts(n_ref=n_ref, n_sub=n_sub, n_del=n_del, n_ins=n_ins)
    if n_ref == 0:
        return None
    return clamp(100.0 * (1.0 - (n_sub + n_del + n_ins) / n_ref))


def speech_span(words: Sequence[WordTimestamp]) -> tuple[int, float | None]:
    """Đo (n_words, span_s) trên các từ KHÔNG phải filler (D4; §5.1, §8).

    span_s = end_s của từ cuối - start_s của từ đầu (đầu vào đã sắp theo start_s).
    Dùng chung cho WPM và H nên hai chỉ số cùng mẫu số (D3).
    n_words < 2 hoặc span <= 0 -> span_s = None (mẫu số không xác định, D18).
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
    """F_wpm (§5.1): 130..160 -> 100; ngoài khoảng trừ 2.5 điểm/WPM từ biên gần nhất.

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
    """Trả (hesitation_count, forgot_word_count, H) (§5.2 Bước 4, D3, D17).

    hesitation_count gồm cả HESITATION và FORGOT_WORD (D17); PUNCTUATION và
    NATURAL không tính. H = hesitation_count / (span_s / 60); span_s None -> H None.
    """
    n_forgot = sum(1 for cp in classified if cp.kind is PauseKind.FORGOT_WORD)
    n_hes = n_forgot + sum(1 for cp in classified if cp.kind is PauseKind.HESITATION)
    if span_s is None or span_s <= 0:
        return n_hes, n_forgot, None
    return n_hes, n_forgot, n_hes / (span_s / 60.0)


def score_hesitation(h: float | None) -> float | None:
    """F_pause = clamp(100 - 20 * max(0, H - 1)) (§5.2 Bước 4). None -> None."""
    if h is None:
        return None
    return clamp(100.0 - 20.0 * max(0.0, h - 1.0))


@dataclass(frozen=True)
class FillerEvent:
    """Một filler tìm được; cùng trường với FillerItem trừ after_ref_index (pipeline tính)."""

    start_s: float
    end_s: float
    source: Literal["stt", "vad"]
    text: str | None  # chữ STT trả về; None nếu nguồn là VAD


def find_fillers(
    words: Sequence[WordTimestamp], segments: Sequence[SpeechSegment]
) -> list[FillerEvent]:
    """Liệt kê mọi filler theo thứ tự thời gian (§5.3). Nguồn logic duy nhất cho count_fillers.

    source "stt": từ STT là filler (text_norm.is_filler). source "vad": đoạn VAD không chồng lấn
    thời gian với BẤT KỲ từ STT nào (filler hay từ thường); mỗi đoạn đếm tối đa một lần. Đoạn
    đã chồng lấn filler STT nên không bị đếm lại.
    Chồng lấn = seg.start < w.end and w.start < seg.end (chạm mép không tính).
    GIỚI HẠN (TỰ CHỌN): một đoạn VAD dài vừa chứa từ thật vừa chứa tiếng "ừm"
    vẫn không được đếm.
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
    """Trả (n_stt, n_vad) (§5.3), đếm từ find_fillers để không có hai nguồn logic."""
    events = find_fillers(words, segments)
    n_stt = sum(1 for e in events if e.source == "stt")
    return n_stt, len(events) - n_stt


def filler_pct(n_filler: int, n_words: int) -> float | None:
    """R = n_filler / n_words * 100 (D5); n_words là số từ KHÔNG tính filler. 0 từ -> None."""
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
    """F = trung bình cộng 3 điểm con (§5); thiếu bất kỳ cái nào -> None (D18, §8)."""
    if f_wpm is None or f_pause is None or f_filler is None:
        return None
    return (f_wpm + f_pause + f_filler) / 3.0

def score_clarity(n_near_miss: int, n_ref: int) -> float | None:
    """P_clarity = clamp(100 * (1 - 5 * n_near_miss / n_ref)).

    Nguồn: ADR-005 "Hệ quả", scoring_framework §6.1.

    n_ref = 0 -> None. Số đếm âm -> ValueError. Hệ số 5 đã chốt, không đổi.
    """
    _check_counts(n_near_miss=n_near_miss, n_ref=n_ref)
    if n_ref == 0:
        return None
    return clamp(100.0 * (1.0 - 5.0 * n_near_miss / n_ref))


@dataclass(frozen=True)
class AccuracyScores:
    accuracy: float | None
    clarity: float | None
    # đủ 7 khoá ADR-004: n_ref, n_sub, n_del, n_ins, n_near_miss, n_homophone, n_oov
    accuracy_detail: dict
    flags: list[str]


def accuracy_scores(result: AlignmentResult) -> AccuracyScores:
    """Chấm A và P_clarity từ AlignmentResult; accuracy_detail là bản sao counts.

    flags = bản sao result.flags, thêm "empty_script" khi n_ref == 0 (phase3_decision #1).
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
    """Đổi độ rộng cao độ R_st (nửa cung) thành điểm P_pitch (scoring_framework.md §6.2).

    R_st >= 6 -> 100; R_st <= 2 -> 0; ở giữa 25 * (R_st - 2). None -> None
    (không đo được thì không chấm, §8; không coi là 0).
    """
    if r_st is None:
        return None
    if r_st >= 6:
        return 100.0
    if r_st <= 2:
        return 0.0
    return 25.0 * (r_st - 2.0)


def pitch_range_st(f0_hz: Sequence[float], f0_ref_hz: float) -> float | None:
    """R_st = P90 - P10 của ST = 12 * log2(F0 / F0_ref) (§6.2). Hàm thuần.

    Bỏ F0 <= 0 hoặc NaN (Praat trả 0 cho đoạn vô thanh). Không còn mẫu nào, hoặc
    f0_ref không hợp lệ (None, NaN, <= 0) -> None.

    GIẢ ĐỊNH (spec không nói): phân vị dùng numpy.percentile mặc định
    (nội suy linear). Chưa kiểm chứng ảnh hưởng của cách nội suy khác lên điểm.
    Còn đúng 1 mẫu hữu thanh -> P90 = P10 nên R_st = 0.0 (không phải None).
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


def _extract_f0(master: MasterAudio) -> list[float]:
    """Trích F0 hữu thanh (Hz, > 0) từ file bằng Parselmouth.

    Giữ nguyên tham số cũ (phase3 #19): Sound(path).to_pitch() mặc định.
    Tách riêng để test monkeypatch, không cần audio thật.
    """
    snd = parselmouth.Sound(str(master.path))
    pitch = snd.to_pitch()
    f0_values = pitch.selected_array["frequency"]
    return [float(v) for v in f0_values[f0_values > 0]]


def score_pitch(master: MasterAudio, baseline: BaselineProfile | None) -> PitchResult:
    """P_pitch (§6.2): F0_ref từ baseline nếu hợp lệ, không thì median F0 của phiên.

    Không gắn cờ no_baseline ở đây (pipeline gắn). Không có F0 hữu thanh hoặc
    Praat lỗi -> score None + flags ["no_f0"], không trả 0.0 (§8, ADR-004 D18).
    """
    try:
        f0 = [v for v in _extract_f0(master) if math.isfinite(v) and v > 0]
    except Exception:
        f0 = []
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
    return PitchResult(pitch_score_from_range(r_st), r_st, f0_ref, source, [])


def combine_pronunciation(clarity: float | None, pitch: float | None) -> float | None:
    """P = 0.5 * P_clarity + 0.5 * P_pitch; thiếu một trong hai -> None (§8)."""
    if clarity is None or pitch is None:
        return None
    return 0.5 * clarity + 0.5 * pitch


SEMANTIC_THRESHOLD = 0.82  # ADR-003 §7, không đổi

Encoder = Callable[[list[str]], np.ndarray]


@dataclass(frozen=True)
class SentenceResult:
    """Một câu kịch bản và kết quả so nghĩa; cùng trường với SentenceItem (ADR-004)."""

    index: int
    ref_text: str
    ref_start: int  # nửa mở [ref_start, ref_end)
    ref_end: int
    hyp_text: str | None
    cosine: float | None
    passed: bool | None


def build_sentence_pairs(
    script: str, items: Sequence[AlignedItem]
) -> list[tuple[int, int, int, str, str | None]]:
    """Ghép câu kịch bản với lời nói theo ALIGNMENT, không theo chỉ số (ADR-004 D8, §7).

    Trả [(index, ref_start, ref_end, ref_text, hyp_text)]. hyp_text của câu i = các hyp_word
    của item có sentence_index == i và status != "del", gồm cả ins (phase3 #2). Mỗi hyp_index
    chỉ lấy một lần (một từ STT như "it's" có thể được hai item dùng chung), sắp theo
    hyp_index, nối bằng dấu cách. Rỗng -> None (phase3 #3). Kịch bản rỗng -> [].

    Giới hạn đã biết: AlignedItem chỉ lưu hyp_index ĐẦU và hyp_word đã nối của item nhiều
    từ, nên khi ins xen giữa item đó thứ tự từ bị lệch (script "A 21 b.", STT "a twenty x
    one b" -> "a twenty one x b"). Ảnh hưởng nhỏ tới cosine; muốn sửa thì AlignedItem cần
    lưu danh sách hyp_index (không sửa ở đây).
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
    """Nạp all-MiniLM-L6-v2 lười, đúng một lần cho cả process (memoization).

    TỰ CHỌN: import sentence_transformers nằm trong hàm để `import scoring` không nạp torch.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(texts: list[str]) -> np.ndarray:
        return np.asarray(model.encode(texts), dtype=float)

    return encode


def _cosine(a: np.ndarray, b: np.ndarray) -> float | None:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return None  # TỰ CHỌN: vector 0 không có hướng -> không chấm được
    return float(np.dot(a, b) / (na * nb))


def score_sentences(
    pairs: Sequence[tuple[int, int, int, str, str | None]],
    *,
    encode: Encoder | None = None,
) -> list[SentenceResult]:
    """Tính cosine từng câu và passed = cosine >= 0.82 (§7).

    Chỉ encode các câu có hyp; không có câu nào có hyp thì không gọi encoder (kể cả
    _get_encoder). SentenceResult.cosine là số thô, không làm tròn (ADR-004 D1).
    passed = cosine >= 0.82 - 1e-9. Epsilon 1e-9 chỉ hấp thụ nhiễu float64 của phép chia;
    cosine nằm dưới 0.82 quá 1e-9 vẫn là không đạt (vd 0.8199996 -> False). Đây là TỰ CHỌN.
    Câu không có hyp (hoặc norm 0): cosine None, passed False, vẫn nằm trong danh sách.
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
    """S = 100 * (số câu passed) / (tổng số câu kịch bản) (§7). Không có câu -> None (#1)."""
    if not sentences:
        return None
    return 100.0 * sum(1 for s in sentences if s.passed) / len(sentences)


def compute_overall(
    a: float | None, f: float | None, p: float | None, s: float | None
) -> float | None:
    """Điểm tổng 0.4A + 0.3F + 0.2P + 0.1S (§3). Thiếu bất kỳ thành phần -> None.

    Không nội suy, không điền 0 (§8, ADR-004 D18).
    """
    if a is None or f is None or p is None or s is None:
        return None
    return 0.40 * a + 0.30 * f + 0.20 * p + 0.10 * s


def display_round(x: float | None) -> Decimal | None:
    """Làm tròn để HIỂN THỊ: 1 chữ số, half-up (§12, phase3 #15). None -> None.

    Vì sao không dùng round() hay Decimal(x): float 89.85 thực chất lưu là
    89.8499999..., nên round(89.85, 1) và Decimal(89.85).quantize(...) đều cho
    89.8. str(x) (repr Python từ 3.1) trả dạng thập phân NGẮN NHẤT mà khi đọc lại
    vẫn ra đúng float đó, tức "89.85"; Decimal("89.85") là số thập phân chính xác
    nên half-up cho 89.9.
    Nhưng str(x) vẫn mang nhiễu tích luỹ: compute_overall(83.5, 98.5, 70, 80) cho
    84.94999999999999 (thật ra 84.95) nên half-up ra 84.9 và nhãn "Good" thay vì
    "Excellent". Vì vậy làm tròn HAI bước: (1) quantize 1e-9 bằng HALF_EVEN để khử
    nhiễu float (sai số tích luỹ sau vài phép nhân cộng cỡ 1e-14, còn điểm trong
    [0, 100] không bao giờ cần chính xác 1e-9); (2) quantize 0.1 half-up.
    Giới hạn: giá trị nằm trong ~1e-9 quanh biên x.x5 bị coi như đúng x.x5.
    GIẢ ĐỊNH: số cần làm tròn là số "người đọc thấy", tức repr ngắn nhất.
    ADR-004 D1 giao việc làm tròn cho UI; bản JS cùng quy tắc thuộc Pha 5b.
    """
    if x is None:
        return None
    denoised = Decimal(str(x)).quantize(Decimal("1e-9"), rounding=ROUND_HALF_EVEN)
    return denoised.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def get_label(overall: float | None) -> str | None:
    """Nhãn xếp loại (§11), tính trên điểm đã display_round (phase3 #14)."""
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
