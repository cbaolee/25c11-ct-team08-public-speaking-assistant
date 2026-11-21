"""Thread-safe in-memory sliding window rate limiting."""

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self._lock = threading.Lock()
        self._hits = {}

    def hit(self, key) -> bool:
        with self._lock:
            now = self.clock()
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                if not hits:
                    del self._hits[key]
                return False
            hits.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()
