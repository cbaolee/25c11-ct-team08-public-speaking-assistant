"""Shared data contracts, exceptions, and constants for the Script Generation module.

This module acts as the stable interface between:
- Member 1 (WP-B0, WP-B1): TemplateStore, Linter, and Content Moderation
- Member 2 (WP-B2, WP-B3): Semantic Retrieval, Citation Verifier, and Template Engine
- Member 3 (WP-B4, WP-B5, WP-B6): Multi-section LLM Generator, Pipeline, and FastAPI routes
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .parser import DocumentChunk

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
class ParagraphCitation:
    """Verified citation attached to a script paragraph or filled slot (Brief §5.6)."""

    paragraph: int
    heading: str | None
    page: int | None
    status: CitationStatus
    chunk_id: int | None = None

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "result": self.result.to_dict() if self.result else None,
            "error_code": self.error_code,
            "message": self.error_message,
        }


__all__ = [
    "CATEGORY_SLUG_MAP",
    "CitationStatus",
    "DocumentChunk",
    "DurationMinutes",
    "GeneratedScript",
    "JobStatus",
    "ModerationDecision",
    "ParagraphCitation",
    "ScriptGenerationError",
    "ScriptGenerationRequest",
    "ScriptJobState",
    "ScriptSource",
    "TARGET_WORD_COUNT_RANGES",
    "TemplateDocument",
    "TemplateSlot",
    "TopicMetadata",
    "VALID_DURATIONS",
]

