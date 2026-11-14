import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.app.db import session_helpers
from src.app.db.session_helpers import (
    AudioEncodingError,
    compact_session,
    encode_opus,
    merge_series,
    split_series,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture_name",
    [
        "evaluation_ok.json",
        "evaluation_ok_mixed.json",
        "evaluation_insufficient.json",
    ],
)
def test_merge_series_round_trips_fixture_without_mutating_inputs(fixture_name):
    result = _load_fixture(fixture_name)
    original = json.loads(json.dumps(result))

    result_without_series, series_json = split_series(result)

    assert result == original
    assert result_without_series["pitch_detail"]["contour_st"] is None
    assert result_without_series["display_only"]["loudness_db"] is None
    assert merge_series(result_without_series, series_json) == original
    assert result_without_series["pitch_detail"]["contour_st"] is None
    assert result_without_series["display_only"]["loudness_db"] is None


def test_compact_session_extracts_mistakes_and_keeps_score_data():
    result = _load_fixture("evaluation_ok_mixed.json")
    original = json.loads(json.dumps(result))

    summary, mistakes = compact_session(result)

    assert result == original
    assert summary["overall"] == result["overall"]
    assert summary["components"] == result["components"]
    assert summary["fluency_detail"] == result["fluency_detail"]
    assert summary["pitch_detail"]["contour_st"] is None
    assert summary["display_only"]["loudness_db"] is None
    assert not {"alignment", "pauses", "fillers", "sentences"} & summary.keys()
    assert [item["type"] for item in mistakes].count("alignment") == 4
    assert [item["type"] for item in mistakes].count("filler") == 1
    assert [item["type"] for item in mistakes].count("pause") == 2
    assert any(
        item["type"] == "alignment"
        and item["status"] == "ins"
        and item["ref_index"] is None
        for item in mistakes
    )
    assert any(
        item["type"] == "filler" and item["after_ref_index"] is not None
        for item in mistakes
    )


def test_compact_session_handles_insufficient_audio():
    summary, mistakes = compact_session(_load_fixture("evaluation_insufficient.json"))

    assert summary["status"] == "insufficient_audio"
    assert summary["overall"] is None
    assert mistakes == []


def _supports_libopus() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    )
    return "libopus" in result.stdout


@pytest.mark.skipif(not _supports_libopus(), reason="FFmpeg with libopus is required")
def test_encode_opus_creates_webm_audio(tmp_path):
    wav_path = tmp_path / "source.wav"
    out_path = tmp_path / "output.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=1:sample_rate=16000",
            "-y",
            str(wav_path),
        ],
        check=True,
    )

    encode_opus(wav_path, out_path)

    assert out_path.is_file()
    assert out_path.stat().st_size > 0
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(out_path), "-f", "null", "-"],
        check=True,
    )


def test_encode_opus_reports_ffmpeg_failure(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="invalid input")

    monkeypatch.setattr(session_helpers.subprocess, "run", fail)

    with pytest.raises(AudioEncodingError, match="invalid input"):
        encode_opus(tmp_path / "source.wav", tmp_path / "output.webm")


def test_encode_opus_reports_timeout(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=60)

    monkeypatch.setattr(session_helpers.subprocess, "run", timeout)

    with pytest.raises(AudioEncodingError, match="timed out"):
        encode_opus(tmp_path / "source.wav", tmp_path / "output.webm")
