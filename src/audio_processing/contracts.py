from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any

MASTER_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioProbe:
    format_name: str
    codec_name: str
    sample_rate: str
    channels: int
    duration_s: float | None
    size_bytes: int


class AudioRejected(Exception):
    # code: "too_long" | "too_large" | "no_audio_stream"
    #       | "unsupported_format" | "corrupt"
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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
    word: str           # từ gốc từ STT (chưa normalize)
    start_s: float
    end_s: float
    confidence: float | None = None   # None nếu provider không trả về


@dataclass(frozen=True)
class SttResult:
    transcript: str               # toàn bộ văn bản
    words: list[WordTimestamp]    # mốc từng từ, đã sắp xếp theo start_s
    provider: str                 # "deepgram" | "gladia" | "faster_whisper"
    model: str                    # tên model cụ thể
    flags: list[str]              # ví dụ: ["filler_from_vad_only"]


@dataclass(frozen=True)
class BaselineProfile:
    median_pause_s: float | None  # trung vị khoảng lặng >= 0.35s; None nếu không có khoảng lặng (D12)
    hesitation_threshold_s: float # = min(1.2, 2 × median_pause_s); 0.7 nếu < 5 khoảng lặng (D13)
    median_f0_hz: float | None    # median F0 từ Parselmouth; None nếu không có F0 (D12)
    mean_loudness_db: float | None  # dB trung bình của baseline (D11); None nếu không đo được
    flags: list[str]              # ["no_baseline", "baseline_pause_unreliable"]


class PauseKind(Enum):
    PUNCTUATION = "punctuation"   # tại dấu câu trong script → không trừ điểm (D6)
    NATURAL = "natural"           # >= 0.35 s, < ngưỡng cá nhân, không tại dấu câu
    HESITATION = "hesitation"     # >= ngưỡng cá nhân, không tại dấu câu → trừ điểm
    FORGOT_WORD = "forgot_word"   # >= 1.2s giữa câu → chỉ hiển thị nhãn đỏ


@dataclass(frozen=True)
class ClassifiedPause:
    pause: Pause  
    kind: PauseKind
    after_ref_index: int | None = None  # ref_index của từ nghe được ngay trước pause (D6)


class InsufficientAudio(Exception):
    """Tiếng nói < 30% tổng thời lượng, hoặc STT trả về rỗng."""
    pass


@dataclass(frozen=True)
class VadParams:
    """Các tham số cấu hình cho Silero VAD."""
    threshold: float = 0.5
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 100
    window_size_samples: int = 512
    speech_pad_ms: int = 30