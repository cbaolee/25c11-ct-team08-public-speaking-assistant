from dataclasses import dataclass
from enum import Enum
from pathlib import Path

MASTER_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioProbe:
    format_name: str
    codec_name: str
    sample_rate: str
    channels: int
    duration_s: float | None
    size_bytes: int


class AudioRejectedError(Exception):
    # code: "too_long" | "too_short" | "too_large" | "no_audio_stream"
    #       | "unsupported_format" | "corrupt"
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


AudioRejected = AudioRejectedError


@dataclass(frozen=True)
class MasterAudio:
    path: Path
    duration_s: float
    warnings: list[str]


@dataclass(frozen=True)
class SpeechSegment:
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class Pause:
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class WordTimestamp:
    word: str           # word as returned by STT (not normalized)
    start_s: float
    end_s: float
    confidence: float | None = None   # None when the provider does not return it


@dataclass(frozen=True)
class SttResult:
    transcript: str               # full text
    words: list[WordTimestamp]    # per-word timings, sorted by start_s
    provider: str                 # "deepgram" | "gladia" | "faster_whisper"
    model: str                    # exact model name
    flags: list[str]              # for example ["filler_from_vad_only"]


@dataclass(frozen=True)
class BaselineProfile:
    median_pause_s: float | None  # median pause >= 0.35 s; None when there is no pause
    hesitation_threshold_s: float # = min(1.2, 2 × median_pause_s); 0.7 when < 5 pauses (D13)
    median_f0_hz: float | None    # median F0 from Parselmouth; None when there is no F0 (D12)
    mean_loudness_db: float | None  # mean dB of the baseline (D11); None when it cannot be measured
    flags: list[str]              # ["no_baseline", "baseline_pause_unreliable"]


class PauseKind(Enum):
    PUNCTUATION = "punctuation"   # at punctuation in the script -> no penalty (D6)
    NATURAL = "natural"           # >= 0.35 s, below the personal threshold, not at punctuation
    HESITATION = "hesitation"     # >= personal threshold, not at punctuation -> penalty
    FORGOT_WORD = "forgot_word"   # >= 1.2 s inside a sentence -> shown as a red label only


@dataclass(frozen=True)
class ClassifiedPause:
    pause: Pause
    kind: PauseKind
    after_ref_index: int | None = None  # ref_index of the word heard right before the pause (D6)


class InsufficientAudioError(Exception):
    """Speech is < 30% of the duration, or STT returned nothing."""
    pass


InsufficientAudio = InsufficientAudioError


class SttUnavailableError(Exception):
    """Every STT provider failed (network, timeout, HTTP error, bad response)."""
    pass


SttUnavailable = SttUnavailableError


@dataclass(frozen=True)
class VadParams:
    """Settings for Silero VAD."""
    threshold: float = 0.5
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 100
    window_size_samples: int = 512
    speech_pad_ms: int = 30
