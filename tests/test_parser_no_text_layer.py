"""`no_text_layer` handling for image-only (scanned) PDFs in the Stage 2 parser."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from src.text_processing import (
    DocumentParserError,
    ScriptGenerationError,
    ScriptGenerationPipeline,
    ScriptGenerationRequest,
    TemplateStore,
    parse_input_to_chunks,
)
from src.text_processing import parser as parser_mod


def _make_pdf(path: Path, pages: list[str | None]) -> str:
    """Write one page per entry: a text line, or only a drawing when the entry is None."""
    c = canvas.Canvas(str(path), pagesize=A4)
    for text in pages:
        if text is None:
            c.rect(50, 50, 300, 300, fill=1)
        else:
            c.drawString(50, 780, text)
        c.showPage()
    c.save()
    return str(path)


def test_image_only_pdf_raises_no_text_layer(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "scan.pdf", [None, None])
    with pytest.raises(DocumentParserError) as exc:
        parse_input_to_chunks(pdf_path=pdf)
    assert exc.value.error_code == "no_text_layer"


def test_pypdf_fallback_also_raises_no_text_layer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(parser_mod, "pymupdf4llm", None)
    pdf = _make_pdf(tmp_path / "scan.pdf", [None])
    with pytest.raises(DocumentParserError) as exc:
        parse_input_to_chunks(pdf_path=pdf)
    assert exc.value.error_code == "no_text_layer"


def test_ocr_hook_text_prevents_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        parser_mod, "maybe_recover_page_text", lambda path, page, text, runner: "Recovered words"
    )
    pdf = _make_pdf(tmp_path / "scan.pdf", [None])
    chunks = parse_input_to_chunks(pdf_path=pdf)
    assert "Recovered words" in chunks[0].content


def test_hybrid_pdf_with_blank_page_still_parses(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "hybrid.pdf", ["Digital page", None])
    chunks = parse_input_to_chunks(pdf_path=pdf)
    assert [c.page for c in chunks] == [1]
    assert "Digital page" in chunks[0].content


def test_raw_text_branch_is_unchanged() -> None:
    chunks = parse_input_to_chunks(raw_text="# Title\nHello")
    assert chunks[0].heading == "Title" and chunks[0].content == "Hello"


def test_ocr_hook_returning_none_still_raises_no_text_layer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(parser_mod, "maybe_recover_page_text", lambda *args: None)
    pdf = _make_pdf(tmp_path / "scan.pdf", [None])
    with pytest.raises(DocumentParserError) as exc:
        parse_input_to_chunks(pdf_path=pdf)
    assert exc.value.error_code == "no_text_layer"


def _run_pipeline(tmp_path: Path, pdf_path: str) -> ScriptGenerationError:
    pipeline = ScriptGenerationPipeline(
        template_store=TemplateStore(tmp_path / "no_templates"), llm_generator=MagicMock()
    )
    with pytest.raises(ScriptGenerationError) as exc:
        pipeline.run(ScriptGenerationRequest(topic="Any topic", pdf_path=pdf_path))
    return exc.value


def test_pipeline_maps_scanned_pdf_to_no_text_layer(tmp_path: Path) -> None:
    err = _run_pipeline(tmp_path, _make_pdf(tmp_path / "scan.pdf", [None]))
    assert (err.error_code, err.status_code) == ("no_text_layer", 422)


def test_pipeline_keeps_invalid_pdf_for_other_parser_errors(tmp_path: Path) -> None:
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"NOT_A_PDF_HEADER_" * 80)
    err = _run_pipeline(tmp_path, str(fake))
    assert (err.error_code, err.status_code) == ("invalid_pdf", 422)
