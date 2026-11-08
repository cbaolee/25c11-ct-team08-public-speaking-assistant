import pytest
from dataclasses import dataclass

from src.audio_processing.contracts import (
    Pause,
    SpeechSegment,
    WordTimestamp,
    PauseKind,
    InsufficientAudio
)
from src.audio_processing.vad import classify_pauses, check_audio_quality


# ==========================================
# TESTS CHO HÀM check_audio_quality
# ==========================================

def test_check_audio_quality_empty_segments_raises_insufficient_audio():
    with pytest.raises(InsufficientAudio, match="Speech < 30%"):
        check_audio_quality(segments=[], duration_s=10.0)

def test_check_audio_quality_below_30_percent_raises_insufficient_audio():
    # 2.5s tiếng nói trên tổng 10.0s (25%) -> Raise
    segments = [SpeechSegment(start_s=0.0, end_s=2.5)]
    with pytest.raises(InsufficientAudio, match="Speech < 30%"):
        check_audio_quality(segments=segments, duration_s=10.0)

def test_check_audio_quality_above_30_percent_passes():
    # 3.5s tiếng nói trên tổng 10.0s (35%) -> Pass
    segments = [SpeechSegment(start_s=0.0, end_s=3.5)]
    try:
        check_audio_quality(segments=segments, duration_s=10.0)
    except InsufficientAudio:
        pytest.fail("Unexpected InsufficientAudio raised for speech >= 30%")


# ==========================================
# TESTS CHO HÀM classify_pauses
# ==========================================

def test_empty_pauses_returns_empty():
    result = classify_pauses(
        pauses=[], 
        words=[WordTimestamp(word="hello", start_s=0.0, end_s=0.5)], 
        script="Hello world", 
        hesitation_threshold_s=0.7
    )
    assert result == []

def test_pause_at_period_is_rhetorical():
    script = "Hello world. How are you?"
    words = [WordTimestamp(word="world", start_s=0.5, end_s=1.0)]
    # end_s - start_s = 0.8s
    pauses = [Pause(start_s=1.0, end_s=1.8)]
    
    result = classify_pauses(pauses, words, script, hesitation_threshold_s=0.7)
    
    assert len(result) == 1
    assert result[0].kind == PauseKind.RHETORICAL

def test_pause_at_comma_is_rhetorical():
    script = "Well, that is good."
    words = [WordTimestamp(word="well", start_s=0.0, end_s=0.5)]
    # end_s - start_s = 0.6s
    pauses = [Pause(start_s=0.5, end_s=1.1)]
    
    result = classify_pauses(pauses, words, script, hesitation_threshold_s=0.7)
    
    assert len(result) == 1
    assert result[0].kind == PauseKind.RHETORICAL

def test_long_pause_mid_sentence_is_forgot_word():
    script = "Hello world and welcome."
    words = [WordTimestamp(word="world", start_s=0.5, end_s=1.0)]
    # Pause 1.5s (1.0 đến 2.5) -> >= 1.2s, không tại dấu câu
    pauses = [Pause(start_s=1.0, end_s=2.5)]
    
    result = classify_pauses(pauses, words, script, hesitation_threshold_s=0.7)
    
    assert len(result) == 1
    assert result[0].kind == PauseKind.FORGOT_WORD

def test_pause_above_threshold_mid_sentence_is_hesitation():
    script = "Hello world and welcome."
    words = [WordTimestamp(word="world", start_s=0.5, end_s=1.0)]
    # Pause 0.9s (1.0 đến 1.9) -> >= ngưỡng 0.7s nhưng < 1.2s
    pauses = [Pause(start_s=1.0, end_s=1.9)]
    
    result = classify_pauses(pauses, words, script, hesitation_threshold_s=0.7)
    
    assert len(result) == 1
    assert result[0].kind == PauseKind.HESITATION

def test_rhetorical_pause_not_counted_as_hesitation_even_if_long():
    script = "Hello world. How are you?"
    words = [WordTimestamp(word="world", start_s=0.5, end_s=1.0)]
    # Pause 2.5s (1.0 đến 3.5), cực dài nhưng nằm tại dấu chấm câu "."
    pauses = [Pause(start_s=1.0, end_s=3.5)]
    
    result = classify_pauses(pauses, words, script, hesitation_threshold_s=0.7)
    
    assert len(result) == 1
    assert result[0].kind == PauseKind.RHETORICAL