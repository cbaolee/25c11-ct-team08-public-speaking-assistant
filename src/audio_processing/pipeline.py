import tempfile
import parselmouth
import numpy as np
from pathlib import Path
from typing import Any

# Import cấu hình thực tế của bạn
from src.app.config import (
    settings, 
    max_audio_seconds, 
    max_upload_bytes, 
    allowed_formats,
    decode_timeout_s, 
    duration_cap_margin_s,
    MIN_PAUSE_S
)

from src.audio_processing.contracts import (
    EvaluationResult, BaselineProfile, InsufficientAudio, PauseKind, AudioRejected
)
from src.audio_processing.probe import probe
from src.audio_processing.decode import decode_to_master
from src.audio_processing.vad import detect_speech, find_pauses, check_audio_quality, classify_pauses
from src.audio_processing.stt import transcribe
from src.audio_processing.baseline import compute_baseline_pause_profile, compute_baseline_f0
from src.audio_processing.scoring import (
    score_accuracy, score_wpm, score_hesitation, score_filler, 
    score_clarity, score_pitch, score_semantic, compute_overall, get_label,
    _normalize_word, FILLER_WORD_LIST
)

def evaluate_session(
    audio_path: Path, 
    script: str, 
    baseline: BaselineProfile | None, 
    *, 
    vad_params: Any
) -> EvaluationResult:
    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)
        
        try:
            # Sử dụng hằng số import từ config.py
            probe(
                audio_path,
                max_seconds=max_audio_seconds,
                max_bytes=max_upload_bytes,
                allowed_formats=frozenset(allowed_formats)  # Ép kiểu set theo prototype
            )
            
            master = decode_to_master(
                audio_path,
                workdir=workdir,
                max_seconds=max_audio_seconds,
                cap_margin_s=duration_cap_margin_s,
                timeout_s=decode_timeout_s
            )
            
            segments = detect_speech(master, params=vad_params)
            check_audio_quality(segments, master.duration_s)
            
            # settings object có chứa deepgram_api_key và gladia_api_key
            stt_result = transcribe(master, settings=settings)
            
            pauses = find_pauses(segments, min_pause_s=MIN_PAUSE_S)
            
            hes_threshold = baseline.hesitation_threshold_s if baseline else 0.7
            classified_pauses = classify_pauses(
                pauses, stt_result.words, script, hesitation_threshold_s=hes_threshold
            )
            
            script_words = script.split()
            stt_words = [w.word for w in stt_result.words]
            
            score_a = score_accuracy(script_words, stt_words)
            
            s_wpm, wpm_val = score_wpm(stt_result.words)
            s_hes = score_hesitation(classified_pauses, master.duration_s)
            s_fil = score_filler(stt_result, segments)
            score_f = (s_wpm + s_hes + s_fil) / 3.0
            
            s_clarity = score_clarity(script_words, stt_words)
            s_pitch = score_pitch(master, baseline)
            score_p = (s_clarity + s_pitch) / 2.0
            
            ref_sentences = [s.strip() for s in script.replace('?', '.').replace('!', '.').split('.') if s.strip()]
            hyp_sentences = [s.strip() for s in stt_result.transcript.replace('?', '.').replace('!', '.').split('.') if s.strip()]
            score_s = score_semantic(ref_sentences, hyp_sentences)
            
            overall = compute_overall(score_a, score_f, score_p, score_s)
            label = get_label(overall)
            
            loudness_db_timeline = []
            try:
                snd = parselmouth.Sound(str(master.path))
                intensity = snd.to_intensity()
                for t in np.arange(0, master.duration_s, 0.5):
                    db = intensity.get_value(t)
                    if not np.isnan(db):
                        loudness_db_timeline.append({"time_s": t, "db": float(db)})
            except Exception:
                pass

            flags = stt_result.flags[:]
            if not baseline:
                flags.append("no_baseline")
                
            hes_count = sum(1 for p in classified_pauses if p.kind in (PauseKind.HESITATION, PauseKind.FORGOT_WORD))
            stt_fillers = [w for w in stt_result.words if _normalize_word(w.word) in FILLER_WORD_LIST]

            return EvaluationResult(
                status="ok", overall=overall, label=label,
                components={"accuracy": score_a, "fluency": score_f, "pronunciation": score_p, "semantic": score_s},
                fluency_detail={"wpm": wpm_val, "hesitations_per_min": hes_count / (master.duration_s / 60.0) if master.duration_s > 0 else 0.0, "pause_threshold_s": hes_threshold, "filler_pct": (len(stt_fillers) / len(stt_words) * 100.0) if stt_words else 0.0},
                pitch_detail={"range_semitones": None, "f0_ref_hz": baseline.median_f0_hz if baseline else None},
                alignment=[], stt={"provider": stt_result.provider, "model": stt_result.model},
                flags=flags, display_only={"loudness_db_timeline": loudness_db_timeline}
            )
            
        except InsufficientAudio:
            return EvaluationResult(
                status="insufficient_audio", overall=None, label=None,
                components={"accuracy": None, "fluency": None, "pronunciation": None, "semantic": None},
                fluency_detail={"wpm": 0.0, "hesitations_per_min": 0.0, "pause_threshold_s": 0.0, "filler_pct": 0.0},
                pitch_detail={"range_semitones": None, "f0_ref_hz": None},
                alignment=[], stt={}, flags=[], display_only={}
            )


def analyze_baseline(
    audio_path: Path, 
    *,
    vad_params: Any
) -> BaselineProfile:
    """
    Dành riêng cho việc phân tích file ghi âm giọng baseline mẫu.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = Path(temp_dir)
        
        probe(
            audio_path,
            max_seconds=max_audio_seconds,
            max_bytes=max_upload_bytes,
            allowed_formats=frozenset(allowed_formats)
        )
        
        master = decode_to_master(
            audio_path,
            workdir=workdir,
            max_seconds=max_audio_seconds,
            cap_margin_s=duration_cap_margin_s,
            timeout_s=decode_timeout_s
        )
        
        segments = detect_speech(master, params=vad_params)
        check_audio_quality(segments, master.duration_s)
        
        pauses = find_pauses(segments, min_pause_s=0.35)
        pause_profile = compute_baseline_pause_profile(pauses)
        
        f0_profile = compute_baseline_f0(master)
        
        combined_flags = pause_profile["flags"] + f0_profile["flags"]
        
        return BaselineProfile(
            median_pause_s=pause_profile["median_pause_s"],
            hesitation_threshold_s=pause_profile["hesitation_threshold_s"],
            median_f0_hz=f0_profile["median_f0_hz"],
            flags=combined_flags
        )