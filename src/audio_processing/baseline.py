import math
import statistics
from collections.abc import Sequence
from typing import Any

import numpy as np
import parselmouth

from src.app.config import MIN_PAUSE_S
from src.audio_processing.contracts import BaselineProfile, MasterAudio, Pause
from src.audio_processing.vad import check_audio_quality, detect_speech, find_pauses


def compute_baseline_pause_profile(pauses: list[Pause]) -> dict:
    """
    Get the median pause and the hesitation threshold from the baseline recording.
    Pause lengths come from start_s and end_s.
    """
    # D13: < 5 pauses (including 0) -> fixed threshold 0.7 s and the unreliable flag,
    # NOT no_baseline (that flag is only for users who have no baseline yet).
    if not pauses:
        return {
            "median_pause_s": None,
            "hesitation_threshold_s": 0.7,
            "flags": ["baseline_pause_unreliable"],
        }

    durations = [(p.end_s - p.start_s) for p in pauses]
    median_pause_s = statistics.median(durations)

    if len(pauses) < 5:
        return {
            "median_pause_s": median_pause_s,
            "hesitation_threshold_s": 0.7,
            "flags": ["baseline_pause_unreliable"],
        }

    flags = []

    # Threshold, clamped to [0.7, 1.2]
    threshold = 2.0 * median_pause_s
    hesitation_threshold_s = max(0.7, min(1.2, threshold))

    return {
        "median_pause_s": median_pause_s,
        "hesitation_threshold_s": hesitation_threshold_s,
        "flags": flags,
    }


def compute_baseline_f0(master: MasterAudio) -> dict:
    """
    Median pitch F0 (Hz) of the baseline, measured with Parselmouth.
    """
    flags = []
    median_f0_hz = None

    try:
        snd = parselmouth.Sound(str(master.path))
        pitch = snd.to_pitch()
        pitch_values = pitch.selected_array["frequency"]

        # Keep only voiced frames (frequency > 0)
        voiced_f0 = pitch_values[pitch_values > 0]

        if len(voiced_f0) > 0:
            median_f0_hz = float(np.median(voiced_f0))
        else:
            flags.append("no_f0")
    except Exception:
        flags.append("no_f0")

    return {"median_f0_hz": median_f0_hz, "flags": flags}


def mean_loudness_db(values: Sequence[float]) -> float | None:
    """Mean dB without NaN and ±inf; empty or no valid value left -> None (D12)."""
    valid = [float(v) for v in values if math.isfinite(v)]
    if not valid:
        return None
    return sum(valid) / len(valid)


def extract_loudness_db(master: MasterAudio) -> list[float]:
    """
    Loudness samples (dB) every 0.5 s with Parselmouth `to_intensity()` (default settings),
    the same way pipeline.evaluate_session measures loudness. Any error -> empty list.
    """
    try:
        snd = parselmouth.Sound(str(master.path))
        intensity = snd.to_intensity()
        values = []
        for t in np.arange(0, master.duration_s, 0.5):
            db = intensity.get_value(t)
            if db is not None and not np.isnan(db):
                values.append(float(db))
        return values
    except Exception:
        return []


def loudness_series(master: MasterAudio, step_s: float = 0.1) -> dict | None:
    """Loudness Series (dB), sampled at the CENTRE of each cell t = (i + 0.5) * step (ADR-004 D10).

    Uses the default to_intensity(); non-finite/None values -> None; any exception -> None.
    """
    try:
        snd = parselmouth.Sound(str(master.path))
        intensity = snd.to_intensity()
        n = math.ceil(round(master.duration_s / step_s, 9))
        values: list[float | None] = []
        for i in range(n):
            db = intensity.get_value((i + 0.5) * step_s)
            values.append(float(db) if db is not None and math.isfinite(db) else None)
        return {"start_s": 0.0, "step_s": step_s, "values": values}
    except Exception:
        return None


def build_baseline_profile(master: MasterAudio, vad_params: Any) -> BaselineProfile:
    """
    Run the whole baseline analysis and return a BaselineProfile.
    """
    # 1. Detect speech (keyword argument params=vad_params)
    segments = detect_speech(master, params=vad_params)

    # 2. Quality check (raises InsufficientAudio when speech is < 30%)
    check_audio_quality(segments, master.duration_s)

    # 3. Pauses: same minimum length as the Evaluate Pipeline, so both compare like with like
    pauses = find_pauses(segments, min_pause_s=MIN_PAUSE_S)
    pause_profile = compute_baseline_pause_profile(pauses)

    # 4. Pitch analysis
    f0_profile = compute_baseline_f0(master)

    loudness = mean_loudness_db(extract_loudness_db(master))

    # 5. Merge flags
    combined_flags = pause_profile["flags"] + f0_profile["flags"]

    return BaselineProfile(
        median_pause_s=pause_profile["median_pause_s"],
        hesitation_threshold_s=pause_profile["hesitation_threshold_s"],
        median_f0_hz=f0_profile["median_f0_hz"],
        mean_loudness_db=loudness,
        flags=combined_flags,
    )
