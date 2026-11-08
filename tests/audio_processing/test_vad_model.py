import struct
import wave
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("numpy")
silero_vad = pytest.importorskip("silero_vad")

from src.audio_processing import vad as vad_module
from src.audio_processing.contracts import MasterAudio, SpeechSegment
from src.audio_processing.vad import VadParams, _read_samples, detect_speech


def _write_wav(path: Path, samples: list[int], *, rate=16000, channels=1) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def _master(path: Path, duration_s: float) -> MasterAudio:
    return MasterAudio(path=path, duration_s=duration_s, warnings=[])


def test_read_samples_scales_int16_to_unit_range(tmp_path):
    wav = _write_wav(tmp_path / "m.wav", [0, 16384, -32768])
    samples = _read_samples(wav)
    assert samples.dtype == torch.float32
    assert samples.tolist() == [0.0, 0.5, -1.0]


@pytest.mark.parametrize("rate, channels", [(44100, 1), (16000, 2)])
def test_read_samples_rejects_wrong_format(tmp_path, rate, channels):
    wav = _write_wav(tmp_path / "m.wav", [0] * 100, rate=rate, channels=channels)
    with pytest.raises(ValueError):
        _read_samples(wav)


def test_silence_has_no_speech(tmp_path):
    wav = _write_wav(tmp_path / "m.wav", [0] * (16000 * 3))
    assert detect_speech(_master(wav, 3.0), params=VadParams()) == []


def test_detect_speech_converts_samples_to_seconds_and_passes_params(tmp_path, monkeypatch):
    wav = _write_wav(tmp_path / "m.wav", [0] * 16000)
    seen = {}

    def fake_get_speech_timestamps(audio, model, **kwargs):
        seen.update(kwargs)
        return [{"start": 16000, "end": 40000}, {"start": 48000, "end": 56000}]

    monkeypatch.setattr(silero_vad, "get_speech_timestamps", fake_get_speech_timestamps)
    params = VadParams(threshold=0.4, min_speech_duration_ms=200,
                       min_silence_duration_ms=150, speech_pad_ms=10)
    result = detect_speech(_master(wav, 1.0), params=params)

    assert result == [SpeechSegment(1.0, 2.5), SpeechSegment(3.0, 3.5)]
    assert seen["threshold"] == 0.4
    assert seen["min_speech_duration_ms"] == 200
    assert seen["min_silence_duration_ms"] == 150
    assert seen["speech_pad_ms"] == 10
    assert not seen.get("return_seconds", False)


def test_model_is_loaded_only_once():
    vad_module._load_model.cache_clear()
    first = vad_module._load_model()
    second = vad_module._load_model()
    assert first is second