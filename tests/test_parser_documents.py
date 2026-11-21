"""Unit tests for unified .pdf, .md, and .txt validation and chunk parsing."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.app import constants
from src.text_processing.parser import (
    MAX_TEXT_FILE_BYTES,
    MAX_TEXT_FILE_WORDS,
    DocumentChunk,
    DocumentParserError,
    validate_and_parse_document,
    validate_text_file,
)


def test_text_file_constants_match_app_constants_toml() -> None:
    script_cfg = constants.load_constants()["script"]
    assert MAX_TEXT_FILE_BYTES == script_cfg["max_text_file_bytes"]
    assert MAX_TEXT_FILE_WORDS == script_cfg["max_text_file_words"]


def test_parse_markdown_with_multiple_headings(tmp_path: Path) -> None:
    md_file = tmp_path / "notes.md"
    md_file.write_text(
        "# Introduction\nPublic speaking builds confidence.\n\n"
        "## Evidence\nStudies show deliberate practice improves fluency.\n",
        encoding="utf-8",
    )
    chunks = validate_and_parse_document(str(md_file), "notes.md")
    assert len(chunks) == 2
    assert (chunks[0].heading, chunks[0].page) == ("Introduction", 1)
    assert "builds confidence" in chunks[0].content
    assert (chunks[1].heading, chunks[1].page) == ("Evidence", 1)
    assert "deliberate practice" in chunks[1].content


def test_parse_markdown_heading_only_falls_back_to_single_chunk(tmp_path: Path) -> None:
    md_file = tmp_path / "outline.md"
    md_file.write_text("# Climate Action Roadmap\n", encoding="utf-8")
    chunks = validate_and_parse_document(str(md_file), "outline.md")
    assert len(chunks) == 1
    assert chunks[0].heading == "outline"
    assert "Climate Action Roadmap" in chunks[0].content


def test_parse_plain_text_utf8_bom(tmp_path: Path) -> None:
    txt_file = tmp_path / "speech_notes.txt"
    txt_file.write_text(
        "\ufeffKỹ năng thuyết trình giúp truyền đạt ý tưởng rõ ràng hơn.\n",
        encoding="utf-8",
    )
    chunks = validate_and_parse_document(str(txt_file), "speech_notes.txt")
    assert len(chunks) == 1
    assert "thuyết trình" in chunks[0].content


def test_parse_pdf_delegates_to_pdf_pipeline(tmp_path: Path) -> None:
    pdf_file = tmp_path / "slides.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\n" + b"0" * 1200)
    expected = [DocumentChunk(1, "Slide 1", 1, "Key metrics from Q4.")]
    with (
        patch("src.text_processing.parser.validate_pdf_file", return_value=1) as mock_val,
        patch("src.text_processing.parser.parse_input_to_chunks", return_value=expected) as mock_p,
    ):
        chunks = validate_and_parse_document(str(pdf_file), "slides.pdf")
    mock_val.assert_called_once_with(str(pdf_file))
    mock_p.assert_called_once_with(pdf_path=str(pdf_file), ocr_runner=None)
    assert chunks == expected


@pytest.mark.parametrize("filename", ["report.docx", "malware.exe", "README"])
def test_rejects_unsupported_extension(tmp_path: Path, filename: str) -> None:
    f = tmp_path / filename
    f.write_text("hello world", encoding="utf-8")
    with pytest.raises(DocumentParserError) as exc_info:
        validate_and_parse_document(str(f), filename)
    assert exc_info.value.error_code == "unsupported_file_type"


def test_rejects_binary_file_renamed_as_txt(tmp_path: Path) -> None:
    fake_txt = tmp_path / "fake.txt"
    fake_txt.write_bytes(b"ELF\x00\x01\x02binary payload")
    with pytest.raises(DocumentParserError) as exc_info:
        validate_and_parse_document(str(fake_txt), "fake.txt")
    assert exc_info.value.error_code == "invalid_text_file"


def test_rejects_invalid_utf8_encoding(tmp_path: Path) -> None:
    bad_utf8 = tmp_path / "latin.txt"
    bad_utf8.write_bytes(b"\xff\xfe\xfd invalid utf8")
    with pytest.raises(DocumentParserError) as exc_info:
        validate_and_parse_document(str(bad_utf8), "latin.txt")
    assert exc_info.value.error_code == "invalid_text_encoding"


def test_rejects_empty_and_whitespace_only_files(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.txt"
    empty_file.write_bytes(b"")
    with pytest.raises(DocumentParserError) as exc_empty:
        validate_text_file(str(empty_file))
    assert exc_empty.value.error_code == "file_too_small"

    ws_file = tmp_path / "spaces.md"
    ws_file.write_text("   \n\t  \n", encoding="utf-8")
    with pytest.raises(DocumentParserError) as exc_ws:
        validate_text_file(str(ws_file))
    assert exc_ws.value.error_code == "empty_document"


def test_rejects_file_exceeding_byte_or_word_limit(tmp_path: Path) -> None:
    big_bytes = tmp_path / "big.txt"
    big_bytes.write_text("a" * 200, encoding="utf-8")
    with pytest.raises(DocumentParserError) as exc_bytes:
        validate_text_file(str(big_bytes), max_bytes=100)
    assert exc_bytes.value.error_code == "file_too_large"

    many_words = tmp_path / "long.md"
    many_words.write_text(" ".join(["word"] * 25), encoding="utf-8")
    with pytest.raises(DocumentParserError) as exc_words:
        validate_text_file(str(many_words), max_words=20)
    assert exc_words.value.error_code == "text_too_long"
