from dataclasses import dataclass


@dataclass(frozen=True)
class AudioProbe:
    format_name: str
    codec_name: str
    sample_rate: str
    channels: int
    duration_s: float | None
    size_bytes: str


class AudioRejected(Exception):
    # code: "too_long" | "too_large" | "no_audio_stream"
    #       | "unsupported_format" | "corrupt"
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message