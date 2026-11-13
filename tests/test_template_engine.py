"""Unit tests for WP-B3: parse_slots, assemble_template, batching, and fallback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.text_processing.contracts import (
    TemplateDocument,
    TopicMetadata,
)
from src.text_processing.limiter import TokenBucketLimiter
from src.text_processing.template_engine import (
    _call_llm_with_fallback,
    _group_slots_into_batches,
    assemble_template,
    parse_slots,
    validate_assembled_script,
)


@pytest.fixture()
def sample_template() -> TemplateDocument:
    body = (
        "Good morning, audience. Today we discuss the core principles.\n\n"
        "First, examining the underlying dynamic shows that {{ argument_core_mechanism }}.\n\n"
        "Furthermore, real-world case studies illustrate that {{ argument_case_evidence }}.\n\n"
        "On the other hand, critics argue that {{ argument_counter_perspective }}.\n\n"
        "In conclusion, synthesizing these dimensions reveals that {{ argument_synthesis }}.\n"
        "Thank you."
    )
    return TemplateDocument(
        metadata=TopicMetadata(
            template_id="sports/test_sport_5m",
            category_slug="sports",
            category="Sports",
            topic="Test Sport Pacing",
            topic_slug="test_sport_5m",
            duration_min=5,
        ),
        body=body,
        file_path="data/templates/sports/test_sport_5m.md",
    )


class TestParseSlots:
    def test_extracts_arguments_and_entities(self, sample_template: TemplateDocument) -> None:
        slots = parse_slots(sample_template)
        assert len(slots) == 4
        assert [s.name for s in slots] == [
            "argument_core_mechanism",
            "argument_case_evidence",
            "argument_counter_perspective",
            "argument_synthesis",
        ]
        assert all(s.slot_type == "argument" for s in slots)

    def test_lead_in_and_follow_text_extracted(self, sample_template: TemplateDocument) -> None:
        slots = parse_slots(sample_template)
        first = slots[0]
        assert "underlying dynamic shows that" in first.lead_in
        last = slots[-1]
        assert "Thank you" in last.follow_text


class TestAssembleTemplate:
    def test_pure_regex_no_ssti(self) -> None:
        body = "Value is {{ argument_test }}."
        malicious = "{{ 7 * 7 }} and {{ config }}"
        assembled = assemble_template(body, {"argument_test": malicious})
        assert "{{ 7 * 7 }}" in assembled

    def test_boundary_period_normalization(self) -> None:
        body = "Before {{ argument_one }}. Middle {{ argument_two }} after."
        values = {
            "argument_one": "sentence ending with dot.",
            "argument_two": "no dot",
        }
        assembled = assemble_template(body, values)
        assert "ending with dot.." not in assembled
        assert "ending with dot." in assembled
        assert "Middle no dot." in assembled


class TestValidateAssembledScript:
    def test_detects_unresolved_slots(self) -> None:
        issues = validate_assembled_script("Hello {{ argument_leftover }} world.", 5)
        assert "unresolved_slots" in issues

    def test_word_count_check(self) -> None:
        issues = validate_assembled_script("This is way too short.", 5)
        assert any(i.startswith("word_count_out_of_range") for i in issues)


class TestSlotBatchingAndFallback:
    def test_group_slots_within_budget(self, sample_template: TemplateDocument) -> None:
        slots = parse_slots(sample_template)
        batches = _group_slots_into_batches(slots, max_tokens_per_batch=5000)
        assert len(batches) >= 1
        total_batched = sum(len(b) for b in batches)
        assert total_batched == 4

    def test_fallback_chain_on_model_failure(self) -> None:
        mock_client = MagicMock()
        ok_response = MagicMock()
        ok_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({"slots": {"arg": {"text": "ok", "source_chunk_ids": []}}})
                )
            )
        ]
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("Rate limit 429"),
            RuntimeError("Rate limit 429"),
            ok_response,
        ]

        limiter = TokenBucketLimiter()
        data, model_used = _call_llm_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            model_chain=("primary-model", "fallback-model"),
            limiter=limiter,
            estimated_tokens=100,
            client=mock_client,
        )
        assert model_used == "fallback-model"
        assert "slots" in data
