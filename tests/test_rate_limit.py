from src.app.rate_limit import SlidingWindowLimiter


def test_sliding_window_and_reset():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 10, clock=lambda: now[0])
    assert limiter.hit("key")
    now[0] = 5
    assert limiter.hit("key")
    assert not limiter.hit("key")
    now[0] = 10
    assert limiter.hit("key")
    assert not limiter.hit("key")
    limiter.reset()
    assert limiter.hit("key")
