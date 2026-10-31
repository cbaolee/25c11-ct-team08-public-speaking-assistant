from dataclasses import dataclass
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