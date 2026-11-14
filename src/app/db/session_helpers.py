"""Pure helpers for storing and compacting practice session results."""

from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any

from src.app.config import decode_timeout_s


class AudioEncodingError(RuntimeError):
    """Audio could not be encoded as Opus."""


def encode_opus(
    wav_path: Path, out_path: Path, timeout_s: float = decode_timeout_s
) -> None:
    """Encode a WAV file as 32 kbps Opus in a WebM container.

    An existing file at ``out_path`` is overwritten.
    """
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-i",
        str(wav_path),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-f",
        "webm",
        str(out_path),
    ]
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as err:
        raise AudioEncodingError("FFmpeg was not found; install it and retry") from err
    except subprocess.TimeoutExpired as err:
        raise AudioEncodingError("Audio encoding timed out") from err
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or "").strip()
        message = f"FFmpeg could not encode the audio: {detail}" if detail else (
            "FFmpeg could not encode the audio"
        )
        raise AudioEncodingError(message) from err

    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise AudioEncodingError("FFmpeg completed without creating a non-empty output")


def split_series(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separate chart series from a result without mutating the input."""
    result_without_series = copy.deepcopy(result)
    series_json = {
        "pitch_detail": {
            "contour_st": copy.deepcopy(result_without_series["pitch_detail"]["contour_st"])
        },
        "display_only": {
            "loudness_db": copy.deepcopy(result_without_series["display_only"]["loudness_db"])
        },
    }
    result_without_series["pitch_detail"]["contour_st"] = None
    result_without_series["display_only"]["loudness_db"] = None
    return result_without_series, series_json


def merge_series(
    result_without_series: dict[str, Any], series_json: dict[str, Any]
) -> dict[str, Any]:
    """Restore chart series into a result without mutating either input."""
    result = copy.deepcopy(result_without_series)
    result["pitch_detail"]["contour_st"] = copy.deepcopy(
        series_json["pitch_detail"]["contour_st"]
    )
    result["display_only"]["loudness_db"] = copy.deepcopy(
        series_json["display_only"]["loudness_db"]
    )
    return result


def compact_session(
    result: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Keep score data and extract script-addressable mistakes for an old session.

    Mistakes use ``type`` values ``alignment``, ``filler``, and ``pause``.
    Alignment entries retain ``status``, ``ref_index``, ``ref_word``, and
    ``hyp_word``; fillers and pauses retain ``after_ref_index`` and their
    timing/type details. Insertions retain a null ``ref_index`` and their
    ``sentence_index`` because they have no corresponding reference word.

    Mistakes are ordered by script position: a reference word ``k`` sits at
    ``k``, while insertions, fillers, and pauses sit right after the previous
    reference word (``k + 0.5``).
    """
    summary = copy.deepcopy(result)
    # Script position: word k -> k, "after word k" -> k + 0.5
    keyed: list[tuple[float, float, str, dict[str, Any]]] = []

    last_ref_index = -1
    for item in result.get("alignment", []):
        if item["ref_index"] is not None:
            last_ref_index = item["ref_index"]
        if item["status"] == "equal":
            continue
        position = (
            item["ref_index"] if item["ref_index"] is not None else last_ref_index + 0.5
        )
        keyed.append(
            (
                position,
                float("-inf"),
                "alignment",
                {
                    "type": "alignment",
                    "status": item["status"],
                    "ref_index": item["ref_index"],
                    "ref_word": item["ref_word"],
                    "hyp_word": item["hyp_word"],
                    "sentence_index": item["sentence_index"],
                },
            )
        )

    for filler in result.get("fillers", []):
        keyed.append(
            (
                filler["after_ref_index"] + 0.5,
                filler["start_s"],
                "filler",
                {
                    "type": "filler",
                    "after_ref_index": filler["after_ref_index"],
                    "text": filler["text"],
                    "source": filler["source"],
                    "start_s": filler["start_s"],
                    "end_s": filler["end_s"],
                },
            )
        )

    for pause in result.get("pauses", []):
        if pause["kind"] in {"hesitation", "forgot_word"}:
            keyed.append(
                (
                    pause["after_ref_index"] + 0.5,
                    pause["start_s"],
                    "pause",
                    {
                        "type": "pause",
                        "kind": pause["kind"],
                        "after_ref_index": pause["after_ref_index"],
                        "start_s": pause["start_s"],
                        "end_s": pause["end_s"],
                    },
                )
            )

    keyed.sort(key=lambda entry: entry[:3])
    mistakes = [entry[3] for entry in keyed]

    for key in ("alignment", "pauses", "fillers", "sentences"):
        summary.pop(key, None)
    summary["pitch_detail"]["contour_st"] = None
    summary["display_only"]["loudness_db"] = None
    return summary, mistakes
