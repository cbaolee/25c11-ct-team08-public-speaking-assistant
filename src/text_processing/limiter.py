"""WP-B3 (Member 2): Token-Bucket Rate Limiter for Groq API.

Responsibilities (Brief §5.5):
- Track per-model RPM (Requests Per Minute) and TPM (Tokens Per Minute)
- Refill linearly over time with process-level thread safety
- Calculate finite wait times and return inf for requests exceeding model TPM limit
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class TokenBucketLimiter:
    """Per-model token and request rate limiter for Groq's free tier (Brief §5.5).

    Each model gets independent RPM and TPM budgets that refill linearly
    over time. Thread-safe across concurrent workers.
    """

    def __init__(self, rpm_limit: int = 30, tpm_limit: int = 8000) -> None:
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self._lock = threading.Lock()
        # Internal state per model_id: [remaining_rpm, remaining_tpm, last_refill_ts]
        self._buckets: dict[str, list[float]] = {}

    def _ensure_bucket(self, model_id: str) -> list[float]:
        if model_id not in self._buckets:
            self._buckets[model_id] = [
                float(self.rpm_limit),
                float(self.tpm_limit),
                time.monotonic(),
            ]
        return self._buckets[model_id]

    def _refill(self, bucket: list[float]) -> None:
        now = time.monotonic()
        elapsed = now - bucket[2]
        if elapsed <= 0:
            return
        bucket[0] = min(self.rpm_limit, bucket[0] + elapsed * self.rpm_limit / 60.0)
        bucket[1] = min(self.tpm_limit, bucket[1] + elapsed * self.tpm_limit / 60.0)
        bucket[2] = now

    def can_consume(self, model_id: str, estimated_tokens: int) -> bool:
        """Return ``True`` if *model_id* has enough budget for *estimated_tokens*."""
        with self._lock:
            bucket = self._ensure_bucket(model_id)
            self._refill(bucket)
            return bucket[0] >= 1 and bucket[1] >= estimated_tokens

    def consume(self, model_id: str, tokens_used: int) -> None:
        """Deduct *tokens_used* and 1 request from *model_id*'s bucket."""
        with self._lock:
            bucket = self._ensure_bucket(model_id)
            self._refill(bucket)
            bucket[0] = max(0.0, bucket[0] - 1.0)
            bucket[1] = max(0.0, bucket[1] - float(tokens_used))

    def wait_time_s(self, model_id: str, estimated_tokens: int) -> float:
        """Seconds until *model_id* can serve *estimated_tokens* (0 if ready).

        Returns ``float('inf')`` if *estimated_tokens* exceeds the maximum capacity.
        """
        if estimated_tokens > self.tpm_limit:
            return float("inf")
        with self._lock:
            bucket = self._ensure_bucket(model_id)
            self._refill(bucket)
            rpm_wait = max(0.0, (1 - bucket[0]) / (self.rpm_limit / 60.0))
            tpm_wait = max(
                0.0,
                (estimated_tokens - bucket[1]) / (self.tpm_limit / 60.0),
            )
            return max(rpm_wait, tpm_wait)
