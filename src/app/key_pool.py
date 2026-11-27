"""Several API keys per external service, with automatic switch when a key runs out.

A key that hits its quota (HTTP 429, or 402 for prepaid credit) is locked for a cooldown, then
tried again. A key that is refused (HTTP 401/403) is locked until the server restarts.
Logs only show the key position ("key #2"), never the key itself.
"""

import logging
import threading
import time
from collections.abc import Callable

from src.app.constants import CONSTANTS

logger = logging.getLogger(__name__)

QUOTA_STATUS_CODES = frozenset({402, 429})
REJECTED_STATUS_CODES = frozenset({401, 403})


class KeysExhaustedError(Exception):
    """Every key of a service is locked (quota or rejected). Callers map it to their error code."""


class KeyPool:
    """Keys of one service, tried in order. Thread-safe: endpoints run in a threadpool.

    `scope` separates limits that are counted apart, for example one Groq key per model:
    a key out of quota for one model can still be used for another.
    """

    def __init__(
        self,
        service: str,
        keys: list[str],
        *,
        cooldown_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.service = service
        self.keys = list(keys)
        self.cooldown_s = (
            CONSTANTS["api_keys"]["exhausted_cooldown_s"] if cooldown_s is None else cooldown_s
        )
        self._clock = clock
        self._lock = threading.Lock()
        self._locked_until: dict[tuple[int, str], float] = {}  # (key index, scope) -> time
        self._rejected: set[int] = set()  # key indexes refused by the provider

    def label(self, key: str) -> str:
        """Safe name for logs: "deepgram key #2"."""
        return f"{self.service} key #{self.keys.index(key) + 1}"

    def available(self, scope: str = "") -> list[str]:
        """Usable keys for this scope, in order."""
        now = self._clock()
        with self._lock:
            return [
                key
                for i, key in enumerate(self.keys)
                if i not in self._rejected and self._locked_until.get((i, scope), 0.0) <= now
            ]

    def current(self, scope: str = "") -> str:
        """The key to use now. Raises KeysExhaustedError when none is usable."""
        keys = self.available(scope)
        if not keys:
            raise KeysExhaustedError(f"No usable {self.service} key")
        return keys[0]

    def mark_exhausted(self, key: str, scope: str = "") -> None:
        """Lock a key that hit its quota for `cooldown_s`; the next key becomes current."""
        with self._lock:
            self._locked_until[(self.keys.index(key), scope)] = self._clock() + self.cooldown_s
        logger.warning(
            "%s out of quota%s, locked for %ss",
            self.label(key),
            f" for {scope}" if scope else "",
            self.cooldown_s,
        )

    def mark_rejected(self, key: str) -> None:
        """Lock a key the provider refused (wrong or revoked) until restart."""
        with self._lock:
            self._rejected.add(self.keys.index(key))
        logger.error("%s rejected by the provider, not used again until restart", self.label(key))

    def report(self, key: str, status_code: int | None, scope: str = "") -> bool:
        """Lock the key if `status_code` is a quota or auth error. True when it was locked."""
        if status_code in QUOTA_STATUS_CODES:
            self.mark_exhausted(key, scope)
            return True
        if status_code in REJECTED_STATUS_CODES:
            self.mark_rejected(key)
            return True
        return False


_pools: dict[tuple[str, tuple[str, ...]], KeyPool] = {}
_pools_lock = threading.Lock()


def get_pool(service: str, keys: list[str]) -> KeyPool:
    """One shared pool per (service, key list); a new key list gets a new pool."""
    ident = (service, tuple(keys))
    with _pools_lock:
        if ident not in _pools:
            _pools[ident] = KeyPool(service, keys)
        return _pools[ident]


def status_code_of(exc: BaseException) -> int | None:
    """HTTP status of a requests or Groq SDK error, or None."""
    response = getattr(exc, "response", None)
    code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    return code if isinstance(code, int) else None
