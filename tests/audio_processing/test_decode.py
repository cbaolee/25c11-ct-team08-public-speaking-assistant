import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from src.audio_processing import decode as decode_module
from src.audio_processing.contracts import AudioRejected
from src.audio_processing.decode import decode_to_master

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not installed",
)

LIMITS = dict(max_seconds=1320, cap_margin_s=10, timeout_s=60)


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def _has_encoder(name: str) -> bool:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout
    return name in out


def _sine(seconds: int, rate: int) -> str:
    return f"sine=frequency=220:duration={seconds}:sample_rate={rate}"


def _read_wav(path: Path):
    """Trả về (dữ liệu mẫu thô, tần số lấy mẫu, số kênh)."""
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()


def _code(info) -> str:
    return info.value.code


@pytest.fixture
def wav_16k_mono(tmp_path: Path) -> Path:
    out = tmp_path / "src.wav"
    _ffmpeg("-f", "lavfi", "-i", _sine(3, 16000), "-ac", "1", str(out))
    return out


@pytest.fixture
def webm_48k_stereo(tmp_path: Path) -> Path:
    if not _has_encoder("libopus"):
        pytest.skip("libopus encoder not available")
    out = tmp_path / "src.webm"
    _ffmpeg("-f", "lavfi", "-i", _sine(3, 48000),
            "-ac", "2", "-c:a", "libopus", "-b:a", "32k", str(out))
    return out


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    d = tmp_path / "work"
    d.mkdir()
    return d


def test_master_is_16k_mono(webm_48k_stereo, workdir):
    result = decode_to_master(webm_48k_stereo, workdir, **LIMITS)
    _, rate, channels = _read_wav(result.path)
    assert (rate, channels) == (16000, 1)


def test_duration_matches_source(webm_48k_stereo, workdir):
    result = decode_to_master(webm_48k_stereo, workdir, **LIMITS)
    assert result.duration_s == pytest.approx(3.0, abs=0.1)


def test_output_is_named_master_wav(wav_16k_mono, workdir):
    result = decode_to_master(wav_16k_mono, workdir, **LIMITS)
    assert result.path == workdir / "master.wav"
    assert result.path.exists()


def test_clean_file_has_no_warnings(wav_16k_mono, workdir):
    result = decode_to_master(wav_16k_mono, workdir, **LIMITS)
    assert result.warnings == []


def test_samples_unchanged_when_source_is_already_16k_mono(wav_16k_mono, workdir):
    result = decode_to_master(wav_16k_mono, workdir, **LIMITS)
    master_samples, _, _ = _read_wav(result.path)
    source_samples, _, _ = _read_wav(wav_16k_mono)
    assert master_samples == source_samples


def test_decode_is_deterministic(webm_48k_stereo, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    a = decode_to_master(webm_48k_stereo, first, **LIMITS)
    b = decode_to_master(webm_48k_stereo, second, **LIMITS)
    assert a.path.read_bytes() == b.path.read_bytes()


def test_too_long_is_detected_through_duration_cap(wav_16k_mono, workdir):
    # Nguồn 3 giây, giới hạn 1 giây, trần -t = 2 giây. Master dài 2 giây > 1 giây.
    with pytest.raises(AudioRejected) as info:
        decode_to_master(wav_16k_mono, workdir,
                         max_seconds=1, cap_margin_s=1, timeout_s=60)
    assert _code(info) == "too_long"


def test_truncated_file_is_flagged_not_rejected(webm_48k_stereo, workdir, tmp_path):
    cut = tmp_path / "cut.webm"
    cut.write_bytes(webm_48k_stereo.read_bytes()[:3000])
    result = decode_to_master(cut, workdir, **LIMITS)
    assert result.warnings                    # có cảnh báo của ffmpeg
    assert result.duration_s < 3.0            # chỉ giải mã được một phần


def test_fake_audio_file_is_corrupt(workdir, tmp_path):
    fake = tmp_path / "fake.mp3"
    fake.write_text("this is not audio")
    with pytest.raises(AudioRejected) as info:
        decode_to_master(fake, workdir, **LIMITS)
    assert _code(info) == "corrupt"


def test_video_without_audio_is_corrupt(workdir, tmp_path):
    video = tmp_path / "video_only.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-c:v", "mpeg4", str(video))
    with pytest.raises(AudioRejected) as info:
        decode_to_master(video, workdir, **LIMITS)
    assert _code(info) == "corrupt"


def test_ffmpeg_timeout_is_corrupt(wav_16k_mono, workdir, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=60)

    monkeypatch.setattr(decode_module.subprocess, "run", fake_run)
    with pytest.raises(AudioRejected) as info:
        decode_to_master(wav_16k_mono, workdir, **LIMITS)
    assert _code(info) == "corrupt"


def test_zero_frame_output_is_corrupt(wav_16k_mono, workdir, monkeypatch):
    # ffmpeg "thành công" nhưng chỉ ghi ra WAV không có khung nào.
    def fake_run(command, **kwargs):
        with wave.open(str(workdir / "master.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(decode_module.subprocess, "run", fake_run)
    with pytest.raises(AudioRejected) as info:
        decode_to_master(wav_16k_mono, workdir, **LIMITS)
    assert _code(info) == "corrupt"