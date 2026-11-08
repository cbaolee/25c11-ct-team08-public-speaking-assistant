import logging
import requests
from typing import Any

from src.audio_processing.contracts import (
    WordTimestamp,
    SttResult,
    MasterAudio,
    InsufficientAudio
)

logger = logging.getLogger(__name__)

def call_deepgram(master: MasterAudio, *, api_key: str, model: str = "nova-2") -> SttResult:
    url = f"https://api.deepgram.com/v1/listen?model={model}&filler_words=true&punctuate=true&utterances=false"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav"
    }
    
    # Đọc file audio từ master.path
    with open(master.path, "rb") as f:
        audio_data = f.read()
        
    response = requests.post(url, headers=headers, data=audio_data)
    response.raise_for_status()
    
    data = response.json()
    
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
        transcript = alt.get("transcript", "")
        raw_words = alt.get("words", [])
    except (KeyError, IndexError):
        transcript = ""
        raw_words = []
        
    if not transcript.strip():
        raise InsufficientAudio("STT returned empty transcript")
        
    words = []
    for w in raw_words:
        words.append(WordTimestamp(
            word=w.get("punctuated_word", w.get("word", "")),
            start_s=w["start"],
            end_s=w["end"],
            confidence=w.get("confidence")
        ))
        
    return SttResult(
        transcript=transcript,
        words=words,
        provider="deepgram",
        model=model,
        flags=[]
    )

def call_gladia(master: MasterAudio, *, api_key: str) -> SttResult:
    url = "https://api.gladia.io/audio/text/audio-transcription/"
    headers = {
        "x-gladia-key": api_key
    }
    
    with open(master.path, "rb") as f:
        # Truyền tên file từ master.path.name
        files = {"audio": (master.path.name, f, "audio/wav")}
        response = requests.post(url, headers=headers, files=files)
        
    response.raise_for_status()
    data = response.json()
    
    transcript = ""
    words = []
    
    if "prediction" in data:
        transcript = data["prediction"]
        for w in data.get("prediction_raw", {}).get("words", []):
            words.append(WordTimestamp(
                word=w.get("word", ""),
                start_s=w.get("time_begin", 0.0),
                end_s=w.get("time_end", 0.0),
                confidence=w.get("confidence")
            ))
            
    if not transcript.strip():
        raise InsufficientAudio("STT returned empty transcript")
        
    return SttResult(
        transcript=transcript,
        words=words,
        provider="gladia",
        model="solaria-1",
        flags=["filler_from_vad_only"]
    )

def transcribe(master: MasterAudio, *, settings: Any) -> SttResult:
    try:
        result = call_deepgram(master, api_key=settings.deepgram_api_key)
        logger.info("Transcribed using Deepgram")
        return result
    except Exception as e:
        logger.warning(f"Deepgram failed: {e}. Falling back to Gladia.")
        result = call_gladia(master, api_key=settings.gladia_api_key)
        logger.info("Transcribed using Gladia")
        return result