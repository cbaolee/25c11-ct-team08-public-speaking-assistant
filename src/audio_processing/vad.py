import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
 
from .contracts import MASTER_SAMPLE_RATE, MasterAudio, Pause, SpeechSegment


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