"""Groq client that rotates over GROQ_API_KEYS.

It has the same `client.chat.completions.create(model=..., ...)` shape as `groq.Groq`, so the
model fallback loops in generator.py and template_engine.py stay as they are. For one model it
tries every usable key; quota limits are counted per model, so a key locked for one model can
still serve the next. When no key is left for that model it raises KeysExhaustedError, and the
caller's loop moves on to the fallback model.
"""

import logging
from typing import Any

from src.app.config import settings
from src.app.key_pool import KeyPool, get_pool, status_code_of

logger = logging.getLogger(__name__)


class _Completions:
    def __init__(self, owner: "PooledGroqClient") -> None:
        self._owner = owner

    def create(self, *, model: str, **kwargs: Any) -> Any:
        pool = self._owner.pool
        while True:
            key = pool.current(scope=model)
            try:
                return self._owner.client_for(key).chat.completions.create(model=model, **kwargs)
            except Exception as e:
                if not pool.report(key, status_code_of(e), scope=model):
                    raise
                logger.warning("%s failed for %s, trying the next key", pool.label(key), model)


class _Chat:
    def __init__(self, owner: "PooledGroqClient") -> None:
        self.completions = _Completions(owner)


class PooledGroqClient:
    def __init__(self, pool: KeyPool, factory: Any) -> None:
        self.pool = pool
        self._factory = factory
        self._clients: dict[str, Any] = {}
        self.chat = _Chat(self)

    def client_for(self, key: str) -> Any:
        if key not in self._clients:
            self._clients[key] = self._factory(api_key=key)
        return self._clients[key]


def make_groq_client(keys: list[str] | None = None) -> PooledGroqClient | None:
    """Pooled client over `keys` (default: settings.groq_api_keys); None without SDK or keys."""
    try:
        from groq import Groq
    except ImportError:
        return None
    keys = settings.groq_api_keys if keys is None else keys
    if not keys:
        return None
    return PooledGroqClient(get_pool("groq", keys), Groq)
