"""In-memory ephemeral chat session management, bounded context, and Groq Q&A engine.

Responsibilities:
- Manage ChatSessionState lifecycle with 30-minute sliding TTL and multi-tenant isolation.
- Perform 0-token slot coverage analysis with cosine similarity via SemanticRetriever.
- Group uncovered argument slots into at most 3 semantic buckets.
- Maintain a bounded context window (sanitize -> moderate -> normalize/extract -> compact).
- Compact older context entries using a configurable smaller Groq model (with rule fallback).
- Run a continuous Groq-powered Q&A loop (Turn 1 gating + Turn 2+ JSON evaluation).
- Track granular processing steps and +10s-buffered ETA telemetry per chat turn.
- Ingest .pdf, .md, and .txt files into DocumentChunk items with immediate disk cleanup.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from src.app.config import settings
from src.app.constants import CONSTANTS

from .contracts import (
    DocumentChunk,
    TemplateDocument,
    TemplateSlot,
    TopicMetadata,
)
from .limiter import TokenBucketLimiter
from .parser import (
    MAX_PDF_SIZE_BYTES,
    MAX_TEXT_FILE_BYTES,
    DocumentParserError,
    validate_and_parse_document,
)
from .sanitizer import sanitize_text
from .template_engine import parse_slots

if TYPE_CHECKING:
    from .retrieval import SemanticRetriever

logger = logging.getLogger(__name__)

# Constants
DEFAULT_STORE_CAPACITY = 100
DEFAULT_STORE_TTL_SECONDS = 1800.0  # 30 minutes
COSINE_SIMILARITY_THRESHOLD = 0.35
FREE_TOPIC_MIN_WORDS = 150
TURN1_MAX_TOKENS = 160
FOLLOWUP_MAX_TOKENS = 220
COMPACTION_MAX_TOKENS = 300
FOLLOWUP_DEFAULT_MODEL = "openai/gpt-oss-20b"
_DEFAULT_QA_MODEL_CHAIN: tuple[str, ...] = (
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
)

_SCRIPT_CFG = CONSTANTS["script"]
CONTEXT_WINDOW_MAX_CHARS = int(_SCRIPT_CFG["context_window_max_chars"])
CONTEXT_WINDOW_MAX_ENTRIES = int(_SCRIPT_CFG["context_window_max_entries"])
CONTEXT_COMPACTION_KEEP_RECENT = int(_SCRIPT_CFG["context_compaction_keep_recent"])
CONTEXT_COMPACTION_MAX_SUMMARY_CHARS = int(_SCRIPT_CFG["context_compaction_max_summary_chars"])
DEFAULT_COMPACTION_MODEL = str(_SCRIPT_CFG["groq_compaction_model"])
ETA_BUFFER_S = int(_SCRIPT_CFG["eta_buffer_s"])

CHAT_TURN_STEP_DURATIONS: dict[str, float] = {
    "validating_input": 0.5,
    "moderating": 1.0,
    "matching_templates": 1.5,
    "analyzing_slots": 1.0,
    "updating_context": 0.5,
    "compacting_context": 2.5,
    "analyzing_with_llm": 3.5,
}

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

_FILLER_PREFIX_RE = re.compile(
    r"^(?:(?:hi|hello|hey|ok|okay|sure|yes|yeah|yep|alright|well|please|thanks|thank you)"
    r"(?:[\s,!.]+)+)+",
    re.IGNORECASE,
)
_LEADIN_FILLER_RE = re.compile(
    r"^(?:go ahead(?: and)?|here(?:'s| is| are)(?: my| the| some)?|"
    r"i(?:'d| would) like to(?: talk| speak)? about)\s*[:,.\-]?\s*",
    re.IGNORECASE,
)

# Shared limiter for pre-generation Q&A & compaction when caller does not supply one
_QA_LIMITER = TokenBucketLimiter()


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
class ContextEntry:
    """One normalized, bounded entry in a session's active context window."""

    turn: int
    source: Literal["prompt", "chat", "feedback", "file_summary"]
    text: str
    char_count: int = 0
    est_tokens: int = 0

    def __post_init__(self) -> None:
        if self.char_count <= 0 and self.text:
            self.char_count = len(self.text)
        if self.est_tokens <= 0 and self.text:
            self.est_tokens = max(1, int(len(self.text.split()) * 1.35))

    def formatted(self) -> str:
        """Return turn-and-source tagged context line for LLM prompts."""
        return f"[Turn {self.turn} | {self.source}] {self.text}"


class TurnStepTracker:
    """Track ordered processing steps and +10s-buffered ETA for chat turns."""

    def __init__(
        self,
        step_keys: list[str] | tuple[str, ...],
        *,
        eta_buffer_s: int = ETA_BUFFER_S,
        durations: dict[str, float] | None = None,
    ) -> None:
        self._durations = durations or CHAT_TURN_STEP_DURATIONS
        self.eta_buffer_s = int(eta_buffer_s)
        self.steps: list[dict[str, str]] = [
            {"key": key, "state": "pending"} for key in step_keys
        ]
        self.stage: str = step_keys[0] if step_keys else "completed"
        self.started_at = time.monotonic()

    def start(self, key: str) -> None:
        for step in self.steps:
            if step["state"] == "running":
                step["state"] = "done"
            if step["key"] == key:
                step["state"] = "running"
                self.stage = key

    def done(self, key: str) -> None:
        for step in self.steps:
            if step["key"] == key:
                step["state"] = "done"

    def skip(self, key: str) -> None:
        for step in self.steps:
            if step["key"] == key and step["state"] == "pending":
                step["state"] = "skipped"

    def finish(self) -> None:
        for step in self.steps:
            if step["state"] in ("pending", "running"):
                step["state"] = "done"
        self.stage = "completed"

    def fail(self) -> None:
        self.stage = "failed"

    @property
    def progress(self) -> int:
        if not self.steps:
            return 100
        completed = sum(1 for s in self.steps if s["state"] in ("done", "skipped"))
        running = sum(0.5 for s in self.steps if s["state"] == "running")
        return min(100, int(round(((completed + running) / len(self.steps)) * 100)))

    @property
    def estimated_total_s(self) -> float:
        base = sum(
            self._durations.get(s["key"], 1.0)
            for s in self.steps
            if s["state"] != "skipped"
        )
        return round(base + self.eta_buffer_s, 1)

    @property
    def estimated_remaining_s(self) -> float:
        if self.stage in ("completed", "failed"):
            return 0.0
        rem = sum(
            self._durations.get(s["key"], 1.0)
            for s in self.steps
            if s["state"] in ("pending", "running")
        )
        if rem <= 0.0:
            return 0.0
        return round(rem + self.eta_buffer_s, 1)

    def to_telemetry(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "progress": self.progress,
            "steps": [dict(s) for s in self.steps],
            "eta_buffer_s": self.eta_buffer_s,
            "estimated_total_s": self.estimated_total_s,
            "estimated_remaining_s": self.estimated_remaining_s,
        }


@dataclass
class FollowupDecision:
    """Structured Groq Q&A evaluation result for Turn 2+."""

    sufficient: bool
    missing_items: list[str]
    reply_message: str
    used_llm: bool = False


@dataclass
class ChatSessionState:
    """In-memory ephemeral state for a single user's script crafting conversation."""

    session_id: str
    user_id: str
    category: str
    duration_min: int
    initial_prompt: str = ""
    selected_template_id: str | None = None
    topic: str | None = None
    files_loaded: list[str] = field(default_factory=list)
    chunks: list[DocumentChunk] = field(default_factory=list)
    chunk_embeddings: Any | None = None  # NDArray[np.float32] normalized
    user_notes: list[str] = field(default_factory=list)
    context_window: list[ContextEntry] = field(default_factory=list)
    compacted_summary: str = ""
    compaction_count: int = 0
    gather_turns: int = 0
    assistant_turn: int = 0
    last_question: str = ""
    missing_items: list[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    missing_entities: list[str] = field(default_factory=list)
    missing_groups: list[str] = field(default_factory=list)
    ready_to_generate: bool = False
    last_active_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update last active timestamp for sliding TTL."""
        self.last_active_at = time.time()

    def get_context_texts(self, *, include_summary: bool = False) -> list[str]:
        """Return active bounded context texts (with legacy `user_notes` fallback)."""
        texts: list[str] = []
        if include_summary and self.compacted_summary.strip():
            texts.append(self.compacted_summary.strip())
        if self.context_window:
            texts.extend(e.text for e in self.context_window if e.text.strip())
        elif self.user_notes:
            texts.extend(n.strip() for n in self.user_notes if n.strip())
        return texts

    def context_char_count(self) -> int:
        """Total characters currently held in compacted summary + active window."""
        return len(self.compacted_summary) + sum(e.char_count for e in self.context_window)


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


# ---------------------------------------------------------------------------
# Raw-to-Context Normalization & Bounded Compaction
# ---------------------------------------------------------------------------


def _truncate_cleanly(text: str, max_chars: int) -> str:
    """Truncate text cleanly at a sentence or word boundary within `max_chars`."""
    if max_chars <= 0:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    cut = text[: max_chars - 3].rstrip()
    last_space = cut.rfind(" ")
    if last_space > max_chars // 2:
        cut = cut[:last_space].rstrip()
    return f"{cut}..."


def normalize_turn_entry(
    raw_text: str,
    *,
    turn: int = 1,
    source: Literal["prompt", "chat", "feedback", "file_summary"] = "chat",
    max_entry_chars: int | None = None,
) -> ContextEntry | None:
    """Sanitize and normalize raw user text into a concise factual ContextEntry."""
    cleaned = sanitize_text(raw_text)
    if not cleaned:
        return None

    # Collapse excessive blank lines while preserving intentional multi-line headings/notes
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in cleaned.splitlines()]
    compact = "\n".join(ln for ln in lines if ln).strip()
    if not compact:
        return None

    # Strip leading conversational filler only when substantive content follows
    stripped = _FILLER_PREFIX_RE.sub("", compact).strip()
    stripped = _LEADIN_FILLER_RE.sub("", stripped).strip()
    if stripped and len(stripped.split()) >= 3:
        compact = stripped

    ceiling = (
        max_entry_chars
        if max_entry_chars is not None
        else max(500, CONTEXT_WINDOW_MAX_CHARS - 500)
    )
    compact = _truncate_cleanly(compact, ceiling)
    if not compact:
        return None
    return ContextEntry(turn=turn, source=source, text=compact)


def deterministic_compact_summary(
    existing_summary: str,
    entries: list[ContextEntry],
    *,
    max_chars: int = CONTEXT_COMPACTION_MAX_SUMMARY_CHARS,
) -> str:
    """Deterministically compact older context entries without calling an LLM."""
    raw_lines: list[str] = []
    if existing_summary and existing_summary.strip():
        for ln in existing_summary.splitlines():
            clean_ln = re.sub(r"^[•\-\*\s]+", "", ln).strip()
            if clean_ln:
                raw_lines.append(clean_ln)

    for entry in entries:
        parts = re.split(r"(?:\n+|(?<=[.!?])\s+)", entry.text.strip())
        for part in parts:
            clean_part = re.sub(r"^[•\-\*\s]+", "", part).strip()
            if clean_part:
                raw_lines.append(clean_part)

    # Deduplicate while preserving chronological order
    seen: set[str] = set()
    unique_lines: list[str] = []
    for ln in raw_lines:
        key = re.sub(r"\s+", " ", ln.lower()).strip(".,;:")
        if key and key not in seen:
            seen.add(key)
            unique_lines.append(ln)

    if not unique_lines:
        return ""

    # Prefer keeping newer/higher-signal facts if the combined summary exceeds max_chars
    bullets = [f"- {ln}" for ln in unique_lines]
    joined = "\n".join(bullets)
    if len(joined) <= max_chars:
        return joined

    # Drop oldest short/low-signal bullets first, keeping newest facts intact
    kept = list(bullets)
    while len("\n".join(kept)) > max_chars and len(kept) > 1:
        # Prefer dropping oldest item under 8 words without digits, else oldest item
        drop_idx = 0
        for idx in range(len(kept) - 1):
            item = kept[idx]
            if len(item.split()) < 8 and not any(ch.isdigit() for ch in item):
                drop_idx = idx
                break
        kept.pop(drop_idx)

    result = "\n".join(kept)
    if len(result) > max_chars:
        result = _truncate_cleanly(result, max_chars)
    return result


def _resolve_compaction_model(model: str | None = None) -> str:
    if model and model.strip():
        return model.strip()
    cfg_model = (getattr(settings, "groq_compaction_model", "") or "").strip()
    return cfg_model or DEFAULT_COMPACTION_MODEL


def compact_context_entries(
    existing_summary: str,
    entries: list[ContextEntry],
    *,
    topic: str = "",
    client: Any | None = None,
    model: str | None = None,
    limiter: TokenBucketLimiter | None = None,
    max_summary_chars: int = CONTEXT_COMPACTION_MAX_SUMMARY_CHARS,
) -> tuple[str, bool]:
    """Compact older context entries using smaller Groq model with deterministic fallback."""
    if not entries and not existing_summary.strip():
        return "", False

    target_model = _resolve_compaction_model(model)
    active_limiter = limiter or _QA_LIMITER

    if client is None:
        return deterministic_compact_summary(
            existing_summary, entries, max_chars=max_summary_chars
        ), False

    entries_block = "\n".join(e.formatted() for e in entries)
    prior_block = (
        f"Existing summary:\n{existing_summary.strip()}\n\n"
        if existing_summary.strip()
        else ""
    )
    user_prompt = (
        f"Topic: {topic or 'Speech'}\n"
        f"{prior_block}"
        f"Older turns to compact:\n{entries_block}"
    )
    est_tokens = max(90, int(len(user_prompt) / 3.5) + COMPACTION_MAX_TOKENS)

    wait = active_limiter.wait_time_s(target_model, est_tokens)
    if wait > 5.0 or not active_limiter.can_consume(target_model, est_tokens):
        logger.info(
            "Compaction rate budget tight for %s; using deterministic fallback.", target_model
        )
        return deterministic_compact_summary(
            existing_summary, entries, max_chars=max_summary_chars
        ), False

    system_prompt = (
        "Compress the speaker's older notes into dense factual bullets (<= 140 words). "
        "Preserve concrete facts, names, audience, numbers, constraints, and examples. "
        'Return strict JSON: {"summary": "- fact 1\\n- fact 2"}.'
    )

    try:
        resp = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=COMPACTION_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        raw_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
        tokens_used = raw_tokens if isinstance(raw_tokens, int) else est_tokens
        active_limiter.consume(target_model, tokens_used)

        summary_text = ""
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    summary_text = str(parsed.get("summary", "")).strip()
            except json.JSONDecodeError:
                summary_text = raw

        if summary_text:
            return _truncate_cleanly(summary_text, max_summary_chars), True
    except Exception as exc:
        logger.warning(
            "Groq compaction with %s failed (%s); using deterministic fallback.",
            target_model,
            exc,
        )

    return deterministic_compact_summary(
        existing_summary, entries, max_chars=max_summary_chars
    ), False


def append_to_context_window(
    session: ChatSessionState,
    raw_text: str,
    *,
    turn: int,
    source: Literal["prompt", "chat", "feedback", "file_summary"] = "chat",
    moderator: Any | None = None,
    client: Any | None = None,
    compaction_model: str | None = None,
    limiter: TokenBucketLimiter | None = None,
    max_chars: int | None = None,
    max_entries: int | None = None,
    keep_recent: int | None = None,
    max_summary_chars: int | None = None,
) -> tuple[ContextEntry | None, bool]:
    """Run sanitize -> moderate -> normalize -> append -> compact if ceiling exceeded."""
    cleaned = sanitize_text(raw_text)
    if not cleaned:
        return None, False

    if moderator is not None:
        moderator.assert_safe(cleaned, user_id=session.user_id)

    eff_max_chars = max_chars if max_chars is not None else CONTEXT_WINDOW_MAX_CHARS
    eff_max_entries = max_entries if max_entries is not None else CONTEXT_WINDOW_MAX_ENTRIES
    eff_keep_recent = max(
        1, keep_recent if keep_recent is not None else CONTEXT_COMPACTION_KEEP_RECENT
    )
    eff_summary_chars = (
        max_summary_chars
        if max_summary_chars is not None
        else CONTEXT_COMPACTION_MAX_SUMMARY_CHARS
    )

    entry = normalize_turn_entry(
        cleaned,
        turn=turn,
        source=source,
        max_entry_chars=max(400, eff_max_chars - 500),
    )
    if entry is None:
        return None, False

    session.context_window.append(entry)

    active_chars = sum(e.char_count for e in session.context_window)
    total_chars = len(session.compacted_summary) + active_chars
    exceeds = len(session.context_window) > eff_max_entries or total_chars > eff_max_chars
    if not exceeds:
        return entry, False

    if len(session.context_window) > eff_keep_recent:
        to_compact = session.context_window[:-eff_keep_recent]
        kept = session.context_window[-eff_keep_recent:]
    elif len(session.context_window) > 1:
        # Always keep at least the latest answer intact
        to_compact = session.context_window[:-1]
        kept = session.context_window[-1:]
    else:
        to_compact = []
        kept = list(session.context_window)

    summary_budget = min(
        eff_summary_chars,
        max(200, eff_max_chars - sum(e.char_count for e in kept)),
    )

    if to_compact:
        new_summary, _ = compact_context_entries(
            session.compacted_summary,
            to_compact,
            topic=session.topic or session.initial_prompt or "",
            client=client,
            model=compaction_model,
            limiter=limiter,
            max_summary_chars=summary_budget,
        )
        session.compacted_summary = new_summary
        session.context_window = kept
        session.compaction_count += 1
        return entry, True

    # Single oversized entry + existing summary pushed over ceiling: shrink existing summary
    if session.compacted_summary:
        session.compacted_summary = _truncate_cleanly(session.compacted_summary, summary_budget)
        session.compaction_count += 1
        return entry, True

    return entry, False


# ---------------------------------------------------------------------------
# Slot Coverage & Continuous Groq Q&A
# ---------------------------------------------------------------------------


def analyze_slot_coverage(
    template_document: str | TemplateDocument,
    chunks: list[DocumentChunk],
    chunk_embeddings: Any | None,
    retriever: SemanticRetriever | None,
    prompt: str = "",
    user_notes: list[str] | None = None,
) -> tuple[float, list[str], list[str]]:
    """Perform deterministic 0-token slot coverage analysis.

    Returns:
        tuple of (coverage_ratio, missing_entities, missing_groups)
    """
    if isinstance(template_document, str):
        template = TemplateDocument(
            metadata=TopicMetadata(
                template_id="virtual/custom",
                category_slug="custom",
                category="Custom",
                topic="Custom Topic",
                topic_slug="custom_topic",
                duration_min=5,
            ),
            body=template_document,
            file_path="",
        )
    else:
        template = template_document

    slots = parse_slots(template)
    argument_slots = [
        s for s in slots if s.name.startswith("argument_") or s.slot_type == "argument"
    ]
    entity_slots = [
        s for s in slots if not (s.name.startswith("argument_") or s.slot_type == "argument")
    ]

    # Check argument slot coverage
    uncovered_arguments: list[TemplateSlot] = []
    if not argument_slots:
        coverage_ratio = 1.0
    elif not chunks or chunk_embeddings is None:
        coverage_ratio = 0.0
        uncovered_arguments = list(argument_slots)
    else:
        model = retriever.get_model() if retriever is not None else None
        covered_count = 0

        for slot in argument_slots:
            query = f"{slot.lead_in} {slot.name.replace('_', ' ')}".strip()
            max_cosine = 0.0

            if model is not None:
                query_vec = retriever._encode(model, [query])
                scores = (chunk_embeddings @ query_vec.T).squeeze()
                scores_arr = np.atleast_1d(scores)
                max_cosine = float(np.max(scores_arr)) if scores_arr.size > 0 else 0.0
            else:
                # Deterministic word overlap fallback when model is None
                query_words = set(re.findall(r"\w+", query.lower()))
                for chunk in chunks:
                    chunk_words = set(re.findall(r"\w+", chunk.content.lower()))
                    if query_words and chunk_words:
                        overlap = len(query_words & chunk_words) / len(query_words)
                        if overlap > max_cosine:
                            max_cosine = overlap

            if max_cosine >= COSINE_SIMILARITY_THRESHOLD:
                covered_count += 1
            else:
                uncovered_arguments.append(slot)

        coverage_ratio = covered_count / len(argument_slots)

    missing_groups = group_uncovered_slots(uncovered_arguments)

    # Check entity slot coverage
    missing_entities: list[str] = []
    notes_list = user_notes or []
    user_context = f"{prompt} {' '.join(notes_list)}".lower()

    model = retriever.get_model() if retriever is not None else None
    has_embeddings = chunks and chunk_embeddings is not None and model is not None

    for slot in entity_slots:
        clean_name = slot.name.removeprefix("entity_").replace("_", " ").lower().strip()
        tokens = [t for t in re.findall(r"\w+", clean_name) if len(t) >= 3]

        # 1. Direct match in prompt or user context
        is_in_text = clean_name in user_context or (
            tokens and all(token in user_context for token in tokens)
        )
        if is_in_text:
            continue

        # 2. Check semantic similarity against chunks if available
        is_in_chunks = False
        if has_embeddings:
            query_vec = retriever._encode(model, [clean_name])
            scores = (chunk_embeddings @ query_vec.T).squeeze()
            scores_arr = np.atleast_1d(scores)
            max_sim = float(np.max(scores_arr)) if scores_arr.size > 0 else 0.0
            if max_sim >= COSINE_SIMILARITY_THRESHOLD:
                is_in_chunks = True

        if not is_in_chunks:
            missing_entities.append(slot.name)

    return coverage_ratio, missing_entities, missing_groups


def check_ready_to_generate(
    *,
    selected_template_id: str | None,
    missing_entities: list[str],
    coverage_ratio: float,
    gather_turns: int = 0,
    files_loaded: list[str] | None = None,
    prompt: str = "",
    user_notes: list[str] | None = None,
) -> bool:
    """Deterministic readiness evaluation (no 2-turn forced hard stop)."""
    _ = gather_turns  # kept in signature for caller compatibility; no forced turn cap
    if selected_template_id is not None:
        return len(missing_entities) == 0 and coverage_ratio >= 0.7

    has_files = bool(files_loaded and len(files_loaded) > 0)
    all_text = f"{prompt} {' '.join(user_notes or [])}".strip()
    word_count = len(all_text.split())
    return has_files or word_count >= FREE_TOPIC_MIN_WORDS


def _clean_entity_label(entity_name: str) -> str:
    return entity_name.removeprefix("entity_").replace("_", " ").strip()


def _ensure_bold_keys(reply: str, keys: list[str]) -> str:
    """Ensure key requested items appear wrapped in **bold** markers for UI scannability."""
    if "**" in reply or not keys:
        return reply
    formatted_keys = ", ".join(f"**{k}**" for k in keys[:3] if k)
    if not formatted_keys:
        return reply
    return f"{reply.rstrip()} (Key focus: {formatted_keys})"


def format_checklist_fallback(
    topic: str,
    missing_entities: list[str],
    missing_groups: list[str],
    *,
    is_free_topic: bool = False,
) -> str:
    """Generate a deterministic 0-token follow-up with **bold** key requests."""
    if is_free_topic:
        return (
            f"To shape your speech on '{topic}', could you share your **central thesis**, "
            f"**target audience**, and any **supporting examples** or reference notes?"
        )
    lines = [f"To help craft your speech on '{topic}', please share a bit more detail on:"]
    if missing_entities:
        clean_entities = [f"**{_clean_entity_label(e)}**" for e in missing_entities]
        lines.append(f"- Specific details: {', '.join(clean_entities)}")
    if missing_groups:
        bold_groups = [f"**{g}**" for g in missing_groups]
        lines.append(f"- Key areas: {', '.join(bold_groups)}")
    if not missing_entities and not missing_groups:
        lines.append(
            "- Your **target audience**, **key examples**, and any specific **tone** preference."
        )
    return "\n".join(lines)


def _get_qa_model_chain(model_chain: tuple[str, ...] | None = None) -> tuple[str, ...]:
    if model_chain:
        return model_chain
    configured = [
        (getattr(settings, "groq_llm_model", "") or "").strip(),
        (getattr(settings, "groq_llm_fallback_model_1", "") or "").strip(),
        (getattr(settings, "groq_llm_fallback_model_2", "") or "").strip(),
    ]
    chain = list(dict.fromkeys(m for m in configured if m))
    return tuple(chain) if chain else _DEFAULT_QA_MODEL_CHAIN


def _derive_missing_items(
    *,
    is_free_topic: bool,
    missing_entities: list[str] | None = None,
    missing_groups: list[str] | None = None,
    context_text: str = "",
    files_loaded: list[str] | None = None,
) -> list[str]:
    if not is_free_topic:
        items = [_clean_entity_label(e) for e in (missing_entities or [])]
        items.extend(missing_groups or [])
        return items or ["target audience", "supporting examples"]

    lower = context_text.lower()
    missing: list[str] = []
    if len(context_text.split()) < 15:
        missing.append("central thesis")
    if not any(
        w in lower for w in ("audience", "student", "listener", "team", "executive", "public")
    ):
        missing.append("target audience")
    if not files_loaded and not any(
        w in lower for w in ("example", "case", "study", "data", "story", "stat")
    ):
        missing.append("supporting examples")
    if not any(w in lower for w in ("tone", "goal", "takeaway", "call to action", "conclude")):
        missing.append("key takeaway")
    return missing or ["tone or extra examples"]


def build_turn1_question(
    *,
    topic: str,
    category: str = "",
    duration_min: int = 5,
    is_free_topic: bool = False,
    initial_prompt: str = "",
    files_loaded: list[str] | None = None,
    missing_entities: list[str] | None = None,
    missing_groups: list[str] | None = None,
    client: Any | None = None,
    model_chain: tuple[str, ...] | None = None,
    limiter: TokenBucketLimiter | None = None,
) -> tuple[str, list[str]]:
    """Build Turn 1 opening context question (always asks, never returns READY_MESSAGE)."""
    missing_items = _derive_missing_items(
        is_free_topic=is_free_topic,
        missing_entities=missing_entities,
        missing_groups=missing_groups,
        context_text=initial_prompt,
        files_loaded=files_loaded,
    )

    if client is None:
        return (
            _turn1_fallback_question(topic, missing_items, is_free_topic=is_free_topic),
            missing_items,
        )

    active_limiter = limiter or _QA_LIMITER
    chain = _get_qa_model_chain(model_chain)
    mode_label = "Free-topic speech" if is_free_topic else "Template-guided speech"
    files_note = ", ".join(files_loaded) if files_loaded else "None"

    system_prompt = (
        "You are a concise public-speaking coach starting a short Q&A before writing a speech. "
        "Ask 1-2 focused context questions tailored to the missing items. "
        "Wrap 1-3 key requested concepts in **bold** markdown (e.g. **target audience**). "
        "Keep under 65 words. Never tell the user to click Generate yet. "
        'Return strict JSON: {"reply_message": "...", "missing_items": ["..."]}.'
    )
    user_prompt = (
        f"Mode: {mode_label} | Category: {category or 'General'} | Duration: {duration_min} min\n"
        f"Topic: {topic}\n"
        f"Initial prompt: {initial_prompt.strip() or 'None'}\n"
        f"Uploaded files: {files_note}\n"
        f"Missing focus items: {', '.join(missing_items)}"
    )
    est_tokens = max(90, int(len(user_prompt) / 3.5) + TURN1_MAX_TOKENS)

    for model_id in chain:
        wait = active_limiter.wait_time_s(model_id, est_tokens)
        if wait > 5.0 or not active_limiter.can_consume(model_id, est_tokens):
            continue
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=TURN1_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            raw = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            raw_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
            tokens_used = raw_tokens if isinstance(raw_tokens, int) else est_tokens
            active_limiter.consume(model_id, tokens_used)

            reply = ""
            parsed_items = list(missing_items)
            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        reply = str(data.get("reply_message", "")).strip()
                        raw_items = data.get("missing_items")
                        if isinstance(raw_items, list) and raw_items:
                            parsed_items = [str(x).strip() for x in raw_items if str(x).strip()]
                except json.JSONDecodeError:
                    reply = raw
            if reply:
                return _ensure_bold_keys(reply, parsed_items), parsed_items
        except Exception as exc:
            logger.warning("Groq Turn 1 question failed on %s (%s)", model_id, exc)

    return (
        _turn1_fallback_question(topic, missing_items, is_free_topic=is_free_topic),
        missing_items,
    )


def _turn1_fallback_question(topic: str, missing_items: list[str], *, is_free_topic: bool) -> str:
    bold_items = [f"**{item}**" for item in missing_items[:3]]
    joined = ", ".join(bold_items) if bold_items else "**target audience** and **key examples**"
    if is_free_topic:
        return (
            f"Let's plan your speech on '{topic}'. "
            f"To start, could you share your {joined}?"
        )
    return (
        f"Great choice on '{topic}'. "
        f"Before drafting, could you share more about your {joined}?"
    )


def evaluate_and_build_followup(
    *,
    topic: str,
    category: str = "",
    duration_min: int = 5,
    is_free_topic: bool = False,
    compacted_summary: str = "",
    context_entries: list[ContextEntry] | None = None,
    latest_user_answer: str = "",
    missing_entities: list[str] | None = None,
    missing_groups: list[str] | None = None,
    coverage_ratio: float = 0.0,
    files_loaded: list[str] | None = None,
    initial_prompt: str = "",
    client: Any | None = None,
    model_chain: tuple[str, ...] | None = None,
    limiter: TokenBucketLimiter | None = None,
) -> FollowupDecision:
    """Turn 2+: Evaluate context sufficiency and generate next Groq follow-up in 1 call."""
    entries = context_entries or []
    combined_texts = [e.text for e in entries]
    if compacted_summary.strip():
        combined_texts.insert(0, compacted_summary.strip())
    all_context_text = " ".join(
        [initial_prompt.strip(), *combined_texts, latest_user_answer.strip()]
    ).strip()

    fallback_missing = _derive_missing_items(
        is_free_topic=is_free_topic,
        missing_entities=missing_entities,
        missing_groups=missing_groups,
        context_text=all_context_text,
        files_loaded=files_loaded,
    )
    fallback_sufficient = check_ready_to_generate(
        selected_template_id=None if is_free_topic else "selected",
        missing_entities=missing_entities or [],
        coverage_ratio=coverage_ratio,
        files_loaded=files_loaded,
        prompt=initial_prompt,
        user_notes=combined_texts,
    )

    if client is not None:
        active_limiter = limiter or _QA_LIMITER
        chain = _get_qa_model_chain(model_chain)

        window_block = "\n".join(e.formatted() for e in entries) or "None"
        summary_block = compacted_summary.strip() or "None"
        files_note = ", ".join(files_loaded) if files_loaded else "None"

        if is_free_topic:
            criteria_block = (
                "Free-topic readiness criteria: central thesis, target audience, "
                "supporting arguments/examples, and clear takeaway/tone.\n"
                f"Currently likely missing: {', '.join(fallback_missing)}"
            )
        else:
            ent_text = (
                ", ".join(_clean_entity_label(e) for e in (missing_entities or [])) or "None"
            )
            grp_text = ", ".join(missing_groups or []) or "None"
            criteria_block = (
                f"Template slot coverage: {coverage_ratio:.0%}\n"
                f"Missing entities: {ent_text}\n"
                f"Missing content areas: {grp_text}"
            )

        system_prompt = (
            "You are a public-speaking coach gathering context before script generation. "
            "Judge if the bounded context is sufficient to write a strong speech. "
            "If insufficient (or if extra details would noticeably improve it), ask 1-2 focused "
            "questions wrapping key requested items in **bold** (e.g. **audience**, **examples**). "
            "If sufficient, confirm readiness briefly and invite any optional extra **examples** "
            "or **tone** notes. Keep reply under 80 words.\n"
            'Return JSON: {"sufficient": bool, "missing_items": [str], "reply_message": str}.'
        )
        user_prompt = (
            f"Topic: {topic} | Category: {category or 'General'} | Duration: {duration_min} min\n"
            f"Uploaded files: {files_note}\n"
            f"Compacted summary:\n{summary_block}\n"
            f"Active context window:\n{window_block}\n"
            f"Latest user answer: {latest_user_answer.strip() or '(file uploaded)'}\n"
            f"{criteria_block}"
        )
        est_tokens = max(120, int(len(user_prompt) / 3.5) + FOLLOWUP_MAX_TOKENS)

        for model_id in chain:
            wait = active_limiter.wait_time_s(model_id, est_tokens)
            if wait > 5.0 or not active_limiter.can_consume(model_id, est_tokens):
                continue
            try:
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=FOLLOWUP_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                raw = (resp.choices[0].message.content or "").strip()
                usage = getattr(resp, "usage", None)
                raw_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
                tokens_used = raw_tokens if isinstance(raw_tokens, int) else est_tokens
                active_limiter.consume(model_id, tokens_used)

                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    reply = str(parsed.get("reply_message", "")).strip()
                    if reply:
                        sufficient = bool(parsed.get("sufficient", fallback_sufficient))
                        raw_items = parsed.get("missing_items")
                        if isinstance(raw_items, list):
                            missing_items = [str(x).strip() for x in raw_items if str(x).strip()]
                        else:
                            missing_items = [] if sufficient else list(fallback_missing)
                        if not sufficient:
                            reply = _ensure_bold_keys(reply, missing_items or fallback_missing)
                        return FollowupDecision(
                            sufficient=sufficient,
                            missing_items=missing_items,
                            reply_message=reply,
                            used_llm=True,
                        )
            except Exception as exc:
                logger.warning("Groq Turn 2+ evaluation failed on %s (%s)", model_id, exc)

    # Deterministic rule-based fallback
    if fallback_sufficient:
        return FollowupDecision(
            sufficient=True,
            missing_items=[],
            reply_message=(
                f"We have strong context for **{topic}**! You can generate your script now, "
                f"or share any additional **examples** or **tone preferences**."
            ),
            used_llm=False,
        )

    reply = format_checklist_fallback(
        topic=topic,
        missing_entities=missing_entities or [],
        missing_groups=missing_groups or [],
        is_free_topic=is_free_topic,
    )
    if is_free_topic and fallback_missing:
        bold_items = ", ".join(f"**{item}**" for item in fallback_missing[:3])
        reply = (
            f"Thanks! To strengthen your speech on '{topic}', "
            f"could you provide more on {bold_items}?"
        )
    return FollowupDecision(
        sufficient=False,
        missing_items=fallback_missing,
        reply_message=reply,
        used_llm=False,
    )


def build_followup_reply(
    topic: str,
    ready_to_generate: bool,
    missing_entities: list[str],
    missing_groups: list[str],
    gather_turns: int = 0,
    client: Any | None = None,
    model: str | None = None,
) -> str:
    """Build follow-up message using Groq or deterministic **bold** checklist fallback."""
    _ = gather_turns  # 2-turn hard stop removed
    if ready_to_generate:
        return READY_MESSAGE

    if client is None:
        return format_checklist_fallback(topic, missing_entities, missing_groups)

    target_model = (
        model
        or getattr(settings, "groq_llm_fallback_model_2", FOLLOWUP_DEFAULT_MODEL)
        or FOLLOWUP_DEFAULT_MODEL
    )

    system_prompt = (
        "You are an expert speech coach helping a speaker prepare their presentation. "
        "Ask 1-2 focused, conversational follow-up questions to gather missing speech elements, "
        "wrapping key requested concepts in **bold** markers. "
        "Keep your response concise (under 75 words). Do not include pleasantries or greetings."
    )
    user_prompt = (
        f"Topic: {topic}\n"
        f"Missing specific details: {', '.join(missing_entities) if missing_entities else 'None'}\n"
        f"Missing key content areas: {', '.join(missing_groups) if missing_groups else 'None'}"
    )

    try:
        resp = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=FOLLOWUP_MAX_TOKENS,
        )
        reply = resp.choices[0].message.content.strip()
        if reply:
            return reply
    except Exception as exc:
        logger.warning(
            "Groq follow-up question generation failed (%s), using fallback checklist.", exc
        )

    return format_checklist_fallback(topic, missing_entities, missing_groups)


def ingest_upload_file(
    file_bytes: bytes,
    filename: str,
    ocr_runner: Any | None = None,
) -> list[DocumentChunk]:
    """Ingest uploaded .pdf, .md, or .txt document into DocumentChunks and clean up temp file."""
    if not file_bytes:
        raise DocumentParserError("empty_file", "The uploaded file is empty.")

    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".md", ".txt"):
        raise DocumentParserError(
            "unsupported_file_type",
            f"Unsupported file format '{suffix}'. Only .pdf, .md, and .txt files are supported.",
        )
    if suffix == ".pdf" and len(file_bytes) > MAX_PDF_SIZE_BYTES:
        raise DocumentParserError(
            "file_too_large",
            f"Uploaded PDF exceeds {MAX_PDF_SIZE_BYTES // (1024 * 1024)}MB limit.",
        )
    if suffix in (".md", ".txt"):
        if len(file_bytes) > MAX_TEXT_FILE_BYTES:
            raise DocumentParserError("file_too_large", "Uploaded file exceeds 2MB limit.")
        if b"\x00" in file_bytes:
            raise DocumentParserError(
                "invalid_text_file", "Binary content with null bytes is not allowed."
            )
        if not file_bytes.strip():
            raise DocumentParserError("empty_file", "Uploaded text file is empty.")

    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        temp_file.write(file_bytes)
        temp_file.flush()
        temp_file.close()
        return validate_and_parse_document(
            file_path=temp_file.name,
            filename=filename,
            ocr_runner=ocr_runner,
        )
    finally:
        Path(temp_file.name).unlink(missing_ok=True)


__all__ = [
    "CHAT_TURN_STEP_DURATIONS",
    "COMPACTION_MAX_TOKENS",
    "CONTEXT_COMPACTION_KEEP_RECENT",
    "CONTEXT_COMPACTION_MAX_SUMMARY_CHARS",
    "CONTEXT_WINDOW_MAX_CHARS",
    "CONTEXT_WINDOW_MAX_ENTRIES",
    "COSINE_SIMILARITY_THRESHOLD",
    "DEFAULT_COMPACTION_MODEL",
    "DEFAULT_STORE_CAPACITY",
    "DEFAULT_STORE_TTL_SECONDS",
    "ETA_BUFFER_S",
    "FOLLOWUP_DEFAULT_MODEL",
    "FOLLOWUP_MAX_TOKENS",
    "FREE_TOPIC_MIN_WORDS",
    "GROUP_COUNTER",
    "GROUP_EVIDENCE",
    "GROUP_MAIN",
    "READY_MESSAGE",
    "TURN1_MAX_TOKENS",
    "ChatSessionState",
    "ChatSessionStore",
    "ContextEntry",
    "FollowupDecision",
    "TurnStepTracker",
    "analyze_slot_coverage",
    "append_to_context_window",
    "build_followup_reply",
    "build_turn1_question",
    "chat_session_store",
    "check_ready_to_generate",
    "classify_argument_slot",
    "compact_context_entries",
    "deterministic_compact_summary",
    "evaluate_and_build_followup",
    "format_checklist_fallback",
    "group_uncovered_slots",
    "ingest_upload_file",
    "normalize_turn_entry",
]
