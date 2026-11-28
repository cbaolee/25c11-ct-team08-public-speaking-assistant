"""Stage 3 regex text sanitizer for PDF and raw text chunks."""

import re
import unicodedata

from .parser import DocumentChunk

ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
CID_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)
DEHYPHEN_RE = re.compile(r"([a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,})")
SPACE_RE = re.compile(r"[ \t]+")
COMPOUNDS = {"state-of-the-art", "real-time", "end-to-end", "open-source", "multi-tier"}


def _join_hyphen(m: re.Match[str]) -> str:
    pair = f"{m.group(1)}-{m.group(2)}"
    return pair if pair.lower() in COMPOUNDS else f"{m.group(1)}{m.group(2)}"


def sanitize_text(raw_text: str) -> str:
    """Remove control chars, CID artifacts, and rejoin line-break hyphenated words."""
    if not raw_text:
        return ""
    t = unicodedata.normalize(
        "NFC",
        ZERO_WIDTH_RE.sub("", raw_text).replace("\xa0", " ").replace("\r\n", "\n"),
    )
    t = DEHYPHEN_RE.sub(_join_hyphen, CID_RE.sub("", t).replace("\ufffd", ""))
    return SPACE_RE.sub(" ", t).strip()


def sanitize_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    """Sanitize all chunks, preserving provenance metadata and dropping empty ones."""
    result: list[DocumentChunk] = []
    for c in chunks:
        cleaned_content = sanitize_text(c.content)
        if not cleaned_content:
            continue
        result.append(
            DocumentChunk(
                chunk_id=c.chunk_id,
                heading=sanitize_text(c.heading),
                page=c.page,
                content=cleaned_content,
                source_kind=getattr(c, "source_kind", "file"),
                source_msg_id=getattr(c, "source_msg_id", None),
                source_file=getattr(c, "source_file", None),
            )
        )
    return result
