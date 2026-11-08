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
    median_pause_s: float         # trung vị khoảng lặng >= 0.35s của baseline
    hesitation_threshold_s: float # = min(1.2, 2 × median_pause_s)
    median_f0_hz: float           # median F0 từ Parselmouth
    flags: list[str]              # ["no_baseline", "baseline_pause_unreliable"]


class PauseKind(Enum):
    RHETORICAL = "rhetorical"     # nằm tại dấu câu trong script → không trừ điểm
    HESITATION = "hesitation"     # >= ngưỡng cá nhân, không tại dấu câu → trừ điểm
    FORGOT_WORD = "forgot_word"   # >= 1.2s giữa câu → chỉ hiển thị nhãn đỏ


@dataclass(frozen=True)
class ClassifiedPause:
    pause: Pause  
    kind: PauseKind


class InsufficientAudio(Exception):
    """Tiếng nói < 30% tổng thời lượng, hoặc STT trả về rỗng."""
    pass


@dataclass(frozen=True)
class EvaluationResult:
    status: str                     # "ok" | "insufficient_audio"
    overall: float | None           # 0–100 hoặc None
    label: str | None               # "Tốt" | "Khá" | "Cần cải thiện" | "Cần luyện thêm" | None
    components: dict                # {"accuracy": float|None, "fluency": float|None, "pronunciation": float|None, "semantic": float|None}
    fluency_detail: dict            # {"wpm": float, "hesitations_per_min": float, "pause_threshold_s": float, "filler_pct": float}
    pitch_detail: dict              # {"range_semitones": float|None, "f0_ref_hz": float|None}
    alignment: list[dict]           # [{"ref_word", "hyp_word", "status": "equal|near_miss|sub|del|ins"}]
    stt: dict                       # {"provider": str, "model": str}
    flags: list[str]
    display_only: dict              # {"loudness_db_timeline": list, ...}


@dataclass(frozen=True)
class VadParams:
    """Các tham số cấu hình cho Silero VAD."""
    threshold: float = 0.5
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 100
    window_size_samples: int = 512
    speech_pad_ms: int = 30