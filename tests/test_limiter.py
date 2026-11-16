"""Unit tests for WP-B3: TokenBucketLimiter."""

from __future__ import annotations

from src.text_processing.limiter import TokenBucketLimiter


class TestTokenBucketLimiter:
    """Tests for TokenBucketLimiter token/RPM tracking and thread safety."""

    def test_initial_state_can_consume(self) -> None:
        limiter = TokenBucketLimiter(rpm_limit=30, tpm_limit=8000)
        assert limiter.can_consume("model-a", estimated_tokens=1000)
        assert limiter.wait_time_s("model-a", estimated_tokens=1000) == 0.0

    def test_consume_deducts_tokens_and_rpm(self) -> None:
        limiter = TokenBucketLimiter(rpm_limit=2, tpm_limit=1000)
        limiter.consume("model-a", tokens_used=600)
        assert limiter.can_consume("model-a", estimated_tokens=300)
        assert not limiter.can_consume("model-a", estimated_tokens=500)

        limiter.consume("model-a", tokens_used=200)
        assert not limiter.can_consume("model-a", estimated_tokens=100)

    def test_refill_over_time(self) -> None:
        limiter = TokenBucketLimiter(rpm_limit=60, tpm_limit=6000)
        limiter.consume("model-a", tokens_used=5000)
        assert not limiter.can_consume("model-a", estimated_tokens=2000)

        bucket = limiter._ensure_bucket("model-a")
        bucket[2] -= 30.0  # Simulate 30s elapsed
        assert limiter.can_consume("model-a", estimated_tokens=2000)

    def test_wait_time_calculation(self) -> None:
        limiter = TokenBucketLimiter(rpm_limit=60, tpm_limit=6000)
        limiter.consume("model-a", tokens_used=6000)
        wait = limiter.wait_time_s("model-a", estimated_tokens=1000)
        assert 9.0 <= wait <= 11.0

    def test_wait_time_infinite_when_exceeds_tpm_limit(self) -> None:
        limiter = TokenBucketLimiter(rpm_limit=30, tpm_limit=8000)
        wait = limiter.wait_time_s("model-a", estimated_tokens=8001)
        assert wait == float("inf")

    def test_independent_models(self) -> None:
        limiter = TokenBucketLimiter(rpm_limit=1, tpm_limit=100)
        limiter.consume("model-a", tokens_used=100)
        assert not limiter.can_consume("model-a", estimated_tokens=50)
        assert limiter.can_consume("model-b", estimated_tokens=50)
