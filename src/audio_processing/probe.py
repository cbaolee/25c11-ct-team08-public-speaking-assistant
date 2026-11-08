import json
import subprocess
from pathlib import Path

from .contracts import AudioProbe, AudioRejected


def _run_ffprobe(path: Path, timeout_s: float = 10) -> dict:
    command = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        path
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_s
        )

        return json.loads(result.stdout)

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        raise AudioRejected("corrupt", "Could not read this audio file. It may be damaged; please try another file or record again.")


def probe(path: Path, *, max_seconds: float, max_bytes: int,
          allowed_formats: frozenset[str]) -> AudioProbe:
    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise AudioRejected("corrupt", "The audio file is empty. Please choose another file or record again.")
    elif size_bytes > max_bytes:
        raise AudioRejected("too_large", f"The file is too large (maximum {max_bytes // (1024 * 1024)} MB). Please choose a smaller file.")

    ffprobe_result = _run_ffprobe(path)
    audio_streams = [
        stream for stream in ffprobe_result.get("streams", []) 
        if stream.get("codec_type") == "audio"
    ]

    num_of_audio = len(audio_streams)

    if num_of_audio == 0:
        raise AudioRejected("no_audio_stream", "No audio was found in this file. Please check the file and try again.")
    elif num_of_audio > 1:
        raise AudioRejected("unsupported_format", "This file contains multiple audio tracks, which is not supported yet.")

    has_video = any(
        stream.get("codec_type") == "video"
        for stream in ffprobe_result.get("streams", [])
    )
    if has_video:
        raise AudioRejected("unsupported_format", "This file contains video or images. Please upload an audio-only file.")

    format_name_str = ffprobe_result.get("format", {}).get("format_name", "")
    actual_formats = format_name_str.split(",")

    is_valid_container = any(fmt in allowed_formats for fmt in actual_formats)

    if not is_valid_container:
        raise AudioRejected("unsupported_format", "This file format is not supported!")

    duration_s = None
    duration_str = ffprobe_result.get("format", {}).get("duration")
    if duration_str:
        try:
            duration_s = float(duration_str)
        except ValueError:
            duration_s = None
    if duration_s is not None and duration_s > max_seconds:
        raise AudioRejected("too_long", f"The recording is longer than the allowed limit ({max_seconds / 60:.0f} minutes). Please choose a shorter recording.")   

    stream = audio_streams[0]
    try:
        sample_rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
    except (KeyError, ValueError):
        raise AudioRejected("corrupt", "Could not read the audio properties of this file. Please try another file or record again.")     

    return AudioProbe(
        format_name=format_name_str,
        codec_name=stream.get("codec_name", ""),
        sample_rate=sample_rate,
        channels=channels,
        duration_s=duration_s,
        size_bytes=size_bytes,
    )