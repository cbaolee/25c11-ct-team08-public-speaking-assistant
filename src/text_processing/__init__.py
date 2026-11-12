"""Text processing package for parsing PDF/text and generating scripts."""

from .contracts import (
    CATEGORY_SLUG_MAP,
    VALID_DURATIONS,
    GeneratedScript,
    ModerationDecision,
    ParagraphCitation,
    ScriptGenerationError,
    ScriptGenerationRequest,
    ScriptJobState,
    TemplateDocument,
    TemplateSlot,
    TopicMetadata,
)
from .generator import ScriptGenerator, ScriptResult
from .moderation import ContentModerator, wrap_untrusted_document_context
from .parser import DocumentChunk, DocumentParserError, parse_input_to_chunks, validate_pdf_file
from .pipeline import ScriptGenerationPipeline
from .retrieval import SemanticRetriever, verify_paragraph_citation
from .sanitizer import sanitize_chunks, sanitize_text
from .template_engine import (
    TemplateEngine,
    TokenBucketLimiter,
    assemble_template,
    parse_slots,
    validate_assembled_script,
)
from .template_store import TemplateStore, lint_template_file, slugify_topic

__all__ = [
    "CATEGORY_SLUG_MAP",
    "ContentModerator",
    "DocumentChunk",
    "DocumentParserError",
    "GeneratedScript",
    "ModerationDecision",
    "ParagraphCitation",
    "ScriptGenerationError",
    "ScriptGenerationPipeline",
    "ScriptGenerationRequest",
    "ScriptGenerator",
    "ScriptJobState",
    "ScriptResult",
    "SemanticRetriever",
    "TemplateDocument",
    "TemplateEngine",
    "TemplateSlot",
    "TemplateStore",
    "TokenBucketLimiter",
    "TopicMetadata",
    "VALID_DURATIONS",
    "assemble_template",
    "lint_template_file",
    "parse_input_to_chunks",
    "parse_slots",
    "sanitize_chunks",
    "sanitize_text",
    "slugify_topic",
    "validate_assembled_script",
    "validate_pdf_file",
    "verify_paragraph_citation",
    "wrap_untrusted_document_context",
]
