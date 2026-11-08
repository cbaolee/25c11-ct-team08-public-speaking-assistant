import shutil
import subprocess
from pathlib import Path

import pytest

from src.audio_processing import probe as probe_module
from src.audio_processing.contracts import AudioRejected
from src.audio_processing.probe import probe

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)

ALLOWED = frozenset({"wav", "matroska", "webm", "mov", "mp4"})
LIMITS = dict(max_seconds=1320, max_bytes=100 * 1024 * 1024, allowed_formats=ALLOWED)


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def _has_encoder(name: str) -> bool:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout
    return name in out


def _sine(freq: int, seconds: int, rate: int) -> str:
    return f"sine=frequency={freq}:duration={seconds}:sample_rate={rate}"


def _code(info) -> str:
    return info.value.code


@pytest.fixture
def ok_wav(tmp_path: Path) -> Path:
    out = tmp_path / "ok.wav"
    _ffmpeg("-f", "lavfi", "-i", _sine(220, 3, 16000), "-ac", "1", str(out))
    return out


@pytest.fixture
def nodur_webm(tmp_path: Path) -> Path:
    # Ghi ra pipe (không seek được) để header không có duration, giống MediaRecorder.
    if not _has_encoder("libopus"):
        pytest.skip("libopus encoder not available")
    out = tmp_path / "nodur.webm"
    with open(out, "wb") as f:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error",
             "-f", "lavfi", "-i", _sine(220, 3, 48000),
             "-ac", "2", "-c:a", "libopus", "-b:a", "32k", "-f", "webm", "pipe:1"],
            stdout=f, check=True,
        )
    return out


@pytest.fixture
def video_only_mp4(tmp_path: Path) -> Path:
    out = tmp_path / "video_only.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-c:v", "mpeg4", str(out))
    return out


@pytest.fixture
def two_audio_tracks(tmp_path: Path) -> Path:
    out = tmp_path / "two_tracks.mkv"
    _ffmpeg(
        "-f", "lavfi", "-i", _sine(220, 2, 16000),
        "-f", "lavfi", "-i", _sine(440, 2, 16000),
        "-map", "0", "-map", "1", "-c:a", "pcm_s16le", str(out),
    )
    return out


@pytest.fixture
def fake_mp3(tmp_path: Path) -> Path:
    out = tmp_path / "fake.mp3"
    out.write_text("this is not audio")
    return out


@pytest.fixture
def empty_file(tmp_path: Path) -> Path:
    out = tmp_path / "empty.wav"
    out.write_bytes(b"")
    return out


# ---------- trường hợp hợp lệ ----------

def test_valid_wav_returns_probe(ok_wav):
    result = probe(ok_wav, **LIMITS)
    assert result.sample_rate == 16000
    assert result.channels == 1
    assert result.duration_s == pytest.approx(3.0, abs=0.1)
    assert result.size_bytes == ok_wav.stat().st_size


def test_webm_without_duration_is_accepted(nodur_webm):
    result = probe(nodur_webm, **LIMITS)
    assert result.duration_s is None
    assert result.codec_name == "opus"


def test_empty_file_is_corrupt(empty_file):
    with pytest.raises(AudioRejected) as info:
        probe(empty_file, **LIMITS)
    assert _code(info) == "corrupt"


def test_file_too_large(ok_wav):
    with pytest.raises(AudioRejected) as info:
        probe(ok_wav, **{**LIMITS, "max_bytes": 10})
    assert _code(info) == "too_large"


def test_file_too_long(ok_wav):
    with pytest.raises(AudioRejected) as info:
        probe(ok_wav, **{**LIMITS, "max_seconds": 2})
    assert _code(info) == "too_long"


def test_fake_audio_file_is_corrupt(fake_mp3):
    with pytest.raises(AudioRejected) as info:
        probe(fake_mp3, **LIMITS)
    assert _code(info) == "corrupt"


def test_video_without_audio_is_rejected(video_only_mp4):
    with pytest.raises(AudioRejected) as info:
        probe(video_only_mp4, **LIMITS)
    assert _code(info) == "no_audio_stream"


def test_multiple_audio_tracks_rejected(two_audio_tracks):
    with pytest.raises(AudioRejected) as info:
        probe(two_audio_tracks, **LIMITS)
    assert _code(info) == "unsupported_format"


def test_container_not_in_whitelist(ok_wav):
    with pytest.raises(AudioRejected) as info:
        probe(ok_wav, **{**LIMITS, "allowed_formats": frozenset({"mp3"})})
    assert _code(info) == "unsupported_format"


def test_empty_ffprobe_output_is_rejected(ok_wav, monkeypatch):
    monkeypatch.setattr(probe_module, "_run_ffprobe", lambda path: {})
    with pytest.raises(AudioRejected) as info:
        probe(ok_wav, **LIMITS)
    assert _code(info) == "no_audio_stream"


def test_ffprobe_timeout_is_corrupt(ok_wav, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=10)

    monkeypatch.setattr(probe_module.subprocess, "run", fake_run)
    with pytest.raises(AudioRejected) as info:
        probe(ok_wav, **LIMITS)
    assert _code(info) == "corrupt"


@pytest.fixture
def mp4_with_video(tmp_path: Path) -> Path:
    out = tmp_path / "av.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2",
        "-f", "lavfi", "-i", _sine(220, 2, 44100),
        "-c:v", "mpeg4", "-c:a", "aac", str(out),
    )
    return out


@pytest.fixture
def mkv_with_video(tmp_path: Path) -> Path:
    out = tmp_path / "av.mkv"
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2",
        "-f", "lavfi", "-i", _sine(220, 2, 16000),
        "-c:v", "mpeg4", "-c:a", "pcm_s16le", str(out),
    )
    return out


@pytest.fixture
def mp3_with_cover_art(tmp_path: Path) -> Path:
    mp3 = tmp_path / "plain.mp3"
    png = tmp_path / "cover.png"
    out = tmp_path / "art.mp3"
    _ffmpeg("-f", "lavfi", "-i", _sine(220, 1, 44100), "-c:a", "libmp3lame", str(mp3))
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", str(png))
    _ffmpeg("-i", str(mp3), "-i", str(png), "-map", "0", "-map", "1",
            "-c", "copy", "-id3v2_version", "3", str(out))
    return out


@pytest.mark.parametrize("fixture_name", ["mp4_with_video", "mkv_with_video", "mp3_with_cover_art"])
def test_file_with_video_or_image_is_rejected(fixture_name, request):
    path = request.getfixturevalue(fixture_name)
    allowed = ALLOWED | {"mp3"}
    with pytest.raises(AudioRejected) as info:
        probe(path, **{**LIMITS, "allowed_formats": allowed})
    assert _code(info) == "unsupported_format"