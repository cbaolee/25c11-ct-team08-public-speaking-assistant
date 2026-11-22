from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
import requests

from src.audio_processing.contracts import InsufficientAudio, MasterAudio, SttUnavailable
from src.audio_processing.stt import STT_TIMEOUT, call_deepgram, call_gladia, transcribe


@dataclass
class MockSettings:
    deepgram_api_keys: tuple = ("fake_dg_key",)
    gladia_api_keys: tuple = ("fake_gl_key",)


@pytest.fixture
def mock_master(tmp_path):
    # Create a fake wav file to avoid FileNotFoundError on with open(...)
    fake_audio = tmp_path / "dummy.wav"
    fake_audio.write_text("fake audio content")

    # Build MasterAudio with all of path, duration_s and warnings
    return MasterAudio(
        path=fake_audio,  # Keep the Path object (tmp_path gives a Path)
        duration_s=10.0,  # Assumed duration
        warnings=[],  # Empty warning list
    )


def test_deepgram_response_parsed_correctly(monkeypatch, mock_master):
    """Check a Deepgram SttResult is parsed with correct timestamps[cite: 1]."""

    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "transcript": "hello world",
                                "words": [
                                    {
                                        "word": "hello",
                                        "punctuated_word": "Hello",
                                        "start": 0.0,
                                        "end": 0.5,
                                        "confidence": 0.9,
                                    },
                                    {
                                        "word": "world",
                                        "punctuated_word": "world.",
                                        "start": 0.5,
                                        "end": 1.0,
                                        "confidence": 0.8,
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        }
        return mock_resp

    # Monkeypatch requests.post in the stt module
    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)

    result = call_deepgram(mock_master, api_key="test_key")

    assert result.provider == "deepgram"
    assert result.model == "nova-2"
    assert result.transcript == "hello world"
    assert len(result.words) == 2
    assert result.words[0].word == "Hello"
    assert result.words[0].start_s == 0.0
    assert result.words[1].end_s == 1.0


def test_deepgram_streams_audio_file(monkeypatch, mock_master):
    expected_audio = mock_master.path.read_bytes()
    request_data = []

    def mock_post(url, *args, **kwargs):
        body = kwargs["data"]
        assert not isinstance(body, bytes)
        request_data.append(body.read())
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {
                "channels": [
                    {"alternatives": [{"transcript": "hello", "words": []}]}
                ]
            }
        }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    call_deepgram(mock_master, api_key="test_key")

    assert request_data == [expected_audio]


def test_empty_transcript_raises_insufficient_audio(monkeypatch, mock_master):
    """Check an empty STT transcript raises InsufficientAudio[cite: 1]."""

    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {"channels": [{"alternatives": [{"transcript": "   ", "words": []}]}]}
        }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)

    with pytest.raises(InsufficientAudio, match="STT returned empty transcript"):
        call_deepgram(mock_master, api_key="test_key")


def test_gladia_adds_filler_flag(monkeypatch, mock_master):
    """Check Gladia automatically adds the 'filler_from_vad_only' flag[cite: 1]."""

    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "prediction": "test transcript",
            "prediction_raw": {
                "words": [{"word": "test", "time_begin": 0.0, "time_end": 0.5, "confidence": 0.9}]
            },
        }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)

    result = call_gladia(mock_master, api_key="test_key")
    assert result.provider == "gladia"
    assert result.model == "solaria-1"
    assert "filler_from_vad_only" in result.flags


def test_gladia_parses_segment_list_response(monkeypatch, mock_master):
    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "prediction": [
                {
                    "transcription": "hello",
                    "words": [
                        {
                            "word": "hello",
                            "time_begin": 0.0,
                            "time_end": 0.5,
                            "confidence": 0.9,
                        }
                    ],
                },
                {"transcription": "world", "words": []},
            ]
        }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    result = call_gladia(mock_master, api_key="test_key")

    assert result.transcript == "hello world"
    assert len(result.words) == 1
    assert result.words[0].word == "hello"
    assert result.words[0].start_s == 0.0
    assert result.words[0].end_s == 0.5


def test_fallback_to_gladia_when_deepgram_fails(monkeypatch, mock_master):
    """Check the router: fall back to Gladia when Deepgram fails[cite: 1]."""

    def mock_post(url, *args, **kwargs):
        mock_resp = MagicMock()
        if "deepgram" in url:
            # Make Deepgram fail
            mock_resp.raise_for_status.side_effect = Exception("Deepgram Error")
        else:
            # Return a good result for Gladia
            mock_resp.json.return_value = {
                "prediction": [{"transcription": "fallback success", "words": []}],
            }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)

    settings = MockSettings()
    result = transcribe(mock_master, settings=settings)

    assert result.provider == "gladia"
    assert result.transcript == "fallback success"


def test_every_stt_call_has_a_timeout(monkeypatch, mock_master):
    """Without `timeout`, a hung provider would block the request forever."""
    seen: list = []

    def mock_post(url, *args, **kwargs):
        seen.append(kwargs.get("timeout"))
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.ConnectionError("down")
        return resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    with pytest.raises(SttUnavailable):
        transcribe(mock_master, settings=MockSettings())
    assert seen == [STT_TIMEOUT, STT_TIMEOUT]
    assert all(t is not None for t in seen)


def test_empty_deepgram_transcript_does_not_call_gladia(monkeypatch, mock_master):
    """Silence is an answer about the audio, not a Deepgram failure: no fallback call."""
    urls: list[str] = []

    def mock_post(url, *args, **kwargs):
        urls.append(url)
        resp = MagicMock()
        resp.json.return_value = {
            "results": {"channels": [{"alternatives": [{"transcript": " ", "words": []}]}]}
        }
        return resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    with pytest.raises(InsufficientAudio):
        transcribe(mock_master, settings=MockSettings())
    assert len(urls) == 1 and "deepgram" in urls[0]


def test_both_providers_fail_raises_stt_unavailable(monkeypatch, mock_master):
    def mock_post(url, *args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("500")
        return resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    with pytest.raises(SttUnavailable):
        transcribe(mock_master, settings=MockSettings())


def test_evaluate_returns_503_stt_unavailable(monkeypatch):
    from fastapi.testclient import TestClient

    from src.app import main

    def fake_evaluate(audio_path, script, baseline, *, vad_params, **callbacks):
        raise SttUnavailable("both down")

    monkeypatch.setattr(main.settings, "baseline_required", False)
    monkeypatch.setattr(main, "evaluate_session", fake_evaluate)
    client = TestClient(main.app)
    r = client.post(
        "/api/evaluate",
        files={"audio": ("a.wav", b"RIFF", "audio/wav")},
        data={"script": "Hello."},
    )
    assert r.status_code == 202
    r = client.get(f"/api/evaluate/{r.json()['job_id']}")
    assert r.json()["status"] == "failed"
    assert r.json()["error_code"] == "stt_unavailable"
