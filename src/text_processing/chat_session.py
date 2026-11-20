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

        # 1. Direct match in prompt or user notes
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
    gather_turns: int,
    files_loaded: list[str] | None = None,
    prompt: str = "",
    user_notes: list[str] | None = None,
) -> bool:
    """Evaluate 3-layer deterministic stop condition for generation readiness."""
    # Layer 1: Sufficient Document & Slot Coverage
    if len(missing_entities) == 0 and coverage_ratio >= 0.7:
        return True

    # Layer 2: Hard Interaction Cap
    if gather_turns >= 2:
        return True

    # Layer 3: Free-Topic Mode Fallback
    if selected_template_id is None:
        has_files = bool(files_loaded and len(files_loaded) > 0)
        all_text = f"{prompt} {' '.join(user_notes or [])}".strip()
        word_count = len(all_text.split())
        if has_files or word_count >= FREE_TOPIC_MIN_WORDS:
            return True

    return False


def format_checklist_fallback(
    topic: str,
    missing_entities: list[str],
    missing_groups: list[str],
) -> str:
    """Generate a deterministic 0-token checklist when LLM is unavailable or fails."""
    lines = [f"To help craft your speech on '{topic}', please provide a bit more detail on:"]
    if missing_entities:
        clean_entities = [e.removeprefix("entity_").replace("_", " ") for e in missing_entities]
        lines.append(f"- Specific details: {', '.join(clean_entities)}")
    if missing_groups:
        lines.append(f"- Key areas: {', '.join(missing_groups)}")
    return "\n".join(lines)


def build_followup_reply(
    topic: str,
    ready_to_generate: bool,
    missing_entities: list[str],
    missing_groups: list[str],
    gather_turns: int = 0,
    client: Any | None = None,
    model: str | None = None,
) -> str:
    """Build follow-up message using minimal tokens (or 0 tokens on ready / fallback)."""
    if ready_to_generate:
        return READY_MESSAGE

    if gather_turns >= 2:
        return READY_MESSAGE

    # If client is None, fallback immediately to 0-token checklist
    if client is None:
        return format_checklist_fallback(topic, missing_entities, missing_groups)

    target_model = (
        model
        or getattr(settings, "groq_llm_fallback_model_2", FOLLOWUP_DEFAULT_MODEL)
        or FOLLOWUP_DEFAULT_MODEL
    )

    system_prompt = (
        "You are an expert speech coach helping a speaker prepare their presentation. "
        "Ask 1-2 focused, conversational follow-up questions to gather missing speech elements. "
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
    """Ingest uploaded document into DocumentChunk items and cleanup temp files."""
    if not file_bytes:
        raise DocumentParserError("empty_file", "The uploaded file is empty.")

    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            temp_file.write(file_bytes)
            temp_file.flush()
            temp_file.close()
            chunks = parse_input_to_chunks(pdf_path=temp_file.name, ocr_runner=ocr_runner)
            return chunks
        finally:
            Path(temp_file.name).unlink(missing_ok=True)

    elif suffix in (".md", ".txt"):
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="replace")

        if not text.strip():
            raise DocumentParserError("empty_file", "Uploaded text file is empty.")

        return parse_input_to_chunks(raw_text=text)

    else:
        raise DocumentParserError(
            "unsupported_file_type",
            f"Unsupported file format '{suffix}'. Only .pdf, .md, and .txt files are supported.",
        )


__all__ = [
    "COSINE_SIMILARITY_THRESHOLD",
    "DEFAULT_STORE_CAPACITY",
    "DEFAULT_STORE_TTL_SECONDS",
    "FOLLOWUP_DEFAULT_MODEL",
    "FOLLOWUP_MAX_TOKENS",
    "FREE_TOPIC_MIN_WORDS",
    "GROUP_COUNTER",
    "GROUP_EVIDENCE",
    "GROUP_MAIN",
    "READY_MESSAGE",
    "ChatSessionState",
    "ChatSessionStore",
    "analyze_slot_coverage",
    "build_followup_reply",
    "chat_session_store",
    "check_ready_to_generate",
    "classify_argument_slot",
    "format_checklist_fallback",
    "group_uncovered_slots",
    "ingest_upload_file",
]
