"""In-memory ephemeral chat session management and minimal-token gathering engine.

Responsibilities:
- Manage ChatSessionState lifecycle with 30-minute sliding TTL and multi-tenant isolation.
- Perform 0-token slot coverage analysis with cosine similarity via SemanticRetriever.
- Group uncovered argument slots into at most 3 semantic buckets.
- Implement 3-layer deterministic stop condition for script generation readiness.
- Build lightweight follow-up questions with Groq API and 0-token checklist fallback.
- Ingest .pdf, .md, and .txt files into DocumentChunk items with immediate disk cleanup.
"""

from __future__ import annotations

import logging
import re
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from src.app.config import settings

from .contracts import (
    DocumentChunk,
    TemplateDocument,
    TemplateSlot,
    TopicMetadata,
)
from .parser import DocumentParserError, parse_input_to_chunks
from .template_engine import parse_slots

if TYPE_CHECKING:
    from .retrieval import SemanticRetriever

logger = logging.getLogger(__name__)

# Constants
DEFAULT_STORE_CAPACITY = 100
DEFAULT_STORE_TTL_SECONDS = 1800.0  # 30 minutes
COSINE_SIMILARITY_THRESHOLD = 0.35
FREE_TOPIC_MIN_WORDS = 150
FOLLOWUP_MAX_TOKENS = 180
FOLLOWUP_DEFAULT_MODEL = "openai/gpt-oss-20b"

READY_MESSAGE = (
    "Great! We have enough information to generate your script. "
    "You can now click Generate Script whenever you're ready."
)

# 3 Semantic Buckets for uncovered argument slots
GROUP_MAIN = "Main thesis & key points"
GROUP_EVIDENCE = "Examples / evidence / data"
GROUP_COUNTER = "Counter-arguments / limitations"

_EVIDENCE_KEYWORDS = (
    "evidence",
    "example",
    "data",
    "practice",
    "detail",
    "case",
    "study",
    "statistic",
    "empiric",
)
_COUNTER_KEYWORDS = (
    "counter",
    "limitation",
    "challenge",
    "alternative",
    "tradeoff",
    "opposing",
    "objection",
)
_MAIN_KEYWORDS = (
    "foundation",
    "development",
    "mechanism",
    "thesis",
    "pillar",
    "synthesis",
    "context",
)


def classify_argument_slot(slot_name: str) -> str:
    """Classify an argument slot into one of 3 semantic buckets."""
    lower_name = slot_name.lower()
    for kw in _COUNTER_KEYWORDS:
        if kw in lower_name:
            return GROUP_COUNTER
    for kw in _EVIDENCE_KEYWORDS:
        if kw in lower_name:
            return GROUP_EVIDENCE
    for kw in _MAIN_KEYWORDS:
        if kw in lower_name:
            return GROUP_MAIN
    return GROUP_MAIN


def group_uncovered_slots(uncovered_slots: list[TemplateSlot | str]) -> list[str]:
    """Group uncovered argument slots into at most 3 semantic buckets preserving order."""
    if not uncovered_slots:
        return []

    names = [s.name if isinstance(s, TemplateSlot) else str(s) for s in uncovered_slots]
    assigned_groups = {classify_argument_slot(name) for name in names}

    ordered_groups = [GROUP_MAIN, GROUP_EVIDENCE, GROUP_COUNTER]
    return [g for g in ordered_groups if g in assigned_groups]


@dataclass
class ChatSessionState:
    """In-memory ephemeral state for a single user's script crafting conversation."""

    session_id: str
    user_id: str
    category: str
    duration_min: int
    initial_prompt: str = ""
    selected_template_id: str | None = None
    files_loaded: list[str] = field(default_factory=list)
    chunks: list[DocumentChunk] = field(default_factory=list)
    chunk_embeddings: Any | None = None  # NDArray[np.float32] normalized
    user_notes: list[str] = field(default_factory=list)
    gather_turns: int = 0
    coverage_ratio: float = 0.0
    missing_entities: list[str] = field(default_factory=list)
    missing_groups: list[str] = field(default_factory=list)
    ready_to_generate: bool = False
    last_active_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update last active timestamp for sliding TTL."""
        self.last_active_at = time.time()


class ChatSessionStore:
    """Thread-safe in-memory LRU store with sliding TTL for ephemeral chat sessions."""

    def __init__(
        self,
        capacity: int = DEFAULT_STORE_CAPACITY,
        ttl_seconds: float = DEFAULT_STORE_TTL_SECONDS,
    ) -> None:
        self._capacity = capacity
        self._ttl_seconds = ttl_seconds
        self._sessions: OrderedDict[str, ChatSessionState] = OrderedDict()
        self._lock = threading.Lock()

    def _prune_expired_locked(self, now: float) -> None:
        """Prune expired sessions while holding the lock."""
        expired_keys = [
            sid
            for sid, state in self._sessions.items()
            if (now - state.last_active_at) > self._ttl_seconds
        ]
        for sid in expired_keys:
            del self._sessions[sid]

    def get(self, session_id: str, user_id: str) -> ChatSessionState | None:
        """Retrieve a session by ID with strict user_id scoping and sliding TTL."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)

            session = self._sessions.get(session_id)
            if session is None:
                return None

            if session.user_id != user_id:
                logger.warning(
                    "Tenant isolation check failed: session_id=%s, "
                    "expected user_id=%s, actual user_id=%s",
                    session_id,
                    user_id,
                    session.user_id,
                )
                return None

            if (now - session.last_active_at) > self._ttl_seconds:
                del self._sessions[session_id]
                return None

            self._sessions.move_to_end(session_id)
            session.touch()
            return session

    def put(self, session: ChatSessionState) -> None:
        """Store or update a session with capacity eviction and sliding TTL."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)

            sid = session.session_id
            if sid in self._sessions:
                del self._sessions[sid]
            elif len(self._sessions) >= self._capacity:
                self._sessions.popitem(last=False)

            session.touch()
            self._sessions[sid] = session

    def delete(self, session_id: str, user_id: str) -> bool:
        """Remove a session if owned by user_id."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.user_id == user_id:
                del self._sessions[session_id]
                return True
            return False

    def clear(self) -> None:
        """Empty all sessions."""
        with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        with self._lock:
            self._prune_expired_locked(time.time())
            return len(self._sessions)


# Global store instance
chat_session_store = ChatSessionStore()


