import math
import numpy as np
import jiwer
import contractions
from num2words import num2words
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import parselmouth

from src.audio_processing.contracts import (
    WordTimestamp,
    ClassifiedPause,
    PauseKind,
    SttResult,
    SpeechSegment,
    MasterAudio,
    BaselineProfile
)

FILLER_WORD_LIST = {"uh", "um", "er", "ah", "like", "you know", "basically", "literally"}


def clamp(x: float) -> float:
    """Ép kết quả về khoảng 0.0 - 100.0[cite: 1, 2]."""
    return max(0.0, min(100.0, x))

def _normalize_word(word: str) -> str:
    """Chuyển chữ thường, bỏ dấu câu, bung dạng viết tắt, đổi số thành chữ[cite: 1, 2]."""
    w = word.lower().strip(".,;:?!")
    w = contractions.fix(w)
    if w.isdigit():
        try:
            w = num2words(w)
        except Exception:
            pass
    return w

def score_accuracy(ref_words: list[str], hyp_words: list[str]) -> float:
    """
    Tính điểm A: clamp(100 * (1 - error_rate))[cite: 2].
    (Lưu ý: Trong thực tế bạn sẽ dùng jiwer.process_words(ref, hyp) để lấy alignment 
    và loại trừ các lỗi do đồng âm, near-miss hoặc filler words khỏi phép tính error_rate)[cite: 1, 2].
    """
    ref_norm = [_normalize_word(w) for w in ref_words]
    hyp_norm = [_normalize_word(w) for w in hyp_words]
    
    # Base WER calculation. Khi tích hợp CMU dict, bạn sẽ custom lại logic đếm lỗi ở đây.
    error_rate = jiwer.wer(" ".join(ref_norm), " ".join(hyp_norm))
    return clamp(100.0 * (1.0 - error_rate))

def score_wpm(words: list[WordTimestamp]) -> tuple[float, float]:
    """
    Tính tốc độ đọc. Trả về (điểm_số, wpm_thực_tế) để lưu vào fluency_detail.
    """
    if len(words) < 2:
        return 0.0, 0.0
        
    duration_m = (words[-1].end_s - words[0].start_s) / 60.0
    wpm = len(words) / duration_m if duration_m > 0 else 0.0
    
    if 130 <= wpm <= 160:
        score = 100.0
    else:
        nearest_boundary = 130 if wpm < 130 else 160
        score = clamp(100.0 - 2.5 * abs(wpm - nearest_boundary))
        
    return score, wpm

def score_hesitation(classified_pauses: list[ClassifiedPause], duration_s: float) -> float:
    """
    Tính điểm ngắt nghỉ dựa trên số lần ngập ngừng / phút[cite: 1, 2].
    """
    if duration_s <= 0:
        return 0.0
        
    hesitation_count = sum(
        1 for cp in classified_pauses 
        if cp.kind in (PauseKind.HESITATION, PauseKind.FORGOT_WORD)
    )
    
    h_per_min = hesitation_count / (duration_s / 60.0)
    return clamp(100.0 - 20.0 * max(0, h_per_min - 1.0))

def score_filler(stt_result: SttResult, segments: list[SpeechSegment]) -> float:
    """
    Tính điểm từ đệm, kết hợp từ STT và các đoạn VAD có tiếng nhưng không khớp chữ[cite: 1, 2].
    """
    total_words = len(stt_result.words)
    if total_words == 0:
        return 0.0
        
    # 1. Đếm từ đệm STT trả về
    stt_fillers = [w for w in stt_result.words if _normalize_word(w.word) in FILLER_WORD_LIST]
    filler_count = len(stt_fillers)
    
    # 2. Đếm các đoạn VAD có tiếng nhưng không đè lên bất kỳ từ STT nào
    for seg in segments:
        seg_start = getattr(seg, 'start_s', 0.0)  # Giả định SpeechSegment có start_s và end_s
        seg_end = seg_start + seg.duration_s
        
        has_overlap = any(
            not (w.start_s >= seg_end or w.end_s <= seg_start)
            for w in stt_result.words
        )
        if not has_overlap:
            filler_count += 1
            
    r_pct = (filler_count / total_words) * 100.0
    return clamp(100.0 * (10.0 - r_pct) / 8.0)

def score_clarity(ref_words: list[str], hyp_words: list[str]) -> float:
    """
    Điểm độ rõ (P_clarity). Sẽ dựa vào near_miss_count khi ráp CMU dict[cite: 1, 2].
    """
    near_miss_count = 0  # Placeholder: số từ bị near-miss (tương đồng 0.65 - 0.90)
    r_nm = near_miss_count / len(ref_words) if ref_words else 0.0
    return clamp(100.0 * (1.0 - 5.0 * r_nm))

def score_pitch(master: MasterAudio, baseline: BaselineProfile | None) -> float:
    """
    Đo độ rộng cao độ (st) từ F0 contour bằng parselmouth[cite: 1, 2].
    """
    try:
        snd = parselmouth.Sound(master.samples, master.sample_rate)
        pitch = snd.to_pitch()
        f0_values = pitch.selected_array['frequency']
        
        # Chỉ lấy các frames có âm thanh
        f0_values = f0_values[f0_values > 0]
        
        if len(f0_values) == 0:
            return 0.0
            
        f0_ref = baseline.median_f0_hz if baseline and baseline.median_f0_hz else float(np.median(f0_values))
        
        st_values = 12.0 * np.log2(f0_values / f0_ref)
        r_st = np.percentile(st_values, 90) - np.percentile(st_values, 10)
        
        if r_st >= 6:
            return 100.0
        if r_st <= 2:
            return 0.0
        return 25.0 * (r_st - 2.0)
    except Exception:
        return 0.0

def score_semantic(ref_sentences: list[str], hyp_sentences: list[str]) -> float:
    """
    Đúng ý (S): Dùng SentenceTransformer để tính cosine similarity[cite: 1, 2].
    """
    if not ref_sentences or not hyp_sentences:
        return 0.0
        
    model = SentenceTransformer('all-MiniLM-L6-v2')
    ref_emb = model.encode(ref_sentences)
    hyp_emb = model.encode(hyp_sentences)
    
    passed = 0
    # Tính similarity cho từng cặp câu (giả định ref và hyp đã được gióng hàng 1-1)
    for r_vec, h_vec in zip(ref_emb, hyp_emb):
        sim = cosine_similarity([r_vec], [h_vec])[0][0]
        if sim >= 0.82:
            passed += 1
            
    return (passed / len(ref_sentences)) * 100.0

def compute_overall(a: float, f: float, p: float, s: float) -> float:
    """Điểm tổng theo trọng số đã chốt[cite: 1, 2]."""
    return 0.40 * a + 0.30 * f + 0.20 * p + 0.10 * s

def get_label(overall: float) -> str:
    """Nhãn xếp loại[cite: 1, 2]."""
    if overall >= 85: return "Excellent"
    if overall >= 70: return "Good"
    if overall >= 50: return "Need improvements"
    return "Need practice more"