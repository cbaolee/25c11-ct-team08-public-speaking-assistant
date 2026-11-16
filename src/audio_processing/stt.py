import logging
from typing import Any

import requests

from src.app.config import stt_connect_timeout_s, stt_read_timeout_s
from src.audio_processing.contracts import (
    InsufficientAudio,
    MasterAudio,
    SttResult,
    SttUnavailable,
    WordTimestamp,
)

logger = logging.getLogger(__name__)

# (connect, read): without a timeout a hung provider blocks the request forever.
STT_TIMEOUT = (stt_connect_timeout_s, stt_read_timeout_s)

def call_deepgram(master: MasterAudio, *, api_key: str, model: str = "nova-2") -> SttResult:
    url = f"https://api.deepgram.com/v1/listen?model={model}&filler_words=true&punctuate=true&utterances=false"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav"
    }

    # Read the audio file from master.path
    with open(master.path, "rb") as f:
        audio_data = f.read()

    response = requests.post(url, headers=headers, data=audio_data, timeout=STT_TIMEOUT)
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
        # Send the file name from master.path.name
        files = {"audio": (master.path.name, f, "audio/wav")}
        response = requests.post(url, headers=headers, files=files, timeout=STT_TIMEOUT)

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
    """Deepgram first, Gladia as fallback.

    An empty transcript (InsufficientAudio) is an answer about the audio, not a provider
    failure, so it is raised at once without calling the fallback. When both providers fail,
    raise SttUnavailable (the API answers 503 stt_unavailable).
    """
    try:
        result = call_deepgram(master, api_key=settings.deepgram_api_key)
        logger.info("Transcribed using Deepgram")
        return result
    except InsufficientAudio:
        raise
    except Exception as e:
        logger.warning("Deepgram failed: %s. Falling back to Gladia.", e)

    try:
        result = call_gladia(master, api_key=settings.gladia_api_key)
        logger.info("Transcribed using Gladia")
        return result
    except InsufficientAudio:
        raise
    except Exception as e:
        logger.error("Gladia failed too: %s", e)
        raise SttUnavailable("Deepgram and Gladia both failed") from e
