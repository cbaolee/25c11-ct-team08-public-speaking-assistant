import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import string
 
from src.audio_processing.contracts import (
    MASTER_SAMPLE_RATE,
    MasterAudio,
    SpeechSegment,
    Pause,
    WordTimestamp,
    ClassifiedPause,
    PauseKind,
    InsufficientAudio
)


@dataclass(frozen=True)
class VadParams:
    threshold: float = 0.5
    min_speech_duration_ms: int = 250   
    min_silence_duration_ms: int = 100 
    speech_pad_ms: int = 30 


def find_pauses(segments: list[SpeechSegment], *, min_pause_s: float) -> list[Pause]:
    """The result are pause segments between speech segments
    Pause segments are pauses with duration >= min_pause_s
    Silent before first speech and after last speech are not pauses
    The input list of speech segment must be sorted
    """
    pauses = []
    for previous, following in zip(segments, segments[1:]):
        gap = following.start_s - previous.end_s
        if gap >= min_pause_s:
            pauses.append(Pause(start_s=previous.end_s, end_s=following.start_s))
    return pauses


@lru_cache(maxsize=1)
def _load_model():
    from silero_vad import load_silero_vad
 
    return load_silero_vad()
 
 
def _read_samples(path: Path):
    import numpy as np
    import torch
 
    with wave.open(str(path), "rb") as wav:
        layout = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
        if layout != (MASTER_SAMPLE_RATE, 1, 2):
            raise ValueError(f"Expected 16 kHz mono 16-bit WAV, got (rate, channels, bytes)={layout}")
        raw = wav.readframes(wav.getnframes())
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return torch.from_numpy(samples)
 
 
def detect_speech(master: MasterAudio, *, params: VadParams) -> list[SpeechSegment]:
    from silero_vad import get_speech_timestamps
 
    samples = _read_samples(master.path)
    raw = get_speech_timestamps(
        samples,
        _load_model(),
        threshold=params.threshold,
        sampling_rate=MASTER_SAMPLE_RATE,
        min_speech_duration_ms=params.min_speech_duration_ms,
        min_silence_duration_ms=params.min_silence_duration_ms,
        speech_pad_ms=params.speech_pad_ms,
    )
    return [
        SpeechSegment(start_s=item["start"] / MASTER_SAMPLE_RATE,
                      end_s=item["end"] / MASTER_SAMPLE_RATE)
        for item in raw
    ]


def check_audio_quality(segments: list[SpeechSegment], duration_s: float) -> None:
    """
    Kiểm tra tỉ lệ tiếng nói trong audio.
    Nếu tiếng nói < 30% hoặc không có tiếng nói, raise InsufficientAudio.
    """
    if not segments:
        raise InsufficientAudio("Speech < 30% of audio duration")
    
    # Tính tổng thời gian tiếng nói dựa trên start_s và end_s
    total_speech = sum((seg.end_s - seg.start_s) for seg in segments)
    speech_ratio = total_speech / duration_s
    
    if speech_ratio < 0.30:
        raise InsufficientAudio(r"Speech < 30% of audio duration")


def _normalize_word(word: str) -> str:
    """Chuẩn hóa từ: lowercase và bỏ dấu câu ở đuôi."""
    return word.lower().rstrip(string.punctuation)


def classify_pauses(
    pauses: list[Pause], 
    words: list[WordTimestamp], 
    script: str, 
    *, 
    hesitation_threshold_s: float
) -> list[ClassifiedPause]:
    """
    Phân loại mỗi Pause thành RHETORICAL, HESITATION, hoặc FORGOT_WORD.
    """
    if not pauses:
        return []

    # 1. Tìm vị trí dấu câu trong script (. , ; : ? !) và lấy các từ chứa nó
    punctuation_marks = {'.', ',', ';', ':', '?', '!'}
    script_punct_words = set()
    
    for token in script.split():
        if token and token[-1] in punctuation_marks:
            norm_token = _normalize_word(token)
            if norm_token:
                script_punct_words.add(norm_token)

    classified_pauses = []

    for pause in pauses:
        pause_duration = pause.end_s - pause.start_s
        
        # Tìm từ STT kết thúc ngay trước khoảng lặng (sai số nhỏ 0.1s)
        preceding_words = [w for w in words if w.end_s <= pause.start_s + 0.1]
        
        is_at_punctuation = False
        
        # 2. Kiểm tra xem từ ngay trước pause có nằm tại vị trí dấu câu không
        if preceding_words:
            last_word = _normalize_word(preceding_words[-1].word)
            if last_word in script_punct_words:
                is_at_punctuation = True

        # 3. Logic phân loại theo thứ tự ưu tiên
        if is_at_punctuation:
            classified_pauses.append(ClassifiedPause(pause, PauseKind.RHETORICAL))
            
        elif pause_duration >= 1.2:
            classified_pauses.append(ClassifiedPause(pause, PauseKind.FORGOT_WORD))
            
        elif pause_duration >= hesitation_threshold_s:
            classified_pauses.append(ClassifiedPause(pause, PauseKind.HESITATION))

    return classified_pauses