"""Stage 1 sanity gate and Stage 2 parser with pluggable OCR page routing."""

import os
import re
import unicodedata
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.app.config import (
    composer_max_words,
    max_pdf_pages,
    max_pdf_size_bytes,
    max_text_file_bytes,
    max_text_file_words,
    max_turn_text_chars,
    min_pdf_size_bytes,
)
from src.app.constants import CONSTANTS

try:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, module="fitz")
        import fitz
except ImportError:
    fitz = None
try:
    import pymupdf4llm
except ImportError:
    pymupdf4llm = None
try:
    import pypdf
except ImportError:
    pypdf = None
try:
    from .ocr_fallback import maybe_recover_page_text
except ImportError:
    maybe_recover_page_text = None

PDF_MAGIC_BYTES = b"%PDF-"
MIN_PDF_SIZE_BYTES = min_pdf_size_bytes
MAX_PDF_SIZE_BYTES = max_pdf_size_bytes
MAX_POC_PAGES = max_pdf_pages
MAX_TEXT_FILE_BYTES = max_text_file_bytes
MAX_TEXT_FILE_WORDS = max_text_file_words
MAX_TURN_TEXT_CHARS = max_turn_text_chars
MAX_TURN_TEXT_WORDS = composer_max_words
CHUNK_MAX_WORDS = int(CONSTANTS["script"].get("chunk_max_words", 180))
CHUNK_OVERLAP_WORDS = int(CONSTANTS["script"].get("chunk_overlap_words", 30))
ALLOWED_DOC_EXTENSIONS = frozenset({".pdf", ".md", ".txt"})
FILE_SIZE_LIMITS_BYTES: dict[str, int] = {
    ".pdf": MAX_PDF_SIZE_BYTES,
    ".md": MAX_TEXT_FILE_BYTES,
    ".txt": MAX_TEXT_FILE_BYTES,
}
HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


class DocumentParserError(Exception):
    """Raised when input fails Stage 1 validation."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code, self.message = error_code, message


@dataclass
class DocumentChunk:
    """A text chunk linked to a heading and 1-based page number."""

    chunk_id: int
    heading: str
    page: int
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_pdf_file(pdf_path: str, max_pages: int = MAX_POC_PAGES) -> int:
    """Validate PDF signature (%PDF-), size (1KB-25MB), password, and page count."""
    if not pdf_path or not os.path.exists(pdf_path):
        raise DocumentParserError("file_not_found", f"File not found: {pdf_path}")
    size_bytes = os.path.getsize(pdf_path)
    if size_bytes < MIN_PDF_SIZE_BYTES:
        raise DocumentParserError("file_too_small", f"Size ({size_bytes}B) < 1 KB.")
    if size_bytes > MAX_PDF_SIZE_BYTES:
        raise DocumentParserError("file_too_large", f"Size ({size_bytes}B) > 25 MB.")
    with open(pdf_path, "rb") as stream:
        if stream.read(5) != PDF_MAGIC_BYTES:
            raise DocumentParserError("invalid_pdf_signature", "Missing '%PDF-' header.")
    page_count = _get_pdf_page_count(pdf_path)
    if page_count <= 0:
        raise DocumentParserError("empty_pdf", "PDF has 0 pages.")
    if page_count > max_pages:
        raise DocumentParserError("too_many_pages", f"PDF exceeds {max_pages} pages.")
    return page_count


def _get_pdf_page_count(pdf_path: str) -> int:
    """Open PDF to check encryption and return total pages."""
    if fitz is not None:
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            raise DocumentParserError("corrupted_pdf", str(exc)) from exc
        is_enc, count = bool(doc.is_encrypted), (0 if doc.is_encrypted else int(doc.page_count))
        doc.close()
        if is_enc:
            raise DocumentParserError("password_protected_pdf", "PDF is encrypted.")
        return count
    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception as exc:
        raise DocumentParserError("corrupted_pdf", str(exc)) from exc
    if reader.is_encrypted:
        raise DocumentParserError("password_protected_pdf", "PDF is encrypted.")
    return len(reader.pages)


def _split_long_chunk_text(
    text: str,
    max_words: int = CHUNK_MAX_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[str]:
    """Split oversized section text into sentence-aligned sub-chunks with word overlap.

    Keeps each chunk within ``all-MiniLM-L6-v2`` (256 wordpieces) and NLI (512 tokens)
    limits so facts in the second half of a long PDF page are never truncated away.
    """
    stripped = text.strip()
    if not stripped:
        return []
    words = stripped.split()
    if max_words <= 0 or len(words) <= max_words:
        return [stripped]

    eff_overlap = max(0, min(overlap_words, max_words // 2))
    # Split into sentence-like units while respecting line breaks
    units: list[str] = []
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for sent in _SENTENCE_BOUNDARY_RE.split(line):
            sent = sent.strip()
            if not sent:
                continue
            sent_words = sent.split()
            if len(sent_words) <= max_words:
                units.append(sent)
            else:
                # Hard-wrap unpunctuated OCR/table blocks by word window
                step = max(1, max_words - eff_overlap)
                for start in range(0, len(sent_words), step):
                    piece = " ".join(sent_words[start : start + max_words])
                    if piece:
                        units.append(piece)
                    if start + max_words >= len(sent_words):
                        break

    if not units:
        return [stripped]

    sub_chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for unit in units:
        u_words = len(unit.split())
        if current and current_words + u_words > max_words:
            sub_chunks.append(" ".join(current))
            # Seed next window with trailing overlap sentences
            overlap_buf: list[str] = []
            overlap_count = 0
            for prev_unit in reversed(current):
                pw = len(prev_unit.split())
                if overlap_count + pw > eff_overlap and overlap_buf:
                    break
                if pw <= max(eff_overlap, max_words // 2):
                    overlap_buf.append(prev_unit)
                    overlap_count += pw
                if overlap_count >= eff_overlap:
                    break
            current = list(reversed(overlap_buf))
            current_words = sum(len(x.split()) for x in current)
            if current_words + u_words > max_words:
                current = []
                current_words = 0

        current.append(unit)
        current_words += u_words

    if current:
        last_chunk = " ".join(current)
        if not sub_chunks or last_chunk != sub_chunks[-1]:
            sub_chunks.append(last_chunk)

    return sub_chunks


def parse_input_to_chunks(
    pdf_path: str | None = None,
    raw_text: str | None = None,
    ocr_runner: Callable[[bytes, int], str] | None = None,
    *,
    max_chunk_words: int = CHUNK_MAX_WORDS,
    chunk_overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[DocumentChunk]:
    """Parse Digital/Hybrid PDF or pasted raw text into size-bounded heading chunks."""
    if raw_text and not pdf_path:
        pages = [{"page": 1, "text": raw_text}]
    elif pdf_path:
        pages = _extract_pdf_pages(pdf_path, ocr_runner=ocr_runner)
    else:
        raise DocumentParserError("missing_input", "Provide pdf_path or raw_text.")
    chunks: list[DocumentChunk] = []

    def _emit_buffer(buf_lines: list[str], sec_heading: str, sec_page: int) -> None:
        raw_block = "\n".join(buf_lines)
        for part in _split_long_chunk_text(
            raw_block, max_words=max_chunk_words, overlap_words=chunk_overlap_words
        ):
            chunks.append(DocumentChunk(len(chunks) + 1, sec_heading, sec_page, part))

    for item in pages:
        page_num, heading, buf = item["page"], f"Page {item['page']} Overview", []
        for line in item["text"].splitlines():
            s, m = line.strip(), HEADING_PATTERN.match(line.strip())
            if m:
                if buf:
                    _emit_buffer(buf, heading, page_num)
                    buf = []
                heading = re.sub(r"[*_`#]+", "", m.group(2)).strip()
            elif s:
                buf.append(s)
        if buf:
            _emit_buffer(buf, heading, page_num)
    return chunks


def _extract_pdf_pages(
    pdf_path: str, ocr_runner: Callable[[bytes, int], str] | None = None
) -> list[dict[str, Any]]:
    """Extract Markdown per page (Branch A) and auto-route broken pages to PR 2 OCR (Branch B)."""
    if pymupdf4llm is not None:
        raw = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
        pages = [
            {"page": int(p.get("metadata", {}).get("page", i + 1)), "text": p.get("text", "")}
            for i, p in enumerate(raw)
        ]
    else:
        reader = pypdf.PdfReader(pdf_path)
        pages = [
            {"page": i + 1, "text": p.extract_text() or ""} for i, p in enumerate(reader.pages)
        ]
    if maybe_recover_page_text is not None:
        for item in pages:
            item["text"] = maybe_recover_page_text(pdf_path, item["page"], item["text"], ocr_runner)
    if not any(ch.isalnum() for item in pages for ch in (item["text"] or "")):
        raise DocumentParserError("no_text_layer", "PDF has no extractable text (scanned?).")
    return pages


def validate_text_file(
    file_path: str,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
    max_words: int = MAX_TEXT_FILE_WORDS,
) -> str:
    """Validate an uploaded .md/.txt file (size, non-binary, UTF-8, word cap) and return text."""
    if not file_path or not os.path.exists(file_path):
        raise DocumentParserError("file_not_found", f"File not found: {file_path}")
    size_bytes = os.path.getsize(file_path)
    if size_bytes <= 0:
        raise DocumentParserError("file_too_small", "Text file is empty.")
    if size_bytes > max_bytes:
        raise DocumentParserError(
            "file_too_large", f"Size ({size_bytes}B) exceeds {max_bytes} bytes."
        )
    raw_bytes = Path(file_path).read_bytes()
    if b"\x00" in raw_bytes:
        raise DocumentParserError("invalid_text_file", "Binary content is not allowed.")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentParserError(
            "invalid_text_encoding", "Text file must be valid UTF-8."
        ) from exc
    if not any(ch.isalnum() for ch in text):
        raise DocumentParserError("empty_document", "Document contains no extractable text.")
    word_count = len(text.split())
    if word_count > max_words:
        raise DocumentParserError(
            "text_too_long", f"Document has {word_count} words (limit: {max_words})."
        )
    return text


def validate_and_parse_document(
    file_path: str,
    filename: str,
    ocr_runner: Callable[[bytes, int], str] | None = None,
) -> list[DocumentChunk]:
    """Validate and parse an uploaded .pdf, .md, or .txt document into heading chunks."""
    ext = Path(filename or file_path).suffix.lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise DocumentParserError(
            "unsupported_file_type",
            f"Unsupported file type '{ext}'. Allowed: .pdf, .md, .txt.",
        )
    if ext == ".pdf":
        validate_pdf_file(file_path)
        return parse_input_to_chunks(pdf_path=file_path, ocr_runner=ocr_runner)
    text = validate_text_file(file_path)
    chunks = parse_input_to_chunks(raw_text=text)
    fallback_heading = Path(filename or file_path).stem or "Document"
    if not chunks:
        chunks = [DocumentChunk(1, fallback_heading, 1, text.strip())]
    else:
        for chunk in chunks:
            if chunk.heading == f"Page {chunk.page} Overview":
                chunk.heading = fallback_heading
    return chunks


def max_bytes_for_extension(filename: str) -> int:
    """Return the per-type byte ceiling for `.pdf`, `.md`, or `.txt` uploads."""
    ext = Path(filename or "").suffix.lower()
    if ext not in FILE_SIZE_LIMITS_BYTES:
        raise DocumentParserError(
            "unsupported_file_type",
            f"Unsupported file format '{ext}'. Only .pdf, .md, and .txt files are supported.",
        )
    return FILE_SIZE_LIMITS_BYTES[ext]


def validate_turn_text_length(
    text: str,
    *,
    max_chars: int = MAX_TURN_TEXT_CHARS,
    max_words: int = MAX_TURN_TEXT_WORDS,
) -> None:
    """Enforce per-turn NFC character and word limits before moderation or LLM calls."""
    if not text:
        return
    normalized = unicodedata.normalize("NFC", text)
    char_count = len(normalized)
    if char_count > max_chars:
        raise DocumentParserError(
            "text_too_long",
            f"Message is too long ({char_count} characters; maximum {max_chars}).",
        )
    word_count = len(normalized.split())
    if word_count > max_words:
        raise DocumentParserError(
            "text_too_long",
            f"Message has too many words ({word_count} words; maximum {max_words}).",
        )
