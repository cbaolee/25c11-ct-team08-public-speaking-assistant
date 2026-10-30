"""Stage 1 sanity gate and Stage 2 parser with pluggable OCR page routing."""

import os
import re
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

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
MIN_PDF_SIZE_BYTES, MAX_PDF_SIZE_BYTES, MAX_POC_PAGES = 1024, 25 * 1024 * 1024, 10
HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$")


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


def parse_input_to_chunks(
    pdf_path: str | None = None,
    raw_text: str | None = None,
    ocr_runner: Callable[[bytes, int], str] | None = None,
) -> list[DocumentChunk]:
    """Parse Digital/Hybrid PDF or pasted raw text into heading chunks."""
    if raw_text and not pdf_path:
        pages = [{"page": 1, "text": raw_text}]
    elif pdf_path:
        pages = _extract_pdf_pages(pdf_path, ocr_runner=ocr_runner)
    else:
        raise DocumentParserError("missing_input", "Provide pdf_path or raw_text.")
    chunks: list[DocumentChunk] = []
    for item in pages:
        page_num, heading, buf = item["page"], f"Page {item['page']} Overview", []
        for line in item["text"].splitlines():
            s, m = line.strip(), HEADING_PATTERN.match(line.strip())
            if m:
                if buf:
                    chunks.append(DocumentChunk(len(chunks) + 1, heading, page_num, "\n".join(buf)))
                    buf = []
                heading = re.sub(r"[*_`#]+", "", m.group(2)).strip()
            elif s:
                buf.append(s)
        if buf:
            chunks.append(DocumentChunk(len(chunks) + 1, heading, page_num, "\n".join(buf)))
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
            {"page": i + 1, "text": p.extract_text() or ""}
            for i, p in enumerate(reader.pages)
        ]
    if maybe_recover_page_text is not None:
        for item in pages:
            item["text"] = maybe_recover_page_text(pdf_path, item["page"], item["text"], ocr_runner)
    return pages
