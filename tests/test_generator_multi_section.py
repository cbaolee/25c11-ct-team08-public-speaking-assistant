"""Unit tests for WP-B4 multi-section free-topic script generator (Issue #19)."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.text_processing.contracts import DocumentChunk, ScriptGenerationError
from src.text_processing.generator import SECTION_PLANS, ScriptGenerator
from src.text_processing.template_engine import TokenBucketLimiter


def _make_response(payload: dict[str, Any]) -> Any:
    msg = SimpleNamespace(content=json.dumps(payload))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeCompletions:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.handler(**kwargs)


def _build_generator(
    handler: Any, limiter: TokenBucketLimiter | None = None
) -> tuple[ScriptGenerator, _FakeCompletions]:
    gen = ScriptGenerator(api_key="test-key", limiter=limiter)
    completions = _FakeCompletions(handler)
    gen.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return gen, completions


@pytest.mark.parametrize("duration_min,expected_sections", [(5, 2), (10, 3), (15, 4), (20, 4)])
def test_generate_free_topic_script_all_durations(
    duration_min: int, expected_sections: int
) -> None:
    target_per_sec = SECTION_PLANS[duration_min][0][1]
    lead = "AI in Healthcare provides speech evidence."
    filler = lead + " " + " ".join(["speech"] * (target_per_sec - len(lead.split())))

    def _handler(**_: Any) -> Any:
        return _make_response({"paragraphs": [{"text": filler, "source_chunk_ids": [0]}]})

    gen, completions = _build_generator(_handler)
    chunks = [
        DocumentChunk(
            chunk_id=0,
            page=2,
            heading="Intro",
            content="AI in Healthcare speech evidence <script>",
        )
    ]
    res = gen.generate_free_topic_script(
        topic="AI in Healthcare",
        duration_min=duration_min,
        chunks=chunks,
        greeting="Hello everyone.",
    )

    assert len(completions.calls) == expected_sections
    assert res.source == "llm"
    assert res.duration_min == duration_min
    assert len(res.citations) == expected_sections
    assert all(c.status == "cited" and c.page == 2 and c.heading == "Intro" for c in res.citations)
    assert "uncited" not in res.flags
    first_user_prompt = completions.calls[0]["messages"][1]["content"]
    assert "<UNTRUSTED_USER_DOCUMENT>" in first_user_prompt
    assert "&lt;script>" in first_user_prompt
    assert "Hello everyone." in first_user_prompt


def test_generate_free_topic_script_uncited_flag_when_no_chunks_or_invalid_id() -> None:
    filler = " ".join(["word"] * 350)
    gen, _ = _build_generator(
        lambda **_: _make_response({"paragraphs": [{"text": filler, "source_chunk_ids": [999]}]})
    )
    chunks = [DocumentChunk(chunk_id=1, page=1, heading="Methods", content="Data")]
    res = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5, chunks=chunks)
    assert all(c.status == "uncited" for c in res.citations)
    assert "uncited" in res.flags

    res_no_src = gen.generate_free_topic_script(topic="Clean Energy", duration_min=5, chunks=None)
    assert res_no_src.citations == []
    assert "uncited" in res_no_src.flags


def test_generate_free_topic_script_chat_context_and_rejects_unsupported_citation() -> None:
    unrelated_para = " ".join(["medieval cathedral masonry"] * 115)
    gen, completions = _build_generator(
        lambda **_: _make_response(
            {"paragraphs": [{"text": unrelated_para, "source_chunk_ids": [0]}]}
        )
    )
    chunks = [
        DocumentChunk(
            chunk_id=0,
            page=3,
            heading="Solar Grid",
            content="Photovoltaic microgrids improve rural clean energy resilience.",
        )
    ]
    res = gen.generate_free_topic_script(
        topic="Clean Energy Microgrids",
        duration_min=5,
        chunks=chunks,
        chat_context="Focus on university campus microgrid deployment and student involvement.",
    )
    first_user_prompt = completions.calls[0]["messages"][1]["content"]
    assert "Speaker's notes & requirements from chat" in first_user_prompt
    assert "university campus microgrid deployment" in first_user_prompt
    assert all(c.status == "uncited" for c in res.citations)
    assert "uncited" in res.flags


def test_generate_free_topic_script_ignores_unrelated_document_chunks() -> None:
    para = " ".join(["volleyball serving teamwork rotation strategy"] * 70)
    gen, completions = _build_generator(
        lambda **_: _make_response({"paragraphs": [{"text": para, "source_chunk_ids": [1]}]})
    )
    unrelated_chunks = [
        DocumentChunk(
            chunk_id=1,
            page=1,
            heading="Tax Law",
            content="Corporate amortization schedules and municipal bond yields.",
        )
    ]
    res = gen.generate_free_topic_script(
        topic="Volleyball Teamwork Strategy",
        duration_min=5,
        chunks=unrelated_chunks,
    )
    first_user_prompt = completions.calls[0]["messages"][1]["content"]
    assert "<UNTRUSTED_USER_DOCUMENT>" not in first_user_prompt
    assert all(c.status == "uncited" for c in res.citations)
    assert "uncited" in res.flags


def test_parse_section_paragraphs_strips_stray_empty_brackets() -> None:
    parsed = ScriptGenerator._parse_section_paragraphs(
        {
            "paragraphs": [
                {
                    "text": "Hello everyone, let us talk about clean energy. []",
                    "source_chunk_ids": [],
                },
                {"text": "Wind power [] grows every year. [ ]", "source_chunk_ids": []},
            ]
        }
    )
    assert parsed == [
        ("Hello everyone, let us talk about clean energy.", []),
        ("Wind power grows every year.", []),
    ]


def test_generate_free_topic_script_fallback_chain_and_503_exhaustion() -> None:
    filler = " ".join(["word"] * 350)

    def _flaky_handler(**kwargs: Any) -> Any:
        if kwargs["model"] == "openai/gpt-oss-120b":
            raise RuntimeError("429 rate limit")
        return _make_response({"paragraphs": [{"text": filler, "source_chunk_ids": []}]})

    gen, _ = _build_generator(_flaky_handler)
    res = gen.generate_free_topic_script(topic="Space Exploration", duration_min=5)
    assert res.models_used == [gen.model_chain[1]]

    gen_fail, _ = _build_generator(lambda **_: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(ScriptGenerationError) as exc_info:
        gen_fail.generate_free_topic_script(topic="Space Exploration", duration_min=5)
    assert exc_info.value.error_code == "generation_unavailable"
    assert exc_info.value.status_code == 503


def test_generate_free_topic_script_validation_and_token_limiter() -> None:
    gen, _ = _build_generator(lambda **_: _make_response({"script": "short text"}))
    with pytest.raises(ScriptGenerationError) as exc_topic:
        gen.generate_free_topic_script(topic="   ", duration_min=5)
    assert exc_topic.value.error_code == "output_invalid"

    with pytest.raises(ScriptGenerationError) as exc_dur:
        gen.generate_free_topic_script(topic="Valid Topic", duration_min=7)
    assert exc_dur.value.error_code == "output_invalid"

    res_short = gen.generate_free_topic_script(topic="Valid Topic", duration_min=5)
    assert "word_count_out_of_range" in res_short.flags

    zero_limiter = TokenBucketLimiter(rpm_limit=0, tpm_limit=10)
    gen_limited, _ = _build_generator(
        lambda **_: _make_response({"script": "short"}), limiter=zero_limiter
    )
    with pytest.raises(ScriptGenerationError) as exc_lim:
        gen_limited.generate_free_topic_script(topic="Valid Topic", duration_min=5)
    assert exc_lim.value.error_code == "generation_unavailable"
