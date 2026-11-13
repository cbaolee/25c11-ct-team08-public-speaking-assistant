"""WP-B3 (Member 2): Token-Budget Rate Limiter and Template Slot Engine.

Responsibilities (Brief §5.4, §5.5):
- Parse ``{{ argument_... }}`` and entity slots from a ``TemplateDocument``
- Assemble filled values using pure regex string replacement (NEVER Jinja2)
- Normalize punctuation at slot boundaries and post-validate word count
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .contracts import (
    TARGET_WORD_COUNT_RANGES,
    DocumentChunk,
    GeneratedScript,
    TemplateDocument,
    TemplateSlot,
)
from .limiter import TokenBucketLimiter
from .retrieval import SemanticRetriever

logger = logging.getLogger(__name__)

SLOT_PATTERN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


# ---------------------------------------------------------------------------
# Slot parsing
# ---------------------------------------------------------------------------


def parse_slots(
    template: TemplateDocument,
    context_window_chars: int = 200,
) -> list[TemplateSlot]:
    """Extract all ``{{ slot_name }}`` placeholders with surrounding context."""
    slots: list[TemplateSlot] = []
    body = template.body
    matches = list(SLOT_PATTERN.finditer(body))
    for i, match in enumerate(matches):
        name = match.group(1)
        start, end = match.span()

        lead_start = body.rfind("\n\n", 0, start)
        lead_start = 0 if lead_start == -1 else lead_start + 2
        if i > 0 and matches[i - 1].end() > lead_start:
            lead_start = matches[i - 1].end()
        lead_start = max(lead_start, start - context_window_chars)
        lead_in = body[lead_start:start].strip()

        follow_end = body.find("\n\n", end)
        follow_end = len(body) if follow_end == -1 else follow_end
        if i + 1 < len(matches) and matches[i + 1].start() < follow_end:
            follow_end = matches[i + 1].start()
        follow_end = min(follow_end, end + context_window_chars)
        follow_text = body[end:follow_end].strip()

        slot_type = "argument" if name.startswith("argument_") else "entity"
        slots.append(
            TemplateSlot(
                name=name,
                slot_type=slot_type,
                start_char=start,
                end_char=end,
                lead_in=lead_in,
                follow_text=follow_text,
            )
        )
    return slots


# ---------------------------------------------------------------------------
# Assembly (pure regex, NEVER Jinja2)
# ---------------------------------------------------------------------------


def assemble_template(template_body: str, slot_values: dict[str, str]) -> str:
    """Replace ``{{ slot_name }}`` placeholders with filled values.

    Normalises duplicate terminal periods (``..`` → ``.``) and ensures
    anti-SSTI by avoiding Jinja2 rendering.
    """

    def _replace(match: re.Match[str]) -> str:
        slot_name = match.group(1)
        if slot_name not in slot_values:
            return match.group(0)
        val = slot_values[slot_name].strip()
        after_pos = match.end()
        has_trailing_punct = after_pos < len(template_body) and template_body[after_pos] in ".!?,;:"
        if has_trailing_punct:
            while val and val[-1] in ".!?,;:":
                val = val[:-1].rstrip()
        else:
            if val and val[-1] not in ".!?":
                val += "."
        return val

    return SLOT_PATTERN.sub(_replace, template_body)


# ---------------------------------------------------------------------------
# Post-validation
# ---------------------------------------------------------------------------


def validate_assembled_script(text: str, duration_min: int) -> list[str]:
    """Post-check assembled script for leftover ``{{ }}`` and word count."""
    issues: list[str] = []
    if "{{" in text or "}}" in text:
        issues.append("unresolved_slots")
    word_count = len(text.split())
    min_words, max_words = TARGET_WORD_COUNT_RANGES.get(duration_min, (100, 3500))
    if not (min_words <= word_count <= max_words):
        issues.append(f"word_count_out_of_range:{word_count}")
    return issues


# ---------------------------------------------------------------------------
# TemplateEngine Skeleton (completed in next PR)
# ---------------------------------------------------------------------------


class TemplateEngine:
    """Engine for slot batching and LLM slot-filling orchestration."""

    def __init__(
        self,
        client: Any = None,
        limiter: TokenBucketLimiter | None = None,
        retriever: SemanticRetriever | None = None,
    ) -> None:
        self.client = client
        self.limiter = limiter or TokenBucketLimiter()
        self.retriever = retriever or SemanticRetriever()

    def fill_template(
        self,
        template: TemplateDocument,
        chunks: list[DocumentChunk] | None = None,
        raw_text: str | None = None,
    ) -> GeneratedScript:
        """Fill slots in template (skeleton placeholder)."""
        slots = parse_slots(template)
        slot_values = {s.name: f"Filled content for {s.name}." for s in slots}
        script_text = assemble_template(template.body, slot_values)
        return GeneratedScript(
            script=script_text,
            word_count=len(script_text.split()),
            duration_min=template.metadata.duration_min,
            source="template",
            template_id=template.metadata.template_id,
            models_used=[],
            citations=[],
            flags=[],
            warnings=[],
        )
