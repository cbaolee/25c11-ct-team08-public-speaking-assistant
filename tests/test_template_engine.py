"""Unit tests for WP-B3: parse_slots, assemble_template, batching, and fallback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.text_processing.contracts import (
    DocumentChunk,
    TemplateDocument,
    TopicMetadata,
)
from src.text_processing.limiter import TokenBucketLimiter
from src.text_processing.template_engine import (
    TemplateEngine,
    _call_llm_with_fallback,
    _compute_slot_budgets,
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


class TestTemplateEngine:
    @pytest.fixture()
    def sample_chunks(self) -> list[DocumentChunk]:
        return [
            DocumentChunk(
                chunk_id=1,
                heading="Pacing Dynamics",
                page=1,
                content="Optimal pacing prevents early glycogen depletion.",
            ),
            DocumentChunk(
                chunk_id=2,
                heading="Biomechanical Data",
                page=2,
                content="Sensors reveal efficiency improvements of 4-6%.",
            ),
        ]

    def test_fill_template_mock_llm(
        self,
        sample_template: TemplateDocument,
        sample_chunks: list[DocumentChunk],
    ) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "slots": {
                                "argument_core_mechanism": {
                                    "text": (
                                        "optimal pacing prevents early glycogen depletion "
                                        "and stabilizes aerobic thresholds."
                                    ),
                                    "source_chunk_ids": [1],
                                },
                                "argument_case_evidence": {
                                    "text": "elite runners exhibit consistent velocity profiles.",
                                    "source_chunk_ids": [2],
                                },
                                "argument_counter_perspective": {
                                    "text": "early splits force rivals into physiological debt.",
                                    "source_chunk_ids": [],
                                },
                                "argument_synthesis": {
                                    "text": "integrating biomechanics ensures optimal pacing.",
                                    "source_chunk_ids": [1, 2],
                                },
                            }
                        }
                    )
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        engine = TemplateEngine(client=mock_client)
        result = engine.fill_template(sample_template, chunks=sample_chunks)

        assert result.source == "template"
        assert result.template_id == sample_template.metadata.template_id
        assert "{{" not in result.script
        assert len(result.citations) == 4

        c1 = result.citations[0]
        assert c1.status == "cited"
        assert c1.chunk_id == 1
        assert c1.paragraph == 2

    def test_fill_template_no_chunks_marks_uncited(
        self,
        sample_template: TemplateDocument,
    ) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "slots": {
                                "argument_core_mechanism": {"text": "mech", "source_chunk_ids": []},
                                "argument_case_evidence": {"text": "ev", "source_chunk_ids": []},
                                "argument_counter_perspective": {
                                    "text": "cp",
                                    "source_chunk_ids": [],
                                },
                                "argument_synthesis": {"text": "synth", "source_chunk_ids": []},
                            }
                        }
                    )
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        engine = TemplateEngine(client=mock_client)
        result = engine.fill_template(sample_template, chunks=None)

        assert "uncited" in result.flags
        assert result.citations == []

    def test_fill_template_chat_context_and_deduplicates_multi_slot_paragraph(
        self,
        sample_chunks: list[DocumentChunk],
    ) -> None:
        multi_slot_template = TemplateDocument(
            metadata=TopicMetadata(
                template_id="sports/multi_5m",
                category_slug="sports",
                category="Sports",
                topic="Pacing Dynamics",
                topic_slug="multi_5m",
                duration_min=5,
            ),
            body=(
                "Intro paragraph.\n\n"
                "In paragraph two, {{ argument_unrelated_intro }} whereas "
                "{{ argument_supported_claim }}.\n"
            ),
            file_path="data/templates/sports/multi_5m.md",
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "slots": {
                                "argument_unrelated_intro": {
                                    "text": "medieval castles stood on hills",
                                    "source_chunk_ids": [1],
                                },
                                "argument_supported_claim": {
                                    "text": "optimal pacing prevents early glycogen depletion",
                                    "source_chunk_ids": [1],
                                },
                            }
                        }
                    )
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        engine = TemplateEngine(client=mock_client)
        result = engine.fill_template(
            multi_slot_template,
            chunks=sample_chunks,
            chat_context="Highlight marathon runners in humid climates.",
        )

        sent_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        user_prompt = sent_messages[1]["content"]
        assert "Speaker's notes & requirements from chat" in user_prompt
        assert "Highlight marathon runners in humid climates." in user_prompt
        assert len(result.citations) == 1
        assert result.citations[0].paragraph == 2
        assert result.citations[0].status == "cited"
        assert result.citations[0].chunk_id == 1


class TestInlineFactSlotsAndDynamicBudgets:
    def test_inline_fact_slots_get_short_budget_and_no_mid_sentence_period(self) -> None:
        body = (
            "There is a film clip from {{ argument_film_year }} at the "
            "{{ argument_zoo_location_name }} Zoo showing the "
            "{{ argument_target_extinct_marsupial }}.\n\n"
            "The last {{ argument_target_extinct_marsupial }} died in captivity."
        )
        doc = TemplateDocument(
            metadata=TopicMetadata(
                template_id="wildlife/tasmanian_10m",
                category_slug="wildlife",
                category="Wildlife",
                topic="The Tasmanian Tiger",
                topic_slug="tasmanian_10m",
                duration_min=10,
            ),
            body=body,
            file_path="data/templates/wildlife/tasmanian_10m.md",
        )
        slots = parse_slots(doc)
        occurrences: dict[str, int] = {}
        unique = []
        for s in slots:
            occurrences[s.name] = occurrences.get(s.name, 0) + 1
            if occurrences[s.name] == 1:
                unique.append(s)

        budgets = _compute_slot_budgets(doc, unique, occurrences)
        assert budgets["argument_film_year"] == (1, 6)
        assert budgets["argument_zoo_location_name"] == (1, 6)
        assert budgets["argument_target_extinct_marsupial"] == (1, 6)

        assembled = assemble_template(
            body,
            {
                "argument_film_year": "1933.",
                "argument_zoo_location_name": "Beaumaris",
                "argument_target_extinct_marsupial": "thylacine",
            },
        )
        assert "from 1933 at the Beaumaris Zoo showing the thylacine." in assembled
        assert "1933." not in assembled
        assert "Beaumaris." not in assembled

    def test_dense_template_scales_down_long_slot_budget(self) -> None:
        fixed_prose = " ".join(["software"] * 1100)
        body = (
            f"Good {{{{ argument_time_of_day }}}}, everyone. {fixed_prose}\n\n"
            + "\n\n".join(f"Point {i} explains {{{{ argument_point_{i} }}}}." for i in range(1, 11))
        )
        doc = TemplateDocument(
            metadata=TopicMetadata(
                template_id="information_technology/dense_10m",
                category_slug="information_technology",
                category="Information Technology",
                topic="Agile vs Waterfall",
                topic_slug="dense_10m",
                duration_min=10,
            ),
            body=body,
            file_path="data/templates/information_technology/dense_10m.md",
        )
        slots = parse_slots(doc)
        occurrences = {s.name: 1 for s in slots}
        budgets = _compute_slot_budgets(doc, slots, occurrences)
        assert budgets["argument_time_of_day"] == (1, 6)
        lo, hi = budgets["argument_point_1"]
        assert hi <= 50
        assert lo >= 15
