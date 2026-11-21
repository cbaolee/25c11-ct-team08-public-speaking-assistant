"""Input limits: practice script length (/api/evaluate) and baseline length (10-60 s)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.app import main
from src.app.config import baseline_max_seconds, baseline_min_seconds, max_script_words
from src.audio_processing.contracts import AudioRejected, VadParams
from src.audio_processing.pipeline import analyze_baseline


def _evaluate(monkeypatch, script: str):
    called: dict[str, bool] = {}

    def fake_evaluate(audio_path, script, baseline, *, vad_params, **callbacks):
        called["yes"] = True
        raise AudioRejected("corrupt", "stop here")

    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main, "evaluate_session", fake_evaluate)
    client = TestClient(main.app)
    r = client.post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"RIFF", "audio/wav")},
        data={"script": script},
    )
    if r.status_code == 202:
        r = client.get(f"/api/evaluate/{r.json()['job_id']}")
        assert r.json()["status"] == "failed"
    return r, called


@pytest.mark.parametrize("script", [" ", "\n\t "])
def test_blank_script_is_rejected_before_scoring(monkeypatch, script):
    r, called = _evaluate(monkeypatch, script)
    assert r.status_code == 422
    assert r.json()["error_code"] == "script_empty"
    assert not called


def test_script_over_word_limit_is_rejected(monkeypatch):
    r, called = _evaluate(monkeypatch, "word " * (max_script_words + 1))
    assert r.status_code == 422
    assert r.json()["error_code"] == "script_too_long"
    assert not called


def test_script_at_word_limit_is_accepted(monkeypatch):
    r, called = _evaluate(monkeypatch, "word " * max_script_words)
    assert r.status_code == 200  # job reached the fake pipeline
    assert r.json()["error_code"] == "corrupt"
    assert called


def test_script_with_huge_tokens_is_rejected(monkeypatch):
    r, _ = _evaluate(monkeypatch, "x" * 50_000)
    assert r.json()["error_code"] == "script_too_long"


needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


def _tone(path: Path, seconds: float) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:duration={seconds}:sample_rate=16000",
            "-ac",
            "1",
            str(path),
        ],
        check=True,
    )
    return path


@needs_ffmpeg
def test_baseline_shorter_than_min_is_rejected(tmp_path):
    audio = _tone(tmp_path / "short.wav", baseline_min_seconds - 5)
    with pytest.raises(AudioRejected) as err:
        analyze_baseline(audio_path=audio, vad_params=VadParams())
    assert err.value.code == "too_short"


@needs_ffmpeg
def test_baseline_longer_than_max_is_rejected(tmp_path):
    audio = _tone(tmp_path / "long.wav", baseline_max_seconds + 5)
    with pytest.raises(AudioRejected) as err:
        analyze_baseline(audio_path=audio, vad_params=VadParams())
    assert err.value.code == "too_long"
    assert f"{baseline_max_seconds} seconds" in err.value.message


@needs_ffmpeg
def test_baseline_inside_limits_passes_length_check(tmp_path):
    """A 30 s tone is not speech, so it ends as insufficient_audio, but not as a length error."""
    audio = _tone(tmp_path / "ok.wav", 30)
    payload = analyze_baseline(audio_path=audio, vad_params=VadParams())
    assert payload["status"] in {"ok", "insufficient_audio"}
