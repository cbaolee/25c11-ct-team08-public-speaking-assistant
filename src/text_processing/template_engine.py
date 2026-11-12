"""WP-B3 (Member 2): Token-Budget Rate Limiter and Template Slot Engine.

Responsibilities (Brief §5.4, §5.5):
- Parse `{{ argument_... }}` and entity slots from a `TemplateDocument`
- Batch slots within Groq's 8K TPM per-model token budget
- Fill slots via LLM using retrieved top-k chunks and anti-injection delimiters
- Assemble filled values using pure regex string replacement (NEVER Jinja2)
- Normalize punctuation at slot boundaries and post-validate word count
"""

import re

from .contracts import (
    TARGET_WORD_COUNT_RANGES,
    DocumentChunk,
    GeneratedScript,
    ParagraphCitation,
    TemplateDocument,
    TemplateSlot,
)
from .retrieval import SemanticRetriever

SLOT_PATTERN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


class TokenBucketLimiter:
    """Per-model token and request rate limiter for Groq model fallback chains (Brief §5.5).

    TODO (Member 2 - WP-B3):
    Implement RPM (30 RPM) and TPM (8,000 TPM) token-bucket tracking per model ID.
    """

    def __init__(self, rpm_limit: int = 30, tpm_limit: int = 8000) -> None:
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit

    def can_consume(self, model_id: str, estimated_tokens: int) -> bool:
        """Return True if `model_id` has enough budget for `estimated_tokens`."""
        return estimated_tokens <= self.tpm_limit


def parse_slots(template: TemplateDocument, context_window_chars: int = 160) -> list[TemplateSlot]:
    """Extract all `{{ slot_name }}` placeholders with surrounding lead-in and follow text."""
    slots: list[TemplateSlot] = []
    body = template.body
    for match in SLOT_PATTERN.finditer(body):
        name = match.group(1)
        start, end = match.span()
        lead_start = max(0, start - context_window_chars)
        follow_end = min(len(body), end + context_window_chars)
        slot_type = "argument" if name.startswith("argument_") else "entity"
        slots.append(
            TemplateSlot(
                name=name,
                slot_type=slot_type,
                start_char=start,
                end_char=end,
                lead_in=body[lead_start:start].strip(),
                follow_text=body[end:follow_end].strip(),
            )
        )
    return slots


def assemble_template(template_body: str, slot_values: dict[str, str]) -> str:
    """Pure regex string replacement for slots without Jinja2 evaluation (Brief §5.4).

    Normalizes duplicate terminal periods (`..` -> `.`) when a filled argument ends with a period
    and the template immediately follows the slot with a period.
    """

    def _replace(match: re.Match[str]) -> str:
        slot_name = match.group(1)
        if slot_name not in slot_values:
            return match.group(0)
        val = slot_values[slot_name].strip()
        after_pos = match.end()
        if after_pos < len(template_body) and template_body[after_pos] == "." and val.endswith("."):
            val = val[:-1].rstrip()
        return val

    return SLOT_PATTERN.sub(_replace, template_body)


def validate_assembled_script(text: str, duration_min: int) -> list[str]:
    """Post-check assembled script for leftover `{{ }}` and word count (Brief §5.2 Stage 7)."""
    issues: list[str] = []
    if "{{" in text or "}}" in text:
        issues.append("unresolved_slots")
    word_count = len(text.split())
    min_words, max_words = TARGET_WORD_COUNT_RANGES.get(duration_min, (100, 3500))
    if not (min_words <= word_count <= max_words):
        issues.append(f"word_count_out_of_range:{word_count}")
    return issues


class TemplateEngine:
    """Orchestrates slot extraction, retrieval, batched LLM filling, and assembly (Brief §5.4)."""

    def __init__(
        self,
        retriever: SemanticRetriever | None = None,
        limiter: TokenBucketLimiter | None = None,
    ) -> None:
        self.retriever = retriever or SemanticRetriever()
        self.limiter = limiter or TokenBucketLimiter()

    def fill_template(
        self,
        template: TemplateDocument,
        chunks: list[DocumentChunk] | None = None,
    ) -> GeneratedScript:
        """Fill all slots in `template` using retrieved chunks and LLM batches.

        TODO (Member 2 - WP-B3):
        1. Group `parse_slots(template)` into token-budget batches.
        2. Retrieve top-k chunks per slot via `self.retriever`.
        3. Call Groq model chain to get JSON `{slot_name: {text, source_chunk_ids}}`.
        4. Verify citations and assemble final text via `assemble_template()`.
        """
        slots = parse_slots(template)
        dummy_values = {s.name: f"[Filled content for {s.name}]" for s in slots}
        assembled = assemble_template(template.body, dummy_values)
        citations = [
            ParagraphCitation(paragraph=i + 1, heading=None, page=None, status="uncited")
            for i, _ in enumerate(assembled.split("\n\n"))
            if _.strip()
        ]
        flags = ["uncited"] if not chunks else []
        return GeneratedScript(
            script=assembled,
            word_count=len(assembled.split()),
            duration_min=template.metadata.duration_min,
            source="template",
            template_id=template.metadata.template_id,
            models_used=[],
            citations=citations,
            flags=flags,
        )

