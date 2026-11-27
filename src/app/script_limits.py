"""Input checks and anti-spam limits of POST /api/generate-script (ADR-015)."""

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal

from fastapi.responses import JSONResponse

from src.app.constants import CONSTANTS
from src.app.db.models import StorageError
from src.app.db.repositories import RateLimitRepo
from src.text_processing.contracts import VALID_DURATIONS, ScriptGenerationError

logger = logging.getLogger(__name__)

Reason = Literal["cooldown", "regenerate_quota", "generate_quota", "job_running"]

_MESSAGES: dict[Reason, str] = {
    "cooldown": "Please wait a moment before regenerating this script again.",
    "regenerate_quota": (
        "You have regenerated scripts many times in a short period. Please try again later."
    ),
    "generate_quota": (
        "You have generated many scripts in a short period. Please try again later."
    ),
    "job_running": "A script is already being generated. Please wait for it to finish.",
}


@dataclass(frozen=True)
class GenerateBlock:
    """Why a generate request is refused and how long the client should wait."""

    reason: Reason
    retry_after_s: int


@dataclass(frozen=True)
class _Layer:
    reason: Reason
    bucket: str  # letters and "_" only (check constraint of auth_rate_limits)
    max_hits: int
    window_s: int


def user_rate_key(user_id: str) -> str:
    """Counter key of a user: a hash, never the id itself (same as the account routes)."""
    return hashlib.sha256(user_id.encode()).hexdigest()


def validate_generate_input(topic: str, duration_min: int, feedback: str | None) -> None:
    """Raise ScriptGenerationError (422) for input that must not cost a rate limit attempt."""
    max_words = CONSTANTS["web"]["composer_max_words"]
    if not topic.strip():
        message = "Topic must not be empty."
    elif duration_min not in VALID_DURATIONS:
        allowed = ", ".join(str(minutes) for minutes in VALID_DURATIONS)
        message = f"The duration must be one of {allowed} minutes."
    elif feedback is not None and len(feedback.split()) > max_words:
        message = f"The feedback is too long (maximum {max_words} words)."
    else:
        return
    raise ScriptGenerationError("output_invalid", message, status_code=422)


def _layers(is_regenerate: bool, duration_min: int) -> list[_Layer]:
    """The limits of one request, in the order they are counted."""
    limits = CONSTANTS["script_limits"]
    total = _Layer(
        "generate_quota",
        "script_gen_window",
        limits["generate_max_per_window"],
        limits["generate_window_s"],
    )
    if not is_regenerate:
        return [total]
    is_long = duration_min >= limits["regenerate_long_min_duration"]
    cooldown_key = "regenerate_long_cooldown_s" if is_long else "regenerate_cooldown_s"
    cooldown = _Layer("cooldown", "script_regen_cooldown", 1, limits[cooldown_key])
    quota = _Layer(
        "regenerate_quota",
        "script_regen_window",
        limits["regenerate_max_per_window"],
        limits["regenerate_window_s"],
    )
    return [cooldown, total, quota]


def _hit(rate_limits: RateLimitRepo, key: str, layer: _Layer) -> bool:
    """Count one attempt; fails open when the counter cannot be reached."""
    try:
        return rate_limits.hit(layer.bucket, key, layer.max_hits, layer.window_s)
    except StorageError:
        logger.warning(
            "Script rate limit counter unavailable for %s; allowing the request", layer.bucket
        )
        return True


def _wait_s(rate_limits: RateLimitRepo, key: str, layer: _Layer) -> int:
    """Seconds left in a full layer; the whole window when that cannot be read."""
    try:
        return rate_limits.retry_after_s(layer.bucket, key, layer.window_s)
    except StorageError:
        logger.warning(
            "Script rate limit wait time unavailable for %s; using the whole window", layer.bucket
        )
        return layer.window_s


def check_generate_limits(
    rate_limits: RateLimitRepo, user_id: str, *, is_regenerate: bool, duration_min: int
) -> GenerateBlock | None:
    """Count this request layer by layer; the first full layer blocks it, None lets it pass.

    Layers after the blocking one are not counted; layers before it stay counted.
    """
    key = user_rate_key(user_id)
    for layer in _layers(is_regenerate, duration_min):
        if not _hit(rate_limits, key, layer):
            return GenerateBlock(layer.reason, _wait_s(rate_limits, key, layer))
    return None


def job_running_block() -> GenerateBlock:
    """The block used while the user's previous script job has not finished."""
    return GenerateBlock("job_running", CONSTANTS["script_limits"]["active_job_retry_after_s"])


def rate_limited_response(block: GenerateBlock) -> JSONResponse:
    """429 `{error_code, message, retry_after_s, reason}` with a `Retry-After` header."""
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(block.retry_after_s)},
        content={
            "error_code": "rate_limited",
            "message": _MESSAGES[block.reason],
            "retry_after_s": block.retry_after_s,
            "reason": block.reason,
        },
    )
