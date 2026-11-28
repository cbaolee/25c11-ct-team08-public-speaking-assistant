"""Shared data contracts, exceptions, and constants for the Script Generation module.

This module acts as the stable interface between:
- Member 1 (WP-B0, WP-B1): TemplateStore, Linter, and Content Moderation
- Member 2 (WP-B2, WP-B3): Semantic Retrieval, Citation Verifier, and Template Engine
- Member 3 (WP-B4, WP-B5, WP-B6): Multi-section LLM Generator, Pipeline, and FastAPI routes
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.app.config import (
    eta_buffer_s,
    generate_stage_base_s,
    generate_stage_durations,
    generate_stage_per_min_s,
)

from .parser import DocumentChunk

ETA_BUFFER_S: int = int(eta_buffer_s)
GENERATE_STAGE_BASE_S: float = float(generate_stage_base_s)
GENERATE_STAGE_PER_MIN_S: float = float(generate_stage_per_min_s)

SCRIPT_JOB_STAGES: tuple[tuple[str, int, float], ...] = (
    ("validating_input", 10, generate_stage_durations["validating_input"]),
    ("extracting", 15, generate_stage_durations["extracting"]),
    ("moderating", 15, generate_stage_durations["moderating"]),
    ("generating", 50, generate_stage_durations["generating"]),
    ("validating_output", 10, generate_stage_durations["validating_output"]),
)


def script_stage_durations(duration_min: int = 5) -> dict[str, float]:
    """Return base stage durations (seconds) scaled modestly by target duration."""
    dur = max(5, int(duration_min or 5))
    return {
        key: (
            round(GENERATE_STAGE_BASE_S + GENERATE_STAGE_PER_MIN_S * dur, 1)
            if key == "generating"
            else base_s
        )
        for key, _, base_s in SCRIPT_JOB_STAGES
    }


def default_script_job_steps() -> list[dict[str, str]]:
    """Initial ordered step list for `ScriptJobState`."""
    return [{"key": key, "state": "pending"} for key, _, _ in SCRIPT_JOB_STAGES]


def compute_script_job_total_s(
    duration_min: int = 5,
    eta_buffer_s: int = ETA_BUFFER_S,
) -> float:
    """Base sum of stage durations plus the ~10-second telemetry buffer."""
    durations = script_stage_durations(duration_min)
    return round(sum(durations.values()) + eta_buffer_s, 1)


def compute_script_job_remaining_s(
    steps: list[dict[str, str]],
    duration_min: int = 5,
    eta_buffer_s: int = ETA_BUFFER_S,
) -> float:
    """Remaining estimated seconds (including buffer) while active; 0.0 when finished."""
    if not steps or all(s.get("state") in ("done", "skipped") for s in steps):
        return 0.0
    durations = script_stage_durations(duration_min)
    rem = sum(
        durations.get(s.get("key", ""), 0.0)
        for s in steps
        if s.get("state") in ("pending", "running")
    )
    return round(rem + eta_buffer_s, 1)

DurationMinutes = Literal[5, 10, 15, 20]
ScriptSource = Literal["template", "llm"]
CitationStatus = Literal["cited", "uncited"]
JobStatus = Literal["queued", "extracting", "moderating", "generating", "completed", "failed"]

VALID_DURATIONS: tuple[int, ...] = (5, 10, 15, 20)

CATEGORY_SLUG_MAP: dict[str, str] = {
    "cinematography": "Cinematography",
    "gender_studies": "Gender Studies",
    "information_technology": "Information Technology",
    "learning_experiences": "Learning Experiences",
    "sports": "Sports",
    "wildlife": "Wildlife",
}

# Target total word count ranges by duration (130-150 WPM speaking pace, Brief §5.3)
TARGET_WORD_COUNT_RANGES: dict[int, tuple[int, int]] = {
    5: (580, 820),
    10: (1160, 1640),
    15: (1750, 2450),
    20: (2340, 3260),
}


class ScriptGenerationError(Exception):
    """Base exception for Script Generation pipeline errors mapped to HTTP responses.

    Standard error_code values (Brief §5.7):
    - 'invalid_pdf': Failed PDF sanity check (signature, size, password, page limit)
    - 'no_text_layer': Scanned PDF with no extractable text layer
    - 'content_rejected': Input failed Stage 4 content moderation (HTTP 422)
    - 'rate_limited': Exceeded user or model rate limit (HTTP 429)
    - 'generation_unavailable': All LLM fallback models failed/exhausted (HTTP 503)
    - 'output_invalid': Generated script failed post-validation after retries (HTTP 422)
    """

    def __init__(self, error_code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.error_code, "message": self.message}


@dataclass(frozen=True)
class TopicMetadata:
    """Metadata for a single template topic returned by GET /api/topics (Brief §5.4)."""

    template_id: str
    category_slug: str
    category: str
    topic: str
    topic_slug: str
    duration_min: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemplateDocument:
    """Loaded markdown template with YAML frontmatter and body text (Brief §5.3)."""

    metadata: TopicMetadata
    body: str
    file_path: str


@dataclass(frozen=True)
class TemplateSlot:
    """A parsed placeholder slot inside a template body (Brief §5.4)."""

    name: str
    slot_type: Literal["argument", "entity"]
    start_char: int
    end_char: int
    lead_in: str
    follow_text: str


@dataclass(frozen=True)
class ModerationDecision:
    """Result of Stage 4 input content moderation (Brief §5.8)."""

    allowed: bool
    reason: str | None = None
    layer: Literal["regex", "llama_guard", "cache"] = "regex"
    flagged_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SentenceCitation:
    """Verified citation attached to a single sentence inside a script paragraph."""

    sentence_index: int
    text: str
    status: CitationStatus
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParagraphCitation:
    """Verified citation attached to a script paragraph or filled slot (Brief §5.6)."""

    paragraph: int
    heading: str | None
    page: int | None
    status: CitationStatus
    chunk_id: int | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    sentences: list[SentenceCitation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GeneratedScript:
    """Final output contract of the Script Generation pipeline (Brief §5.7)."""

    script: str
    word_count: int
    duration_min: int | None
    source: ScriptSource
    template_id: str | None
    models_used: list[str] = field(default_factory=list)
    citations: list[ParagraphCitation] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "script": self.script,
            "word_count": self.word_count,
            "duration_min": self.duration_min,
            "source": self.source,
            "template_id": self.template_id,
            "models_used": list(self.models_used),
            "citations": [c.to_dict() for c in self.citations],
            "flags": list(self.flags),
            "warnings": list(self.warnings),
            "title": self.title,
        }


@dataclass
class ScriptGenerationRequest:
    """Input payload for the 8-stage script generation pipeline (Brief §5.2, §5.7)."""

    topic: str
    category: str | None = None
    duration_min: int = 5
    pdf_path: str | None = None
    raw_text: str | None = None
    greeting: str | None = None
    user_id: str = "anonymous"
    session_id: str | None = None
    user_feedback: str | None = None
    chat_context: str | None = None
    feedback_msg_id: str | None = None


@dataclass
class ScriptJobState:
    """In-memory background job state for POST/GET /api/generate-script (Brief §5.5)."""

    job_id: str
    user_id: str
    status: JobStatus = "queued"
    progress: int = 0
    result: GeneratedScript | None = None
    error_code: str | None = None
    error_message: str | None = None
    stage: str = "queued"
    steps: list[dict[str, str]] = field(default_factory=default_script_job_steps)
    eta_buffer_s: int = ETA_BUFFER_S
    duration_min: int = 5
    estimated_total_s: float = field(default_factory=lambda: compute_script_job_total_s(5))
    estimated_remaining_s: float = field(default_factory=lambda: compute_script_job_total_s(5))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "steps": [dict(s) for s in self.steps],
            "eta_buffer_s": self.eta_buffer_s,
            "estimated_total_s": self.estimated_total_s,
            "estimated_remaining_s": self.estimated_remaining_s,
            "result": self.result.to_dict() if self.result else None,
            "error_code": self.error_code,
            "message": self.error_message,
        }


__all__ = [
    "CATEGORY_SLUG_MAP",
    "CitationStatus",
    "DocumentChunk",
    "DurationMinutes",
    "ETA_BUFFER_S",
    "GENERATE_STAGE_BASE_S",
    "GENERATE_STAGE_PER_MIN_S",
    "GeneratedScript",
    "JobStatus",
    "ModerationDecision",
    "ParagraphCitation",
    "SCRIPT_JOB_STAGES",
    "ScriptGenerationError",
    "ScriptGenerationRequest",
    "ScriptJobState",
    "ScriptSource",
    "SentenceCitation",
    "TARGET_WORD_COUNT_RANGES",
    "TemplateDocument",
    "TemplateSlot",
    "TopicMetadata",
    "VALID_DURATIONS",
    "compute_script_job_remaining_s",
    "compute_script_job_total_s",
    "default_script_job_steps",
    "script_stage_durations",
]
