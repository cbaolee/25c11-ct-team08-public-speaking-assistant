"""Content guards of the script chat and script generation routes.

Gibberish input (contract E v2) and material that belongs to another category. The category
helpers encode text with a local model, so call them off the event loop.
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Literal

from src.app.config import chat_session_store_capacity, chat_session_ttl_s, settings
from src.app.constants import CONSTANTS
from src.text_processing.category_guard import (
    CategoryMismatchError,
    check_category_alignment,
    normalize_category_slug,
    split_segments,
)
from src.text_processing.chat_session import ChatSessionState
from src.text_processing.contracts import ScriptGenerationError
from src.text_processing.input_guard import GIBBERISH_MESSAGE, is_gibberish
from src.text_processing.limiter import TokenBucketLimiter
from src.text_processing.parser import DocumentChunk
from src.text_processing.pipeline import ScriptGenerationPipeline

_MAX_SEGMENTS = int(CONSTANTS["script_guard"]["category_guard_max_segments"])
# What to store after a request: "verified" really passed, "skipped" was too short or has no
# known category; None (fail-open or unchecked content) stores nothing.
CategoryRecord = Literal["verified", "skipped"] | None


def reject_gibberish(*texts: str, has_file: bool) -> None:
    """Raise 422 `gibberish_input` when any text is junk; an attached file lets all pass."""
    if any(is_gibberish(text, has_file=has_file) for text in texts):
        raise ScriptGenerationError("gibberish_input", GIBBERISH_MESSAGE, status_code=422)


class CategoryDecisionStore:
    """Which session content already passed the category check: LRU with a sliding TTL.

    One entry per session holds the category slug, a hash of the content (never the content) and
    whether that content was verified. Its size and lifetime match the chat session store.
    """

    def __init__(
        self,
        capacity: int = chat_session_store_capacity,
        ttl_s: float = chat_session_ttl_s,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacity = capacity
        self._ttl_s = ttl_s
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, tuple[str, str], bool]] = OrderedDict()
        self._lock = threading.Lock()

    def remember(
        self, session_id: str, category_slug: str, content_key: str, *, verified: bool = False
    ) -> None:
        """Record that this content passed for this category; verified content stays verified."""
        decision = (category_slug, content_key)
        with self._lock:
            previous = self._entries.pop(session_id, None)
            if previous is not None and previous[1] == decision:
                verified = verified or previous[2]
            self._entries[session_id] = (self._clock(), decision, verified)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)

    def covers(
        self, session_id: str, category_slug: str, content_key: str, *, verified_only: bool = False
    ) -> bool:
        """Whether a live decision matches both; a match renews its lifetime."""
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                return False
            now = self._clock()
            stored_at, decision, verified = entry
            if now - stored_at > self._ttl_s:
                del self._entries[session_id]
                return False
            if decision != (category_slug, content_key) or (verified_only and not verified):
                return False
            self._entries[session_id] = (now, decision, verified)
            self._entries.move_to_end(session_id)
            return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


category_decisions = CategoryDecisionStore()


def _content_key(session: ChatSessionState) -> str:
    """Hash that changes with a new first prompt or a new file."""
    material = json.dumps([session.initial_prompt, session.files_loaded, len(session.chunks)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def remember_category_decision(session: ChatSessionState, record: CategoryRecord) -> None:
    """Call after the session update with what the guard of that request returned."""
    slug = normalize_category_slug(session.category)
    if slug is not None and record is not None:
        category_decisions.remember(
            session.session_id, slug, _content_key(session), verified=record == "verified"
        )


def _uses_template_of_category(
    pipeline: ScriptGenerationPipeline, session: ChatSessionState
) -> bool:
    """Whether the session already selected a template of its own category."""
    if not session.selected_template_id:
        return False
    template = pipeline.template_store.get(session.selected_template_id)
    return template is not None and template.metadata.category_slug == normalize_category_slug(
        session.category
    )


def _has_decision(
    session: ChatSessionState, category: str, *, verified_only: bool = False
) -> bool:
    """Whether a decision for `category` covers the current session content."""
    slug = normalize_category_slug(category)
    return slug is not None and category_decisions.covers(
        session.session_id, slug, _content_key(session), verified_only=verified_only
    )


def _old_content_covered(session: ChatSessionState | None, category: str) -> bool:
    """Whether the session holds no content yet, or a decision for `category` covers it."""
    if session is None or not (session.initial_prompt or session.chunks):
        return True
    return _has_decision(session, category)


def _assert_category(
    pipeline: ScriptGenerationPipeline,
    category: str,
    prompt: str,
    chunks: list[DocumentChunk],
    *,
    has_template_match: bool = False,
    client: Any | None = None,
    limiter: TokenBucketLimiter | None = None,
    allow_llm: bool = False,
) -> CategoryRecord:
    """Raise 422 `category_mismatch` when prompt and chunks clearly belong elsewhere.

    Otherwise say how the material passed.
    """
    result = check_category_alignment(
        selected_category=category,
        segments=split_segments(prompt, chunks, max_segments=_MAX_SEGMENTS),
        whole_text="\n".join(text for text in (prompt, *(c.content for c in chunks)) if text),
        has_template_match=has_template_match,
        retriever=getattr(pipeline.template_engine, "retriever", None),
        client=client,
        model=settings.groq_compaction_model,
        limiter=limiter,
        allow_llm=allow_llm,
    )
    if not result.allowed and result.suggested_category:
        raise CategoryMismatchError(result.selected_category, result.suggested_category)
    if result.layer == "fail_open":
        return None
    return "skipped" if result.layer == "skipped" else "verified"


def guard_category_suggest(
    pipeline: ScriptGenerationPipeline,
    *,
    session: ChatSessionState | None,
    category: str,
    prompt: str,
    file_chunks: list[DocumentChunk],
    has_template_match: bool,
    client: Any | None,
    limiter: TokenBucketLimiter | None,
) -> CategoryRecord:
    """`/suggest`, before the session changes; returns what to store afterwards.

    A new file is scored (with this request's prompt only) only while the session has no
    verified content for this category; a verified session takes it unscored.
    Otherwise, and for a different new prompt sent with such a file, the first prompt, the new
    prompt and the session chunks are scored together.
    """
    trusted_file = bool(file_chunks) and session is not None and _has_decision(
        session, category, verified_only=True
    )
    if trusted_file and prompt in ("", session.initial_prompt):
        return "verified"
    scores_file = bool(file_chunks) and not trusted_file
    if scores_file:
        text, chunks = prompt, file_chunks
    else:
        first_prompt = session.initial_prompt if session else ""
        text = "\n".join(part for part in dict.fromkeys((first_prompt, prompt)) if part)
        chunks = session.chunks if session else []
    record = _assert_category(
        pipeline,
        category,
        text,
        chunks,
        has_template_match=has_template_match,
        client=client,
        limiter=limiter,
        allow_llm=True,
    )
    if record is None:
        return None
    if trusted_file:
        return "verified"
    if scores_file and not has_template_match and not _old_content_covered(session, category):
        return None
    return record


def guard_category_message_file(
    pipeline: ScriptGenerationPipeline,
    session: ChatSessionState,
    message: str,
    file_chunks: list[DocumentChunk],
    *,
    client: Any | None,
    limiter: TokenBucketLimiter | None,
) -> CategoryRecord:
    """A chat turn with a new file, before the session changes; returns what to store afterwards.

    The message and the new file chunks are scored only while the session has no verified
    content for its category; a verified session takes the file unscored.
    A template pass or older content without a decision stores nothing.
    """
    if _has_decision(session, session.category, verified_only=True):
        return "verified"
    template_pass = _uses_template_of_category(pipeline, session)
    record = _assert_category(
        pipeline,
        session.category,
        message,
        file_chunks,
        has_template_match=template_pass,
        client=client,
        limiter=limiter,
        allow_llm=True,
    )
    if template_pass or not _old_content_covered(session, session.category):
        return None
    return record


def guard_category_generate(
    pipeline: ScriptGenerationPipeline,
    *,
    session: ChatSessionState | None,
    category: str,
    topic: str,
    raw_text: str,
) -> None:
    """`/generate-script`: local layer only, never the LLM.

    A session brings its own category (`category` is the form field, used without a session).
    Its content is skipped when an earlier decision covers it; `raw_text` is always new.
    """
    if session is None:
        text = "\n".join(part for part in (topic, raw_text) if part.strip())
        _assert_category(pipeline, category, text, [])
        return
    slug = normalize_category_slug(session.category)
    if slug is None or _uses_template_of_category(pipeline, session):
        return
    if not category_decisions.covers(session.session_id, slug, _content_key(session)):
        _assert_category(pipeline, slug, session.initial_prompt, session.chunks)
    if raw_text.strip():
        _assert_category(pipeline, slug, raw_text, [])
