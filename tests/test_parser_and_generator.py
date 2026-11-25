"""Unit tests for PR 1: parse from text and digital PDF (PB-08)."""

import json
from unittest.mock import MagicMock

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from src.app.config import settings
from src.text_processing import (
    DocumentParserError,
    ScriptGenerator,
    parse_input_to_chunks,
    sanitize_chunks,
    validate_pdf_file,
)


def _make_pdf(path: str) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawString(50, 780, "# 1. Intro to Speech Coaching")
    c.drawString(50, 750, "Clear pronun-")
    c.drawString(50, 730, "ciation and steady pacing.")
    for i in range(12):
        c.drawString(50, 700 - i * 20, f"Padding line {i} to exceed 1024 bytes threshold.")
    c.showPage()
    c.save()


def test_parse_and_sanitize_valid_pdf_and_raw_text(tmp_path) -> None:
    """Verify Digital PDF and Raw Text parsing, hyphen joining, and page tracking."""
    pdf_path = str(tmp_path / "valid.pdf")
    _make_pdf(pdf_path)
    assert validate_pdf_file(pdf_path) == 1
    chunks = sanitize_chunks(parse_input_to_chunks(pdf_path=pdf_path))
    assert chunks[0].page == 1 and "pronunciation" in chunks[0].content
    raw_chunks = sanitize_chunks(parse_input_to_chunks(raw_text="# Topic\nHello\u200b world"))
    assert raw_chunks[0].heading == "Topic" and "\u200b" not in raw_chunks[0].content


def test_validate_pdf_file_rejects_fake_pdf(tmp_path) -> None:
    """Reject a non-PDF file renamed to .pdf at Stage 1."""
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"NOT_A_PDF_HEADER_" * 80)
    try:
        validate_pdf_file(str(fake))
        raise AssertionError()
    except DocumentParserError as exc:
        assert exc.error_code == "invalid_pdf_signature"


def test_script_generator_fallback_and_citation_check(monkeypatch) -> None:
    """Verify Groq fallback model chain and citation page verification."""
    monkeypatch.setattr(settings, "groq_api_keys", ["dummy_key"])
    gen = ScriptGenerator()
    mock_client, ok_resp = MagicMock(), MagicMock()
    ok_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {"script": "Speech.", "citations": [{"heading": "Intro", "page": 99}]}
                )
            )
        )
    ]
    mock_client.chat.completions.create.side_effect = [RuntimeError("429"), ok_resp]
    gen.client = mock_client
    res = gen.generate_script(parse_input_to_chunks(raw_text="# Intro\nPage 1."), topic="AI")
    assert res.model_used == gen.model_chain[1] and res.citations == [
        {"heading": "Intro", "page": 1}
    ]


def test_verify_citations_rejects_whitespace_headings_and_bool_pages(monkeypatch) -> None:
    """Whitespace headings must be dropped and bool pages must never leak as page numbers."""
    from src.text_processing.contracts import DocumentChunk

    monkeypatch.setattr(settings, "groq_api_keys", ["dummy_key"])
    gen = ScriptGenerator()
    chunks = [
        DocumentChunk(chunk_id=1, heading="Intro", page=1, content="Opening."),
        DocumentChunk(chunk_id=2, heading="Methods", page=2, content="Details."),
    ]
    verified = gen.verify_citations(
        [
            {"heading": "   ", "page": 1},
            {"heading": None, "page": 2},
            {"heading": "Intro", "page": True},
            {"heading": "Unknown", "page": True},
            {"heading": "Methods", "page": 2},
        ],
        chunks,
    )
    assert verified == [
        {"heading": "Intro", "page": 1},
        {"heading": "Methods", "page": 2},
    ]
    assert all(type(item["page"]) is int for item in verified)
