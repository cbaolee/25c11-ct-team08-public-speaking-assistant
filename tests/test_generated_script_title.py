"""Tests for the generated script title (normalisation, generator, template, contract)."""

import json
import unicodedata
from types import SimpleNamespace
from typing import Any

import pytest

from src.app.config import script_title_max_chars
from src.text_processing import template_engine
from src.text_processing.contracts import (
    GeneratedScript,
    TemplateDocument,
    TopicMetadata,
)
from src.text_processing.generator import (
    SCRIPT_TITLE_MAX_WORDS,
    ScriptGenerator,
    _section_title,
    _title_prompt_note,
    normalize_script_title,
)
from src.text_processing.template_engine import TemplateEngine, TokenBucketLimiter

FILLER = " ".join(["word"] * 350)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  The Future of Clean Energy  ", "The Future of Clean Energy"),
        ('"Quoted Title Here."', "Quoted Title Here"),
        ("“Curly Quoted Title”", "Curly Quoted Title"),
        ('"Quoted Title Here".', "Quoted Title Here"),
        ("Line\nbreak\tTitle Here", "Line break Title Here"),
        ("Clean\x00 Energy Now", "Clean Energy Now"),
        ("Clean​ Energy Now", "Clean Energy Now"),
        ("Why Does Sleep Matter?", "Why Does Sleep Matter?"),
        ("Act Now Before Midnight!", "Act Now Before Midnight!"),
        ("Title: Clean Energy Now", "Clean Energy Now"),
        ("TITLE: Clean Energy Now", "Clean Energy Now"),
        ("**Bold Title Here**", "Bold Title Here"),
        ("# Heading Style Title", "Heading Style Title"),
        ("# Heading Title Here", "Heading Title Here"),
        ("Learning C#", "Learning C#"),
        ("Rise of the U.S.", "Rise of the U.S."),
        ('"Rise of the U.S."', "Rise of the U.S."),
        ('"Rise of the U.S.".', "Rise of the U.S."),
        ("Clean Energy Now.", "Clean Energy Now"),
        ("Ellipsis Title Here...", "Ellipsis Title Here"),
        ("Title:", None),
        ('"Title: Foo Bar"', "Foo Bar"),
        ("Năng lượng sạch cho tương lai", "Năng lượng sạch cho tương lai"),
        (
            "one two three four five six seven eight nine ten eleven twelve",
            "one two three four five six seven eight nine ten eleven twelve",
        ),
        ("Two words", "Two words"),
        ("Single", None),
        ("one two three four five six seven eight nine ten eleven twelve thirteen", None),
        ("a" * 35 + " " + "b" * 35, None),
        ("", None),
        ("   ", None),
        ('""', None),
        (None, None),
        (123, None),
        ([], None),
        ({}, None),
    ],
)
def test_normalize_script_title(raw: object, expected: str | None) -> None:
    assert normalize_script_title(raw) == expected


def test_normalize_script_title_nfd_equals_nfc() -> None:
    nfc = "Năng lượng sạch cho tương lai"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    assert normalize_script_title(nfd) == nfc


def test_normalize_script_title_counts_nfc_length_not_nfd() -> None:
    nfc = "ế" * 12 + " " + "ế" * 16  # 29 chars composed, 85 decomposed (limit is 70)
    nfd = unicodedata.normalize("NFD", nfc)
    assert len(nfc) == 29
    assert len(nfd) > script_title_max_chars
    assert normalize_script_title(nfd) == nfc


def test_title_prompt_note_only_for_section_one() -> None:
    assert "title" in _title_prompt_note(1)
    assert _title_prompt_note(2) == ""


def test_section_title_only_section_one_and_dict() -> None:
    assert _section_title({"title": "Clean Energy Now."}, 1) == "Clean Energy Now"
    assert _section_title({"title": "Clean Energy Now"}, 2) is None
    assert _section_title(["Clean Energy Now"], 1) is None
    assert _section_title({}, 1) is None


def test_normalize_script_title_word_limit_boundary() -> None:
    at_max = " ".join(["w"] * SCRIPT_TITLE_MAX_WORDS)
    assert normalize_script_title(at_max) == at_max
    assert normalize_script_title(at_max + " w") is None


def test_normalize_script_title_rejects_too_many_chars_without_cutting() -> None:
    too_long = ("x" * 10 + " ") * 7 + "y" * 10
    assert len(too_long) > script_title_max_chars
    assert normalize_script_title(too_long) is None

    at_limit = "x" * (script_title_max_chars - 3) + " ab"
    assert len(at_limit) == script_title_max_chars
    assert normalize_script_title(at_limit) == at_limit


# ---------- generator ----------


def _response(payload: dict[str, Any]) -> Any:
    msg = SimpleNamespace(content=json.dumps(payload))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeCompletions:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.handler(**kwargs)


def _build(handler: Any) -> tuple[ScriptGenerator, _FakeCompletions]:
    gen = ScriptGenerator(api_key="test-key", limiter=TokenBucketLimiter())
    completions = _FakeCompletions(handler)
    gen.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return gen, completions


def _section_index(kwargs: dict[str, Any]) -> int:
    system = kwargs["messages"][0]["content"]
    return int(system.split("Write section ")[1].split("/")[0])


def _payload(title: object = None, include_title: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {"paragraphs": [{"text": FILLER, "source_chunk_ids": []}]}
    if include_title:
        data["title"] = title
    return data


def test_only_section_one_prompt_asks_for_title() -> None:
    gen, completions = _build(lambda **_: _response(_payload("Clean Energy Now")))
    gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)

    first, second = (c["messages"][0]["content"] for c in completions.calls)
    assert '"title"' in first
    assert '"title"' not in second


def test_section_one_title_is_normalized_onto_result() -> None:
    gen, _ = _build(lambda **_: _response(_payload('"The Future of Clean Energy."')))
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)
    assert res.title == "The Future of Clean Energy"
    assert res.to_dict()["title"] == "The Future of Clean Energy"


def test_title_from_later_sections_is_ignored() -> None:
    def handler(**kwargs: Any) -> Any:
        if _section_index(kwargs) == 1:
            return _response(_payload("First Section Title"))
        return _response(_payload("Second Section Title"))

    gen, _ = _build(handler)
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)
    assert res.title == "First Section Title"

    def only_later(**kwargs: Any) -> Any:
        return _response(_payload("Late Title Here" if _section_index(kwargs) == 2 else None))

    gen2, _ = _build(only_later)
    assert gen2.generate_free_topic_script(topic="Clean Energy", duration_min=5).title is None


def test_missing_title_gives_none_and_keeps_other_fields() -> None:
    gen, _ = _build(lambda **_: _response(_payload(include_title=False)))
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)
    assert res.title is None
    assert res.word_count == 700
    assert res.flags == ["uncited"]
    assert res.warnings == []


@pytest.mark.parametrize("bad_title", ["Single", "", 123, ["a", "b"], "w " * 20])
def test_invalid_title_gives_none_without_extra_llm_calls(bad_title: object) -> None:
    gen, completions = _build(lambda **_: _response(_payload(bad_title)))
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)
    assert res.title is None
    assert len(completions.calls) == 2
    assert res.models_used == [gen.model_chain[0]]


def test_fallback_model_without_title_gives_none() -> None:
    def handler(**kwargs: Any) -> Any:
        if kwargs["model"] == gen.model_chain[0]:
            raise RuntimeError("429 rate limit")
        return _response(_payload(include_title=False))

    gen, _ = _build(handler)
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)
    assert res.title is None
    assert res.models_used == [gen.model_chain[1]]


def test_title_with_empty_paragraphs_is_dropped_with_that_model() -> None:
    def handler(**kwargs: Any) -> Any:
        if kwargs["model"] == gen.model_chain[0]:
            return _response({"paragraphs": [], "title": "Title From Model A"})
        return _response(_payload("Title From Model B"))

    gen, _ = _build(handler)
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5)
    assert res.title == "Title From Model B"


# ---------- contract ----------


def _script(**extra: Any) -> GeneratedScript:
    return GeneratedScript(
        script="Hello there.",
        word_count=2,
        duration_min=5,
        source="llm",
        template_id=None,
        **extra,
    )


def test_generated_script_title_defaults_to_none_in_dict() -> None:
    data = _script().to_dict()
    assert "title" in data
    assert data["title"] is None


def test_generated_script_title_is_in_dict() -> None:
    assert _script(title="My Title").to_dict()["title"] == "My Title"


# ---------- template ----------


def test_fill_template_title_is_template_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template_engine, "_get_groq_client", lambda: None)
    doc = TemplateDocument(
        metadata=TopicMetadata(
            template_id="wildlife/keystone_5m",
            category_slug="wildlife",
            category="Wildlife",
            topic="  Keystone Species Conservation ",
            topic_slug="keystone_5m",
            duration_min=5,
        ),
        body="Opening thought {{ argument_intro }}. Closing thought.",
        file_path="data/templates/wildlife/keystone_5m.md",
    )
    res = TemplateEngine().fill_template(doc)
    assert res.source == "template"
    assert res.title == doc.metadata.topic.strip()


def test_fill_template_blank_topic_gives_no_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template_engine, "_get_groq_client", lambda: None)
    doc = TemplateDocument(
        metadata=TopicMetadata(
            template_id="wildlife/blank_5m",
            category_slug="wildlife",
            category="Wildlife",
            topic="   ",
            topic_slug="blank_5m",
            duration_min=5,
        ),
        body="Opening thought {{ argument_intro }}. Closing thought.",
        file_path="data/templates/wildlife/blank_5m.md",
    )
    assert TemplateEngine().fill_template(doc).title is None
