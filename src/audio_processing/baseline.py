import statistics
import numpy as np
import parselmouth
from typing import Any

from src.audio_processing.contracts import (
    Pause,
    MasterAudio,
    BaselineProfile,
    InsufficientAudio
)
from src.audio_processing.vad import detect_speech, find_pauses, check_audio_quality


def compute_baseline_pause_profile(pauses: list[Pause]) -> dict:
    """
    Trích xuất trung vị khoảng lặng và ngưỡng ngập ngừng từ file baseline.
    Sử dụng start_s và end_s để tính độ dài.
    """
    if not pauses:
        return {
            "median_pause_s": None,
            "hesitation_threshold_s": 0.7,
            "flags": ["no_baseline"]
        }
    
    flags = []
    if len(pauses) < 5:
        flags.append("baseline_pause_unreliable")
        
    durations = [(p.end_s - p.start_s) for p in pauses]
    median_pause_s = statistics.median(durations)
    
    # Tính ngưỡng và chặn biên trong khoảng [0.7, 1.2]
    threshold = 2.0 * median_pause_s
    hesitation_threshold_s = max(0.7, min(1.2, threshold))
    
    return {
        "median_pause_s": median_pause_s,
        "hesitation_threshold_s": hesitation_threshold_s,
        "flags": flags
    }


def compute_baseline_f0(master: MasterAudio) -> dict:
    """
    Tính trung vị cao độ F0 (Hz) của baseline bằng Parselmouth.
    """
    flags = []
    median_f0_hz = None
    
    try:
        snd = parselmouth.Sound(str(master.path))
        pitch = snd.to_pitch()
        pitch_values = pitch.selected_array['frequency']
        
        # Chỉ lấy các frames có âm thanh (voiced), frequency > 0
        voiced_f0 = pitch_values[pitch_values > 0]
        
        if len(voiced_f0) > 0:
            median_f0_hz = float(np.median(voiced_f0))
        else:
            flags.append("no_f0")
    except Exception:
        flags.append("no_f0")
        
    return {
        "median_f0_hz": median_f0_hz,
        "flags": flags
    }


def build_baseline_profile(master: MasterAudio, vad_params: Any) -> BaselineProfile:
    """
    Orchestrator phân tích toàn bộ audio baseline và trả về BaselineProfile.
    """
    # 1. Phát hiện tiếng nói (Sử dụng keyword argument params=vad_params)
    segments = detect_speech(master, params=vad_params)
    
    # 2. Kiểm tra chất lượng (ném ngoại lệ InsufficientAudio nếu tiếng nói < 30%)
    check_audio_quality(segments, master.duration_s)
    
    # 3. Phân tích khoảng lặng (Sử dụng keyword argument min_pause_s=0.35)
    pauses = find_pauses(segments, min_pause_s=0.35)
    pause_profile = compute_baseline_pause_profile(pauses)
    
    # 4. Phân tích cao độ giọng
    f0_profile = compute_baseline_f0(master)
    
    # 5. Gộp flags
    combined_flags = pause_profile["flags"] + f0_profile["flags"]
    
    return BaselineProfile(
        median_pause_s=pause_profile["median_pause_s"],
        hesitation_threshold_s=pause_profile["hesitation_threshold_s"],
        median_f0_hz=f0_profile["median_f0_hz"],
        flags=combined_flags
    )