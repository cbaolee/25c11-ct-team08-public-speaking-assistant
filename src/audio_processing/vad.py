import wave
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.audio_processing.alignment import AlignedItem
from src.audio_processing.contracts import (
    MASTER_SAMPLE_RATE,
    ClassifiedPause,
    InsufficientAudio,
    MasterAudio,
    Pause,
    PauseKind,
    SpeechSegment,
)
from src.audio_processing.text_norm import normalize_token, trailing_punct

# Clock tolerance between VAD and STT when finding "the word right before a pause". This is NOT a
# scoring threshold of ADR-003; it only absorbs the time offset between the two sources.
# Starting value, tune in M7.
WORD_PAUSE_TOLERANCE_S = 0.1


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
    for previous, following in zip(segments, segments[1:], strict=False):
        gap = round(following.start_s - previous.end_s, 6)  # float guard at the min_pause_s edge
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
            raise ValueError(
                "Expected 16 kHz mono 16-bit WAV, "
                f"got (rate, channels, bytes)={layout}"
            )
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
    Check the share of speech in the audio.
    Raise InsufficientAudio when speech is < 30% or there is no speech.
    """
    if not segments:
        raise InsufficientAudio("Speech < 30% of audio duration")

    # Total speech time from start_s and end_s
    total_speech = sum((seg.end_s - seg.start_s) for seg in segments)
    speech_ratio = total_speech / duration_s

    if speech_ratio < 0.30:
        raise InsufficientAudio(r"Speech < 30% of audio duration")


def after_ref_index(
    items: Sequence[AlignedItem], pause_start_s: float, ref_tokens: Sequence[str]
) -> int | None:
    """ref_index of the word heard right before the pause; None when no word comes before it.

    Candidates: items with a hyp (end_s not None; del excluded) and
    end_s <= pause_start_s + WORD_PAUSE_TOLERANCE_S (VAD/STT clock tolerance, not an
    ADR-003 scoring threshold; tuned in M7). Take the largest end_s; on a tie, the item that
    comes last in items. If that item is an ins (no ref_index), use the nearest earlier ref
    in items (phase3 #2), skipping items whose original token ref_tokens[ref_index] is only
    punctuation (normalize_token empty, e.g. "—"); del items still count.
    """
    best_pos = None
    for pos, item in enumerate(items):
        if item.end_s is None or item.end_s > pause_start_s + WORD_PAUSE_TOLERANCE_S:
            continue
        if best_pos is None or item.end_s >= items[best_pos].end_s:
            best_pos = pos
    if best_pos is None:
        return None
    for pos in range(best_pos, -1, -1):
        ref = items[pos].ref_index
        if ref is not None and normalize_token(ref_tokens[ref]) != ():
            return ref
    return None


def classify_pauses(
    pauses: list[Pause],
    items: Sequence[AlignedItem],
    script: str,
    *,
    hesitation_threshold_s: float,
    forgot_word_s: float = 1.2,
) -> list[ClassifiedPause]:
    """Classify every Pause (ADR-004 D6), keeping the count and input order.

    Priority: punctuation > forgot_word (>= forgot_word_s) > hesitation (>= threshold) > natural.
    "At punctuation" = token script.split()[after_ref_index] has a non-empty trailing_punct,
    so the same word with and without punctuation is told apart by position (1.9.2 #26).
    Edges are inclusive (>=).
    """
    ref_tokens = script.split()
    result = []
    for pause in pauses:
        ref = after_ref_index(items, pause.start_s, ref_tokens)
        at_punct = ref is not None and bool(trailing_punct(ref_tokens[ref]))
        duration = round(pause.end_s - pause.start_s, 6)  # float guard at the 0.7/1.2 edges
        if at_punct:
            kind = PauseKind.PUNCTUATION
        elif duration >= forgot_word_s:
            kind = PauseKind.FORGOT_WORD
        elif duration >= hesitation_threshold_s:
            kind = PauseKind.HESITATION
        else:
            kind = PauseKind.NATURAL
        result.append(ClassifiedPause(pause, kind, ref))
    return result
