import logging
from collections.abc import Callable
from typing import Any

import requests

from src.app.config import stt_connect_timeout_s, stt_read_timeout_s
from src.app.key_pool import get_pool, status_code_of
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
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"}

    with open(master.path, "rb") as f:
        response = requests.post(url, headers=headers, data=f, timeout=STT_TIMEOUT)
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
        words.append(
            WordTimestamp(
                word=w.get("punctuated_word", w.get("word", "")),
                start_s=w["start"],
                end_s=w["end"],
                confidence=w.get("confidence"),
            )
        )

    return SttResult(transcript=transcript, words=words, provider="deepgram", model=model, flags=[])


def call_gladia(master: MasterAudio, *, api_key: str) -> SttResult:
    url = "https://api.gladia.io/audio/text/audio-transcription/"
    headers = {"x-gladia-key": api_key}

    with open(master.path, "rb") as f:
        # Send the file name from master.path.name
        files = {"audio": (master.path.name, f, "audio/wav")}
        response = requests.post(url, headers=headers, files=files, timeout=STT_TIMEOUT)

    response.raise_for_status()
    data = response.json()

    prediction = data.get("prediction")
    raw_words = []
    if isinstance(prediction, str):
        transcript = prediction
        raw_words = data.get("prediction_raw", {}).get("words", [])
    elif isinstance(prediction, list):
        transcript_parts = []
        for segment in prediction:
            if not isinstance(segment, dict):
                raise ValueError("Invalid Gladia prediction segment")
            segment_transcript = segment.get("transcription", "")
            if not isinstance(segment_transcript, str):
                raise ValueError("Invalid Gladia segment transcription")
            transcript_parts.append(segment_transcript)
            segment_words = segment.get("words", [])
            if not isinstance(segment_words, list):
                raise ValueError("Invalid Gladia segment words")
            raw_words.extend(segment_words)
        transcript = " ".join(part for part in transcript_parts if part)
    elif prediction is None and "prediction" not in data:
        raise ValueError("Gladia response is missing prediction")
    else:
        raise ValueError("Invalid Gladia prediction")

    words = []
    for w in raw_words:
        if not isinstance(w, dict):
            raise ValueError("Invalid Gladia word")
        words.append(
            WordTimestamp(
                word=w.get("word", w.get("text", "")),
                start_s=w.get("time_begin", 0.0),
                end_s=w.get("time_end", 0.0),
                confidence=w.get("confidence"),
            )
        )

    if not transcript.strip():
        raise InsufficientAudio("STT returned empty transcript")

    return SttResult(
        transcript=transcript,
        words=words,
        provider="gladia",
        model="solaria-1",
        flags=["filler_from_vad_only"],
    )


def _try_provider(name: str, call: Callable[[str], SttResult], keys: list[str]) -> SttResult:
    """Try each usable key of one provider in order.

    429/402 locks the key for a cooldown and 401/403 locks it until restart, then the next
    key is tried with the same request. Any other failure means the provider itself is down,
    so the caller moves on to the next provider. Raises KeysExhaustedError when no key is left.
    """
    pool = get_pool(name, keys)
    while True:
        key = pool.current()
        try:
            return call(key)
        except InsufficientAudio:
            raise
        except Exception as e:
            if not pool.report(key, status_code_of(e)):
                raise
            logger.warning("%s failed, trying the next key", pool.label(key))


def transcribe(master: MasterAudio, *, settings: Any) -> SttResult:
    """Every Deepgram key first, then every Gladia key.

    An empty transcript (InsufficientAudio) is an answer about the audio, not a provider
    failure, so it is raised at once without calling the fallback. When both providers fail,
    raise SttUnavailable (the API answers 503 stt_unavailable).
    """
    try:
        result = _try_provider(
            "deepgram", lambda key: call_deepgram(master, api_key=key), settings.deepgram_api_keys
        )
        logger.info("Transcribed using Deepgram")
        return result
    except InsufficientAudio:
        raise
    except Exception as e:
        logger.warning("Deepgram failed: %s. Falling back to Gladia.", type(e).__name__)

    try:
        result = _try_provider(
            "gladia", lambda key: call_gladia(master, api_key=key), settings.gladia_api_keys
        )
        logger.info("Transcribed using Gladia")
        return result
    except InsufficientAudio:
        raise
    except Exception as e:
        logger.error("Gladia failed too: %s", type(e).__name__)
        raise SttUnavailable("Deepgram and Gladia both failed") from e
