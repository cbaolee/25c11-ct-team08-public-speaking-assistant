"""Text processing package for parsing PDF/text and generating scripts."""

from .generator import ScriptGenerator, ScriptResult
from .parser import DocumentChunk, DocumentParserError, parse_input_to_chunks, validate_pdf_file
from .sanitizer import sanitize_chunks, sanitize_text

__all__ = [
    "DocumentChunk",
    "DocumentParserError",
    "ScriptGenerator",
    "ScriptResult",
    "parse_input_to_chunks",
    "sanitize_chunks",
    "sanitize_text",
    "validate_pdf_file",
]
