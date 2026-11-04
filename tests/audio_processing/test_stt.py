import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass

from src.audio_processing.stt import (
    call_deepgram,
    call_gladia,
    transcribe
)
from src.audio_processing.contracts import InsufficientAudio, MasterAudio

@dataclass
class MockSettings:
    deepgram_api_key: str = "fake_dg_key"
    gladia_api_key: str = "fake_gl_key"

@pytest.fixture
def mock_master(tmp_path):
    # Tạo một file wav giả để tránh FileNotFoundError khi with open(...)
    fake_audio = tmp_path / "dummy.wav"
    fake_audio.write_text("fake audio content")
    
    # Khởi tạo MasterAudio với đầy đủ các tham số path, duration_s và warnings
    return MasterAudio(
        path=fake_audio,       # Giữ nguyên object Path (tmp_path tạo ra Path)
        duration_s=10.0,       # Thời lượng giả định
        warnings=[]            # Danh sách cảnh báo rỗng
    )


def test_deepgram_response_parsed_correctly(monkeypatch, mock_master):
    """Kiểm tra Deepgram trả về SttResult được parse đúng timestamps[cite: 1]."""
    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {
                "channels": [{
                    "alternatives": [{
                        "transcript": "hello world",
                        "words": [
                            {"word": "hello", "punctuated_word": "Hello", "start": 0.0, "end": 0.5, "confidence": 0.9},
                            {"word": "world", "punctuated_word": "world.", "start": 0.5, "end": 1.0, "confidence": 0.8}
                        ]
                    }]
                }]
            }
        }
        return mock_resp

    # Monkeypatch hàm requests.post trong module stt
    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    
    result = call_deepgram(mock_master, api_key="test_key")
    
    assert result.provider == "deepgram"
    assert result.model == "nova-2"
    assert result.transcript == "hello world"
    assert len(result.words) == 2
    assert result.words[0].word == "Hello"
    assert result.words[0].start_s == 0.0
    assert result.words[1].end_s == 1.0


def test_empty_transcript_raises_insufficient_audio(monkeypatch, mock_master):
    """Kiểm tra nếu STT trả transcript rỗng sẽ raise InsufficientAudio[cite: 1]."""
    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": {
                "channels": [{"alternatives": [{"transcript": "   ", "words": []}]}]
            }
        }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    
    with pytest.raises(InsufficientAudio, match="STT returned empty transcript"):
        call_deepgram(mock_master, api_key="test_key")


def test_gladia_adds_filler_flag(monkeypatch, mock_master):
    """Kiểm tra Gladia tự động thêm cờ 'filler_from_vad_only'[cite: 1]."""
    def mock_post(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "prediction": "test transcript",
            "prediction_raw": {
                "words": [{"word": "test", "time_begin": 0.0, "time_end": 0.5, "confidence": 0.9}]
            }
        }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    
    result = call_gladia(mock_master, api_key="test_key")
    assert result.provider == "gladia"
    assert result.model == "solaria-1"
    assert "filler_from_vad_only" in result.flags


def test_fallback_to_gladia_when_deepgram_fails(monkeypatch, mock_master):
    """Kiểm tra tính năng router: fallback qua Gladia khi Deepgram lỗi[cite: 1]."""
    def mock_post(url, *args, **kwargs):
        mock_resp = MagicMock()
        if "deepgram" in url:
            # Gây lỗi cho Deepgram
            mock_resp.raise_for_status.side_effect = Exception("Deepgram Error")
        else:
            # Trả kết quả tốt cho Gladia
            mock_resp.json.return_value = {
                "prediction": "fallback success",
                "prediction_raw": {"words": []}
            }
        return mock_resp

    monkeypatch.setattr("src.audio_processing.stt.requests.post", mock_post)
    
    settings = MockSettings()
    result = transcribe(mock_master, settings=settings)
    
    assert result.provider == "gladia"
    assert result.transcript == "fallback success"