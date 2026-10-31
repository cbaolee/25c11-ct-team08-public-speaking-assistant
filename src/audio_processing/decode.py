from pathlib import Path
import subprocess
import wave

from .contracts import MasterAudio, AudioRejected


def decode_to_master(src: Path, workdir: Path, *, max_seconds: float,
                     cap_margin_s: float, timeout_s: float) -> MasterAudio:
    out_path = workdir / "master.wav"

    command = [
        "ffmpeg", "-nostdin", "-v",
        "error", "-i", src, "-map",
        "0:a:0", "-vn", "-ac", "1",
        "-ar", "16000", "-c:a", "pcm_s16le",
        "-t", str(max_seconds + cap_margin_s),
        "-y", out_path
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_s
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        raise AudioRejected("corrupt", "Could not decode this audio file. It may be damaged; please try another file or record again.")

    try:
        with wave.open(str(out_path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
    except (wave.Error, EOFError, FileNotFoundError):
        raise AudioRejected("corrupt", "Could not decode this audio file. It may be damaged; please try another file or record again.")

    if frames == 0 or rate == 0:
        raise AudioRejected("corrupt", "No audio could be decoded from this file. Please try another file or record again.")

    duration_s = frames / rate
    if duration_s > max_seconds:
        raise AudioRejected("too_long", f"The recording is longer than the allowed limit ({max_seconds / 60:.0f} minutes). Please choose a shorter recording.")

    warnings = [line for line in result.stderr.splitlines() if line.strip()]
    return MasterAudio(path=out_path, duration_s=duration_s, warnings=warnings)