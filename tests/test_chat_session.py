"""Unit tests for Phase 1: ChatSessionState, ChatSessionStore, and minimal-token gathering."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import types
import unicodedata
import zlib
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.app.constants import CONSTANTS
from src.text_processing.chat_session import (
    FREE_TOPIC_TURN1_READY_WORDS,
    GROUP_COUNTER,
    GROUP_EVIDENCE,
    GROUP_MAIN,
    READY_MESSAGE,
    ChatSessionState,
    ChatSessionStore,
    ContextEntry,
    TurnStepTracker,
    analyze_slot_coverage,
    append_to_context_window,
    build_followup_reply,
    build_turn1_decision,
    build_turn1_question,
    check_ready_to_generate,
    classify_argument_slot,
    compact_context_entries,
    deterministic_compact_summary,
    evaluate_and_build_followup,
    group_uncovered_slots,
    ingest_upload_file,
    is_free_topic_identifiable,
    normalize_turn_entry,
)
from src.text_processing.contracts import (
    ETA_BUFFER_S,
    DocumentChunk,
    ScriptGenerationRequest,
    ScriptJobState,
    TemplateDocument,
    TopicMetadata,
)
from src.text_processing.limiter import TokenBucketLimiter
from src.text_processing.moderation import ContentModerator
from src.text_processing.parser import (
    FILE_SIZE_LIMITS_BYTES,
    MAX_PDF_SIZE_BYTES,
    MAX_TEXT_FILE_BYTES,
    DocumentParserError,
    max_bytes_for_extension,
    validate_turn_text_length,
)
from src.text_processing.pipeline import ScriptGenerationPipeline
from src.text_processing.retrieval import SemanticRetriever
from src.text_processing.template_engine import assemble_template
from src.text_processing.template_store import TemplateStore


class MockSentenceTransformer:
    """Deterministic, lightweight SentenceTransformer mock producing 384-d L2 vectors."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name

    def encode(
        self,
        texts: list[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        dim = 384
        vecs = []
        for text in texts:
            vec = np.zeros(dim, dtype=np.float32)
            vec[0] = 0.001
            tokens = re.findall(r"\w+", text.lower())
            for token in tokens:
                idx = zlib.crc32(token.encode("utf-8")) % dim
                vec[idx] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vecs.append(vec)
        return np.array(vecs, dtype=np.float32)


@pytest.fixture(autouse=True)
def mock_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> MockSentenceTransformer:
    """Mock sentence_transformers globally for chat session tests."""
    mock_instance = MockSentenceTransformer()
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.SentenceTransformer = lambda model_name="all-MiniLM-L6-v2": mock_instance
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_module)

    SemanticRetriever._shared_model = None
    SemanticRetriever._load_attempted = False
    yield mock_instance
    SemanticRetriever._shared_model = None
    SemanticRetriever._load_attempted = False


@pytest.fixture()
def sample_template() -> TemplateDocument:
    body = (
        "Welcome {{ entity_audience_type }} to today's keynote.\n\n"
        "First, examining the core foundation shows that {{ argument_core_mechanism }}.\n\n"
        "Furthermore, real-world case studies illustrate that {{ argument_case_evidence }}.\n\n"
        "On the other hand, critics argue that {{ argument_counter_perspective }}.\n\n"
        "In conclusion, synthesizing these dimensions reveals that {{ argument_synthesis }}.\n"
    )
    return TemplateDocument(
        metadata=TopicMetadata(
            template_id="sports/sample_test",
            category_slug="sports",
            category="Sports",
            topic="Marathon Pacing Strategies",
            topic_slug="marathon_pacing",
            duration_min=5,
        ),
        body=body,
        file_path="data/templates/sports/sample_test.md",
    )


class TestChatSessionStore:
    def test_store_put_and_get_success(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=60.0)
        state = ChatSessionState(
            session_id="s1",
            user_id="user_123",
            category="Sports",
            duration_min=5,
        )
        store.put(state)
        retrieved = store.get("s1", user_id="user_123")
        assert retrieved is not None
        assert retrieved.session_id == "s1"
        assert retrieved.user_id == "user_123"

    def test_store_user_id_isolation(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=60.0)
        state = ChatSessionState(
            session_id="s_private",
            user_id="user_alice",
            category="Wildlife",
            duration_min=10,
        )
        store.put(state)

        # Bob attempts to access Alice's session
        bob_access = store.get("s_private", user_id="user_bob")
        assert bob_access is None

        # Alice accesses her own session
        alice_access = store.get("s_private", user_id="user_alice")
        assert alice_access is not None

    def test_store_sliding_ttl_expiration(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=0.05)
        state = ChatSessionState(
            session_id="s_expire",
            user_id="user_alice",
            category="IT",
            duration_min=5,
        )
        store.put(state)
        time.sleep(0.08)

        # Should be expired and return None
        assert store.get("s_expire", user_id="user_alice") is None
        assert len(store) == 0

    def test_store_capacity_eviction_lru(self) -> None:
        store = ChatSessionStore(capacity=3, ttl_seconds=60.0)
        for i in range(1, 4):
            store.put(
                ChatSessionState(
                    session_id=f"s{i}",
                    user_id="u1",
                    category="Sports",
                    duration_min=5,
                )
            )

        # Access s1 to move it to MRU (s2 becomes LRU)
        _ = store.get("s1", user_id="u1")

        # Put 4th item -> should evict s2
        store.put(
            ChatSessionState(
                session_id="s4",
                user_id="u1",
                category="Sports",
                duration_min=5,
            )
        )
        assert store.get("s2", user_id="u1") is None
        assert store.get("s1", user_id="u1") is not None
        assert store.get("s3", user_id="u1") is not None
        assert store.get("s4", user_id="u1") is not None

    def test_store_delete_scoping(self) -> None:
        store = ChatSessionStore(capacity=10, ttl_seconds=60.0)
        state = ChatSessionState(
            session_id="s_del",
            user_id="user_alice",
            category="IT",
            duration_min=5,
        )
        store.put(state)

        # Bob cannot delete Alice's session
        assert not store.delete("s_del", user_id="user_bob")
        assert store.get("s_del", user_id="user_alice") is not None

        # Alice can delete her session
        assert store.delete("s_del", user_id="user_alice")
        assert store.get("s_del", user_id="user_alice") is None

    def test_store_thread_safety(self) -> None:
        store = ChatSessionStore(capacity=50, ttl_seconds=60.0)

        def worker(worker_id: int) -> None:
            for i in range(20):
                sid = f"thread_{worker_id}_{i}"
                store.put(
                    ChatSessionState(
                        session_id=sid,
                        user_id=f"user_{worker_id}",
                        category="Sports",
                        duration_min=5,
                    )
                )
                _ = store.get(sid, user_id=f"user_{worker_id}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(store) <= 50


class TestSemanticBucketing:
    def test_classify_argument_slot_groups(self) -> None:
        # Group 1: Main thesis & key points
        assert classify_argument_slot("argument_core_mechanism") == GROUP_MAIN
        assert classify_argument_slot("argument_foundation") == GROUP_MAIN
        assert classify_argument_slot("argument_synthesis") == GROUP_MAIN
        assert classify_argument_slot("argument_unspecified_concept") == GROUP_MAIN

        # Group 2: Examples / evidence / data
        assert classify_argument_slot("argument_case_evidence") == GROUP_EVIDENCE
        assert classify_argument_slot("argument_empirical_data") == GROUP_EVIDENCE
        assert classify_argument_slot("argument_practice_study") == GROUP_EVIDENCE

        # Group 3: Counter-arguments / limitations
        assert classify_argument_slot("argument_counter_perspective") == GROUP_COUNTER
        assert classify_argument_slot("argument_challenge_tradeoff") == GROUP_COUNTER
        assert classify_argument_slot("argument_opposing_objection") == GROUP_COUNTER

    def test_group_uncovered_slots_order_and_filtering(self) -> None:
        # Empty
        assert group_uncovered_slots([]) == []

        # Only evidence
        evidence_slots = ["argument_case_evidence", "argument_clinical_study"]
        assert group_uncovered_slots(evidence_slots) == [GROUP_EVIDENCE]

        # Evidence + counter (order preserved: Main, Evidence, Counter)
        mixed_slots = ["argument_case_evidence", "argument_counter_perspective"]
        assert group_uncovered_slots(mixed_slots) == [GROUP_EVIDENCE, GROUP_COUNTER]

        # All three groups
        all_slots = [
            "argument_counter_perspective",
            "argument_foundation",
            "argument_case_evidence",
        ]
        assert group_uncovered_slots(all_slots) == [GROUP_MAIN, GROUP_EVIDENCE, GROUP_COUNTER]


class TestAnalyzeSlotCoverage:
    def test_analyze_empty_chunks_returns_zero_coverage(
        self,
        sample_template: TemplateDocument,
    ) -> None:
        retriever = SemanticRetriever()
        cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
            template_document=sample_template,
            chunks=[],
            chunk_embeddings=None,
            retriever=retriever,
            prompt="",
        )
        assert cov_ratio == 0.0
        assert "entity_audience_type" in missing_entities
        assert GROUP_MAIN in missing_groups
        assert GROUP_EVIDENCE in missing_groups
        assert GROUP_COUNTER in missing_groups

    def test_analyze_slot_coverage_with_matching_chunks(
        self,
        sample_template: TemplateDocument,
    ) -> None:
        retriever = SemanticRetriever()
        chunks = [
            DocumentChunk(
                chunk_id=1,
                heading="Core Mechanism",
                page=1,
                content="Core mechanism and physiological foundation of marathon pacing.",
            ),
            DocumentChunk(
                chunk_id=2,
                heading="Case Evidence",
                page=1,
                content="Case evidence and real world empirical data from elite marathon runners.",
            ),
            DocumentChunk(
                chunk_id=3,
                heading="Counter Perspective",
                page=2,
                content="Critics argue counter perspectives and physiological limitations.",
            ),
            DocumentChunk(
                chunk_id=4,
                heading="Synthesis",
                page=2,
                content="Synthesizing pacing dimensions ensures peak athletic performance.",
            ),
        ]
        embeddings = retriever.encode_chunks(chunks)

        cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
            template_document=sample_template,
            chunks=chunks,
            chunk_embeddings=embeddings,
            retriever=retriever,
            prompt="Speech addressed to college student audience type.",
        )
        assert cov_ratio >= 0.75
        assert len(missing_entities) == 0

    def test_analyze_slot_coverage_string_template_support(self) -> None:
        raw_text = (
            "Speaker {{ entity_presenter }}.\n\n"
            "Key idea: {{ argument_thesis }}.\n\n"
            "Evidence: {{ argument_case_evidence }}."
        )
        retriever = SemanticRetriever()
        cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
            template_document=raw_text,
            chunks=[],
            chunk_embeddings=None,
            retriever=retriever,
            prompt="Presenter Dr. Smith",
        )
        assert cov_ratio == 0.0
        assert "entity_presenter" not in missing_entities  # covered by prompt!
        assert GROUP_MAIN in missing_groups
        assert GROUP_EVIDENCE in missing_groups

    def test_analyze_slot_coverage_tracks_chat_notes_without_uploaded_chunks(
        self,
        sample_template: TemplateDocument,
    ) -> None:
        retriever = SemanticRetriever()
        cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
            template_document=sample_template,
            chunks=[],
            chunk_embeddings=None,
            retriever=retriever,
            prompt="Speech addressed to college student audience type.",
            user_notes=[
                "Core mechanism and physiological foundation of marathon pacing.",
                "Case evidence and real world empirical data from elite marathon runners.",
                "In conclusion, synthesizing these dimensions shows synthesis of pacing.",
            ],
        )
        assert cov_ratio >= 0.75
        assert "entity_audience_type" not in missing_entities
        assert GROUP_MAIN not in missing_groups
        assert GROUP_EVIDENCE not in missing_groups
        assert GROUP_COUNTER in missing_groups


class Test3LayerStopRule:
    def test_layer_1_sufficient_coverage(self) -> None:
        # Layer 1 holds: 0 missing entities and coverage >= 0.7
        is_ready = check_ready_to_generate(
            selected_template_id="sports/sample",
            missing_entities=[],
            coverage_ratio=0.75,
            gather_turns=0,
        )
        assert is_ready is True

    def test_layer_1_unmet_when_entities_missing(self) -> None:
        # Coverage is high but missing entity blocks Layer 1
        is_ready = check_ready_to_generate(
            selected_template_id="sports/sample",
            missing_entities=["entity_guest_name"],
            coverage_ratio=1.0,
            gather_turns=1,
        )
        assert is_ready is False

    def test_layer_1_unmet_when_coverage_low(self) -> None:
        is_ready = check_ready_to_generate(
            selected_template_id="sports/sample",
            missing_entities=[],
            coverage_ratio=0.69,
            gather_turns=1,
        )
        assert is_ready is False

    def test_no_forced_2_turn_cap(self) -> None:
        # Removing the 2-turn hard cap: missing entities & low coverage stay False at turn 2+
        is_ready = check_ready_to_generate(
            selected_template_id="sports/sample",
            missing_entities=["entity_target", "entity_name"],
            coverage_ratio=0.1,
            gather_turns=2,
        )
        assert is_ready is False

    def test_layer_3_free_topic_with_uploaded_file(self) -> None:
        is_ready = check_ready_to_generate(
            selected_template_id=None,
            missing_entities=[],
            coverage_ratio=0.0,
            gather_turns=0,
            files_loaded=["research_paper.pdf"],
            prompt="Short topic",
        )
        assert is_ready is True

    def test_layer_3_free_topic_with_sufficient_words(self) -> None:
        long_notes = ["word " * 50, "word " * 60, "word " * 45]  # > 150 words
        is_ready = check_ready_to_generate(
            selected_template_id=None,
            missing_entities=[],
            coverage_ratio=0.0,
            gather_turns=0,
            files_loaded=[],
            prompt="Initial prompt",
            user_notes=long_notes,
        )
        assert is_ready is True

    def test_layer_3_free_topic_insufficient(self) -> None:
        is_ready = check_ready_to_generate(
            selected_template_id=None,
            missing_entities=[],
            coverage_ratio=0.0,
            gather_turns=0,
            files_loaded=[],
            prompt="Short prompt with few words",
            user_notes=["Just a note"],
        )
        assert is_ready is False

    def test_template_mode_does_not_trigger_layer_3(self) -> None:
        # Layer 3 is only for selected_template_id is None
        is_ready = check_ready_to_generate(
            selected_template_id="sports/sample",
            missing_entities=["entity_name"],
            coverage_ratio=0.4,
            gather_turns=0,
            files_loaded=["research.pdf"],
        )
        assert is_ready is False


class TestBuildFollowupReply:
    def test_ready_to_generate_returns_deterministic_message(self) -> None:
        reply = build_followup_reply(
            topic="Marathon Pacing",
            ready_to_generate=True,
            missing_entities=["entity_name"],
            missing_groups=[GROUP_MAIN],
            gather_turns=0,
        )
        assert reply == READY_MESSAGE

    def test_gather_turns_2_continues_asking_when_not_ready(self) -> None:
        reply = build_followup_reply(
            topic="Marathon Pacing",
            ready_to_generate=False,
            missing_entities=["entity_name"],
            missing_groups=[GROUP_MAIN],
            gather_turns=2,
        )
        assert reply != READY_MESSAGE
        assert "**name**" in reply
        assert f"**{GROUP_MAIN}**" in reply

    def test_client_none_falls_back_to_checklist(self) -> None:
        reply = build_followup_reply(
            topic="Space Exploration",
            ready_to_generate=False,
            missing_entities=["entity_mission_name"],
            missing_groups=[GROUP_EVIDENCE, GROUP_COUNTER],
            gather_turns=0,
            client=None,
        )
        assert "Space Exploration" in reply
        assert "mission name" in reply
        assert GROUP_EVIDENCE in reply
        assert GROUP_COUNTER in reply

    def test_client_exception_falls_back_to_checklist(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Groq 429 Rate Limited")

        reply = build_followup_reply(
            topic="Renewable Energy",
            ready_to_generate=False,
            missing_entities=["entity_region"],
            missing_groups=[GROUP_MAIN],
            gather_turns=1,
            client=mock_client,
        )
        assert "Renewable Energy" in reply
        assert "region" in reply
        assert GROUP_MAIN in reply

    def test_groq_mock_success(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [
            MagicMock(
                message=MagicMock(
                    content="Could you share a specific real-world example or case study?"
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_resp

        reply = build_followup_reply(
            topic="Autonomous Vehicles",
            ready_to_generate=False,
            missing_entities=[],
            missing_groups=[GROUP_EVIDENCE],
            gather_turns=0,
            client=mock_client,
        )
        assert reply == "Could you share a specific real-world example or case study?"

        # Verify no document chunks were passed to the LLM
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        assert "Autonomous Vehicles" in user_msg
        assert "Chunk" not in user_msg


class TestIngestUploadFile:
    def test_ingest_empty_bytes_raises_error(self) -> None:
        with pytest.raises(DocumentParserError, match="empty"):
            ingest_upload_file(b"", "document.pdf")

    def test_ingest_unsupported_file_extension(self) -> None:
        with pytest.raises(DocumentParserError, match="Unsupported file format"):
            ingest_upload_file(b"some content", "data.xlsx")

    def test_ingest_markdown_file(self) -> None:
        md_bytes = (
            b"# Introduction to Quantum Computing\n"
            b"Quantum computers harness qubits to perform complex operations.\n\n"
            b"# Current Limitations\n"
            b"Decoherence and thermal noise remain major engineering hurdles."
        )
        chunks = ingest_upload_file(md_bytes, "notes.md")
        assert len(chunks) == 2
        assert "Quantum Computing" in chunks[0].heading
        assert "Limitations" in chunks[1].heading

    def test_ingest_txt_file(self) -> None:
        txt_bytes = b"Public speaking requires deliberate vocal pacing and structured arguments."
        chunks = ingest_upload_file(txt_bytes, "speech_draft.txt")
        assert len(chunks) >= 1
        assert "deliberate vocal pacing" in chunks[0].content

    def test_ingest_file_exceeding_2mb_raises_error(self) -> None:
        large_bytes = b"x" * (2 * 1024 * 1024 + 1)
        with pytest.raises(DocumentParserError) as exc_info:
            ingest_upload_file(large_bytes, "large.txt")
        assert exc_info.value.error_code == "file_too_large"
        assert "2MB" in exc_info.value.message

    def test_ingest_null_bytes_raises_error(self) -> None:
        binary_bytes = b"hello\x00world"
        with pytest.raises(DocumentParserError) as exc_info:
            ingest_upload_file(binary_bytes, "binary.txt")
        assert exc_info.value.error_code == "invalid_text_file"
        assert "null bytes" in exc_info.value.message


class TestAssembleTemplateEdgeCases:
    def test_assemble_template_mid_sentence_entity_slot_no_unwanted_period(self) -> None:
        body = "Welcome {{ entity_audience_type }} to today's keynote."
        slot_values = {"entity_audience_type": "College Students"}
        assembled = assemble_template(body, slot_values)
        assert assembled == "Welcome College Students to today's keynote."
        assert "College Students." not in assembled

    def test_assemble_template_end_of_block_argument_slot_adds_period(self) -> None:
        body = "Welcome everyone.\n\nFirst, {{ argument_core_mechanism }}\n\nConclusion."
        slot_values = {"argument_core_mechanism": "trophic cascades regulate the balance"}
        assembled = assemble_template(body, slot_values)
        assert "First, trophic cascades regulate the balance.\n\n" in assembled


class TestPipelineJobCapacityEviction:
    def test_evict_jobs_if_needed_removes_oldest_finished_jobs(self) -> None:
        pipeline = ScriptGenerationPipeline(
            template_store=TemplateStore(Path("nonexistent")),
        )
        pipeline.max_jobs_capacity = 3

        job1 = pipeline.create_job("user1")
        job1.status = "completed"
        job2 = pipeline.create_job("user1")
        job2.status = "queued"
        job3 = pipeline.create_job("user1")
        job3.status = "failed"

        assert len(pipeline._jobs) == 3

        job4 = pipeline.create_job("user1")
        assert len(pipeline._jobs) == 3
        assert job1.job_id not in pipeline._jobs
        assert job2.job_id in pipeline._jobs
        assert job3.job_id in pipeline._jobs
        assert job4.job_id in pipeline._jobs


class TestPerTurnLimitsAndExtensionCaps:
    def test_file_size_limits_mapping_matches_constants(self) -> None:
        assert FILE_SIZE_LIMITS_BYTES[".pdf"] == MAX_PDF_SIZE_BYTES
        assert FILE_SIZE_LIMITS_BYTES[".md"] == MAX_TEXT_FILE_BYTES
        assert FILE_SIZE_LIMITS_BYTES[".txt"] == MAX_TEXT_FILE_BYTES
        assert max_bytes_for_extension("notes.PDF") == MAX_PDF_SIZE_BYTES
        assert max_bytes_for_extension("outline.md") == MAX_TEXT_FILE_BYTES
        with pytest.raises(DocumentParserError) as exc_info:
            max_bytes_for_extension("slides.pptx")
        assert exc_info.value.error_code == "unsupported_file_type"

    def test_validate_turn_text_length_checks_chars_and_words(self) -> None:
        validate_turn_text_length("Short valid message.", max_chars=100, max_words=20)
        with pytest.raises(DocumentParserError) as char_exc:
            validate_turn_text_length("a" * 51, max_chars=50, max_words=100)
        assert char_exc.value.error_code == "text_too_long"

        with pytest.raises(DocumentParserError) as word_exc:
            validate_turn_text_length(" ".join(["word"] * 11), max_chars=500, max_words=10)
        assert word_exc.value.error_code == "text_too_long"


class TestBoundedContextAndCompaction:
    def test_normalize_turn_entry_strips_filler_and_tags(self) -> None:
        entry = normalize_turn_entry(
            "Sure, here is my point:   Our audience is first-year medical students.\n\n\n"
            "Focus on ethics.",
            turn=2,
            source="chat",
        )
        assert entry is not None
        assert entry.turn == 2
        assert entry.source == "chat"
        assert "Our audience is first-year medical students." in entry.text
        assert not entry.text.lower().startswith("sure")
        assert entry.formatted().startswith("[Turn 2 | chat]")

    def test_append_to_context_window_compacts_via_smaller_groq_model(self) -> None:
        session = ChatSessionState(
            session_id="s-compact",
            user_id="u1",
            category="science",
            duration_min=10,
            topic="CRISPR Ethics",
        )
        mock_client = MagicMock()
        mock_resp = MagicMock()
        summary_json = (
            '{"summary": "- Audience: grad students\\n'
            '- Key focus: gene therapy safety"}'
        )
        mock_resp.choices = [MagicMock(message=MagicMock(content=summary_json))]
        mock_resp.usage = MagicMock(total_tokens=180)
        mock_client.chat.completions.create.return_value = mock_resp

        compacted_flags = []
        for turn in range(1, 5):
            _, compacted = append_to_context_window(
                session,
                f"Turn {turn} detailed fact about gene therapy trial #{turn} with 95% accuracy.",
                turn=turn,
                source="chat",
                client=mock_client,
                compaction_model="openai/gpt-oss-20b",
                limiter=TokenBucketLimiter(),
                max_entries=3,
                keep_recent=2,
            )
            compacted_flags.append(compacted)

        assert compacted_flags == [False, False, False, True]
        assert session.compaction_count == 1
        assert len(session.context_window) == 2
        assert session.context_window[-1].turn == 4
        assert "grad students" in session.compacted_summary
        assert mock_client.chat.completions.create.call_args.kwargs["model"] == "openai/gpt-oss-20b"

    def test_compaction_deterministic_fallback_when_groq_fails_or_rate_limited(self) -> None:
        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("429 quota exhausted")

        entries = [
            ContextEntry(
                turn=1, source="chat", text="Target audience is 200 high school teachers."
            ),
            ContextEntry(
                turn=2, source="chat", text="Include 2024 UNESCO AI literacy benchmark."
            ),
        ]
        summary, used_llm = compact_context_entries(
            "",
            entries,
            topic="AI in Education",
            client=failing_client,
            limiter=TokenBucketLimiter(),
            max_summary_chars=400,
        )
        assert used_llm is False
        assert "200 high school teachers" in summary
        assert "2024 UNESCO" in summary

        # Rate-limiter exhaustion skips Groq cleanly and uses deterministic summary
        tight_limiter = TokenBucketLimiter(rpm_limit=0, tpm_limit=10)
        summary2, used_llm2 = compact_context_entries(
            summary,
            [ContextEntry(turn=3, source="chat", text="Keep tone practical and optimistic.")],
            client=MagicMock(),
            limiter=tight_limiter,
            max_summary_chars=300,
        )
        assert used_llm2 is False
        assert "practical and optimistic" in summary2

    def test_deterministic_compact_summary_enforces_max_chars(self) -> None:
        entries = [
            ContextEntry(
                turn=i,
                source="chat",
                text=f"Point {i}: unique fact number {i * 17} for speech.",
            )
            for i in range(1, 15)
        ]
        summary = deterministic_compact_summary("", entries, max_chars=220)
        assert len(summary) <= 220
        assert "Point 14" in summary

    def test_append_to_context_window_trims_kept_on_consecutive_near_ceiling_entries(self) -> None:
        from src.text_processing.chat_session import CONTEXT_WINDOW_MAX_CHARS

        session = ChatSessionState(
            session_id="s-ceiling",
            user_id="u1",
            category="science",
            duration_min=5,
            topic="Energy Storage",
        )
        append_to_context_window(
            session,
            "Short initial audience note for students " + ("x" * 350),
            turn=1,
            source="chat",
        )
        _, compacted_2 = append_to_context_window(
            session,
            "Turn 2 detailed evidence " + ("a" * 3800),
            turn=2,
            source="chat",
        )
        assert compacted_2 is False

        _, compacted_3 = append_to_context_window(
            session,
            "Turn 3 detailed counterpoint " + ("b" * 3800),
            turn=3,
            source="chat",
        )
        assert compacted_3 is True
        assert len(session.context_window) == 1
        assert session.context_window[0].turn == 3
        assert session.context_char_count() <= CONTEXT_WINDOW_MAX_CHARS

    def test_pipeline_run_consumes_compacted_summary_and_active_window(self) -> None:
        from src.text_processing.contracts import GeneratedScript

        store = TemplateStore(Path("nonexistent"))
        mock_llm = MagicMock()
        mock_llm.generate_free_topic_script.return_value = GeneratedScript(
            script=" ".join(["speech"] * 650),
            word_count=650,
            duration_min=5,
            source="llm",
            template_id=None,
            models_used=["openai/gpt-oss-120b"],
        )
        pipeline = ScriptGenerationPipeline(
            template_store=store,
            llm_generator=mock_llm,
            moderator=ContentModerator(enable_llama_guard=False),
        )
        sess = ChatSessionState(
            session_id="s-pipe",
            user_id="u1",
            category="free",
            duration_min=5,
            initial_prompt="AI Ethics",
            compacted_summary=(
                "- Audience: software engineers\n- Focus on algorithmic accountability"
            ),
            context_window=[
                ContextEntry(
                    turn=3,
                    source="chat",
                    text="Cite the EU AI Act tiered risk framework with concrete startup examples.",
                )
            ],
        )
        pipeline.session_store.put(sess)
        try:
            pipeline.run(
                ScriptGenerationRequest(
                    topic="AI Ethics",
                    category="free",
                    duration_min=5,
                    session_id="s-pipe",
                    user_id="u1",
                    user_feedback="Emphasize practical audit checklists in the closing.",
                )
            )
            kwargs = mock_llm.generate_free_topic_script.call_args.kwargs
            assert "[Session Summary]" in kwargs["chat_context"]
            assert "algorithmic accountability" in kwargs["chat_context"]
            assert "EU AI Act" in kwargs["chat_context"]
            assert "practical audit checklists" in kwargs["chat_context"]

            updated = pipeline.session_store.get("s-pipe", user_id="u1")
            assert updated is not None
            assert any("practical audit checklists" in e.text for e in updated.context_window)
        finally:
            pipeline.session_store.delete("s-pipe", user_id="u1")

    def test_dual_track_compaction_keeps_raw_citable_facts_and_never_cites_summary(self) -> None:
        """Track 1 compacts context_window into compacted_summary; Track 2 keeps verbatim
        raw user_notes for source_classifier/NLI chunks and excludes compacted_summary."""
        from src.text_processing.contracts import GeneratedScript, ScriptGenerationRequest
        from src.text_processing.pipeline import ScriptGenerationPipeline

        mock_llm = MagicMock()
        mock_llm.retriever = None
        mock_llm.generate_free_topic_script.return_value = GeneratedScript(
            script=" ".join(["word"] * 650),
            word_count=650,
            duration_min=5,
            source="llm",
            template_id=None,
            models_used=["mock"],
        )
        mock_tpl_engine = MagicMock()
        mock_tpl_engine.retriever = None
        mock_mod = MagicMock(unsafe=True)
        pipeline = ScriptGenerationPipeline(
            moderator=mock_mod,
            template_engine=mock_tpl_engine,
            llm_generator=mock_llm,
        )
        sess = ChatSessionState(
            session_id="s-dual-track",
            user_id="u-dual",
            category="wildlife",
            duration_min=5,
            initial_prompt="Coral Reef Recovery",
            selected_template_id=None,
        )
        early_fact = (
            "According to a 2023 NOAA marine survey, coral reef cover in the protected "
            "atoll recovered by 42 percent between 2018 and 2023."
        )
        append_to_context_window(
            sess,
            early_fact,
            turn=1,
            source="chat",
            max_chars=520,
            max_entries=3,
            keep_recent=1,
            max_summary_chars=220,
        )
        append_to_context_window(
            sess,
            "Uploaded reference file: field_notes.pdf",
            turn=2,
            source="file_summary",
            max_chars=520,
            max_entries=3,
            keep_recent=1,
            max_summary_chars=220,
        )
        append_to_context_window(
            sess,
            "Please make the opening more energetic and keep transitions concise for students.",
            turn=3,
            source="chat",
            max_chars=520,
            max_entries=3,
            keep_recent=1,
            max_summary_chars=220,
        )
        append_to_context_window(
            sess,
            (
                "Researchers at James Cook University recorded 180 native fish species returning "
                "within 24 months after nursery restoration began in 2021."
            ),
            turn=4,
            source="chat",
            max_chars=520,
            max_entries=3,
            keep_recent=1,
            max_summary_chars=220,
        )
        assert sess.compaction_count >= 1
        assert sess.compacted_summary
        # Track 2 keeps verbatim chat notes (excluding file_summary)
        assert any("42 percent" in n for n in sess.user_notes)
        assert all("Uploaded reference file:" not in n for n in sess.user_notes)

        # Mutate compacted_summary to a distinctive marker to prove it never enters citation chunks
        sess.compacted_summary = (
            "- COMPACTED_SUMMARY_MARKER_2025: 99 percent summary paraphrase for prompt only"
        )
        pipeline.session_store.put(sess)
        try:
            pipeline.run(
                ScriptGenerationRequest(
                    topic="Coral Reef Recovery",
                    category="free",
                    duration_min=5,
                    session_id="s-dual-track",
                    user_id="u-dual",
                )
            )
            kwargs = mock_llm.generate_free_topic_script.call_args.kwargs
            # Track 1: LLM chat_context receives the bounded summary + recent context window
            assert "[Session Summary]" in kwargs["chat_context"]
            assert "COMPACTED_SUMMARY_MARKER_2025" in kwargs["chat_context"]
            # Track 2: citation chunks contain both raw verbatim facts, never summary or instruction
            passed_chunks = kwargs["chunks"] or []
            chunk_blob = "\n".join(c.content for c in passed_chunks)
            assert "42 percent" in chunk_blob
            assert "180 native fish species" in chunk_blob
            assert "COMPACTED_SUMMARY_MARKER_2025" not in chunk_blob
            assert "more energetic" not in chunk_blob
            assert "Uploaded reference file:" not in chunk_blob
        finally:
            pipeline.session_store.delete("s-dual-track", user_id="u-dual")


class TestContinuousGroqQA:
    def test_turn1_question_uses_groq_and_fallback_with_bold_keys(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"reply_message": "Who is your **target audience** and what '
                        '**real-world examples** should we include?", '
                        '"missing_items": ["target audience", "real-world examples"]}'
                    )
                )
            )
        ]
        mock_resp.usage = MagicMock(total_tokens=110)
        mock_client.chat.completions.create.return_value = mock_resp

        reply, missing = build_turn1_question(
            topic="Solar Microgrids",
            category="IT",
            duration_min=5,
            is_free_topic=True,
            client=mock_client,
            limiter=TokenBucketLimiter(),
        )
        assert "**target audience**" in reply
        assert "target audience" in missing

        # Fallback when client is None
        fb_reply, fb_missing = build_turn1_question(
            topic="Solar Microgrids",
            is_free_topic=True,
            client=None,
        )
        assert "**" in fb_reply
        assert len(fb_missing) >= 1

    def test_evaluate_and_build_followup_json_and_fallback(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"sufficient": false, '
                        '"missing_items": ["concrete case study"], '
                        '"reply_message": "Thanks! Could you share one **concrete case study**?"}'
                    )
                )
            )
        ]
        mock_resp.usage = MagicMock(total_tokens=140)
        mock_client.chat.completions.create.return_value = mock_resp

        decision = evaluate_and_build_followup(
            topic="Urban Forests",
            is_free_topic=True,
            compacted_summary="- Audience: city planners",
            context_entries=[
                ContextEntry(turn=1, source="chat", text="Focus on heat island reduction.")
            ],
            latest_user_answer="Focus on heat island reduction.",
            client=mock_client,
            limiter=TokenBucketLimiter(),
        )
        assert decision.used_llm is True
        assert decision.sufficient is False
        assert decision.missing_items == ["concrete case study"]
        assert "**concrete case study**" in decision.reply_message

        # Verify bounded context was passed to Groq
        sent_user = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "city planners" in sent_user
        assert "[Turn 1 | chat]" in sent_user

        # Verify previous question memory & non-checklist template coaching hints
        evaluate_and_build_followup(
            topic="Tasmanian Tiger",
            is_free_topic=False,
            context_entries=[
                ContextEntry(
                    turn=1,
                    source="chat",
                    text="I want a deep tone focusing on extinction.",
                )
            ],
            latest_user_answer="I want a deep tone focusing on extinction.",
            last_question="Who is your **target audience** for this talk?",
            missing_entities=["entity_audience_type"],
            missing_groups=[GROUP_MAIN, GROUP_EVIDENCE, GROUP_COUNTER],
            coverage_ratio=0.0,
            client=mock_client,
            limiter=TokenBucketLimiter(),
        )
        sent_sys = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        sent_tpl_user = mock_client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ]
        assert "Your previous question (do not repeat):" in sent_tpl_user
        assert "Who is your **target audience** for this talk?" in sent_tpl_user
        assert "Template slot coverage: 0%" not in sent_tpl_user
        assert GROUP_COUNTER not in sent_tpl_user  # capped at <=2 optional hints, never all 3
        assert "acknowledging" in sent_sys.lower()

        # Verify latest_user_answer is not duplicated when already in context_window,
        # and an 18,000-char paste stays well inside the 8,000 TPM budget
        session = ChatSessionState(
            session_id="s-big",
            user_id="u1",
            category="free",
            duration_min=5,
            topic="Deep Sea Vent Ecosystems",
        )
        huge_msg = ("Hydrothermal vent sulfur bacteria sustain giant tube worms. " * 290).strip()
        assert len(huge_msg) > 15_000
        append_to_context_window(session, huge_msg, turn=2, source="chat")

        big_decision = evaluate_and_build_followup(
            topic="Deep Sea Vent Ecosystems",
            is_free_topic=True,
            compacted_summary=session.compacted_summary,
            context_entries=session.context_window,
            latest_user_answer=huge_msg,
            client=mock_client,
            limiter=TokenBucketLimiter(),
        )
        assert big_decision.used_llm is True
        big_prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "(see [Turn 2 | chat] above)" in big_prompt
        assert len(big_prompt) < 5_200  # bounded (~1,500 tok), never 18,000+ raw chars

        # Malformed JSON falls back deterministically without raising
        bad_client = MagicMock()
        bad_resp = MagicMock()
        bad_resp.choices = [MagicMock(message=MagicMock(content="not-json"))]
        bad_resp.usage = MagicMock(total_tokens=50)
        bad_client.chat.completions.create.return_value = bad_resp

        fb_decision = evaluate_and_build_followup(
            topic="Urban Forests",
            is_free_topic=True,
            latest_user_answer="Short note",
            client=bad_client,
            limiter=TokenBucketLimiter(),
        )
        assert fb_decision.used_llm is False
        assert fb_decision.sufficient is False
        assert "**" in fb_decision.reply_message

    def test_compaction_and_turn1_reject_truncated_or_malformed_json(self) -> None:
        bad_compact_client = MagicMock()
        bad_compact_resp = MagicMock()
        bad_compact_resp.choices = [
            MagicMock(message=MagicMock(content='{"summary": "unterminated'))
        ]
        bad_compact_resp.usage = MagicMock(total_tokens=40)
        bad_compact_client.chat.completions.create.return_value = bad_compact_resp

        summary, used_llm = compact_context_entries(
            "",
            [ContextEntry(turn=1, source="chat", text="42% efficiency gain in Berlin.")],
            topic="Transit",
            client=bad_compact_client,
            limiter=TokenBucketLimiter(),
        )
        assert used_llm is False
        assert "42% efficiency gain in Berlin" in summary
        assert '{"summary"' not in summary

        bad_turn1_client = MagicMock()
        bad_turn1_resp = MagicMock()
        bad_turn1_resp.choices = [
            MagicMock(message=MagicMock(content="{malformed json truncated"))
        ]
        bad_turn1_resp.usage = MagicMock(total_tokens=40)
        bad_turn1_client.chat.completions.create.return_value = bad_turn1_resp

        reply, missing = build_turn1_question(
            topic="Transit",
            is_free_topic=True,
            client=bad_turn1_client,
            limiter=TokenBucketLimiter(),
        )
        assert "{malformed" not in reply
        assert "**" in reply
        assert len(missing) >= 1

    def test_evaluate_and_build_followup_parses_string_sufficient_flags(self) -> None:
        for raw_flag, expected in [
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("", False),
            ("true", True),
            ("1", True),
            ("yes", True),
            ("unrecognized", False),
        ]:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [
                MagicMock(
                    message=MagicMock(
                        content=(
                            f'{{"sufficient": "{raw_flag}", '
                            '"missing_items": ["audience"], '
                            '"reply_message": "Tell me about your **audience**."}'
                        )
                    )
                )
            ]
            mock_resp.usage = MagicMock(total_tokens=80)
            mock_client.chat.completions.create.return_value = mock_resp

            decision = evaluate_and_build_followup(
                topic="Transit",
                is_free_topic=True,
                latest_user_answer="Short note",
                client=mock_client,
                limiter=TokenBucketLimiter(),
            )
            assert decision.sufficient is expected, f"Failed for {raw_flag!r}"

    def test_pipeline_preserves_passed_empty_chat_session_store(self) -> None:
        from src.text_processing.chat_session import chat_session_store

        isolated_store = ChatSessionStore()
        assert len(isolated_store) == 0
        pipeline = ScriptGenerationPipeline(
            template_store=TemplateStore(Path("nonexistent")),
            session_store=isolated_store,
        )
        assert pipeline.session_store is isolated_store
        assert pipeline.session_store is not chat_session_store


class TestStepAndEtaTelemetry:
    def test_turn_step_tracker_adds_10s_buffer_and_zeros_remaining_on_finish(self) -> None:
        tracker = TurnStepTracker(
            [
                "validating_input",
                "moderating",
                "updating_context",
                "compacting_context",
                "analyzing_with_llm",
            ]
        )
        tracker.start("validating_input")
        active = tracker.to_telemetry()
        assert active["eta_buffer_s"] == ETA_BUFFER_S == 10
        assert active["estimated_total_s"] > 10.0
        assert active["estimated_remaining_s"] > 10.0

        tracker.skip("compacting_context")
        tracker.finish()
        done = tracker.to_telemetry()
        assert done["stage"] == "completed"
        assert done["progress"] == 100
        assert done["estimated_remaining_s"] == 0.0
        assert any(
            s["key"] == "compacting_context" and s["state"] == "skipped"
            for s in done["steps"]
        )

    def test_script_job_state_exposes_steps_and_10s_buffered_eta(self) -> None:
        job = ScriptJobState(job_id="j1", user_id="u1")
        payload = job.to_dict()
        assert payload["eta_buffer_s"] == 10
        assert payload["estimated_total_s"] > 10.0
        assert payload["estimated_remaining_s"] == payload["estimated_total_s"]
        assert [s["key"] for s in payload["steps"]] == [
            "validating_input",
            "extracting",
            "moderating",
            "generating",
            "validating_output",
        ]


# ---------- Turn 1 Smart Generate (Contract C) ----------

_READY_HINT = "You can also generate the script right now."


def _turn1_client(payload: object) -> MagicMock:
    """A Groq mock answering every call with `payload` (a dict, or raw text)."""
    client = MagicMock()
    response = MagicMock()
    content = payload if isinstance(payload, str) else json.dumps(payload)
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = MagicMock(total_tokens=90)
    client.chat.completions.create.return_value = response
    return client


def _asking_payload(**extra: object) -> dict[str, object]:
    return {
        "reply_message": "Who is your **target audience**?",
        "missing_items": ["target audience"],
        **extra,
    }


def _free_decision(prompt: str, **kwargs: object):
    kwargs.setdefault("limiter", TokenBucketLimiter())
    return build_turn1_decision(
        topic=prompt or "Custom Speech", is_free_topic=True, initial_prompt=prompt, **kwargs
    )


def _template_decision(**kwargs: object):
    kwargs.setdefault("limiter", TokenBucketLimiter())
    return build_turn1_decision(topic="Keystone Species", **kwargs)


def _sent_prompts(client: MagicMock) -> tuple[str, str]:
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    return messages[0]["content"], messages[1]["content"]


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("help me write a speech", False),
        ("write a 5 minute presentation", False),
        ("for my class", False),
        ("tạo bài thuyết trình giúp tôi", False),
        (unicodedata.normalize("NFD", "viết bài nói giúp tôi"), False),
        ("viết bài nói giúp tôi", False),
        ("5 phút cho sinh viên", False),
        ("make me a 5-minute speech for my college class", False),
        ("a 10-min talk for my college class", False),
        ("Tell me what to say", False),
        ("I need a speech for tomorrow", False),
        ("bạn có thể giúp mình viết bài được không", False),
        ("HELP ME, write a SPEECH!", False),
        ("Football", False),
        ("", False),
        ("Coral reefs", True),
        ("Climate change in the Mekong Delta", True),
        ("help me write a speech about ocean plastic pollution", True),
        ("Biến đổi khí hậu ở đồng bằng sông Cửu Long", True),
    ],
)
def test_free_topic_is_identifiable_from_the_prompt(prompt: str, expected: bool) -> None:
    assert is_free_topic_identifiable(prompt, [], []) is expected


def test_free_topic_is_identifiable_from_a_file_or_chunks() -> None:
    chunk = DocumentChunk(chunk_id=1, heading="Notes", page=1, content="Reef survey.")

    assert is_free_topic_identifiable("", ["notes.txt"], []) is True
    assert is_free_topic_identifiable("help me", [], [chunk]) is True


def test_turn1_ready_words_come_from_the_script_guard_section() -> None:
    configured = CONSTANTS["script_guard"]["free_topic_turn1_ready_words"]

    assert FREE_TOPIC_TURN1_READY_WORDS == configured == 40


def test_turn1_ready_template_replies_without_calling_the_llm() -> None:
    client = _turn1_client(_asking_payload())

    decision = _template_decision(coverage_ratio=0.7, missing_entities=[], client=client)

    assert decision.can_generate is True
    assert decision.topic_clear is True
    assert decision.used_llm is False
    assert decision.missing_items == []
    assert decision.reply_message == (
        "You already shared enough detail on **Keystone Species** to draft the speech. "
        "You can generate right now, or add any **extra examples** or "
        "**tone preferences** first."
    )
    assert client.mock_calls == []


@pytest.mark.parametrize(
    ("coverage_ratio", "missing_entities"),
    [(0.69, []), (1.0, ["entity_audience_type"])],
)
def test_turn1_incomplete_template_never_allows_generate(
    coverage_ratio: float, missing_entities: list[str]
) -> None:
    client = _turn1_client(_asking_payload(sufficient=True))

    decision = _template_decision(
        coverage_ratio=coverage_ratio, missing_entities=missing_entities, client=client
    )

    assert decision.can_generate is False
    assert decision.topic_clear is True
    assert decision.used_llm is True
    assert decision.reply_message == "Who is your **target audience**?"
    assert client.chat.completions.create.call_count == 1
    system_prompt, user_prompt = _sent_prompts(client)
    assert "Never tell the user to click Generate yet." in system_prompt
    assert "Mode: Template-guided speech" in user_prompt


def test_turn1_template_without_argument_slots_is_ready() -> None:
    document = TemplateDocument(
        metadata=TopicMetadata(
            template_id="sports/no_slots",
            category_slug="sports",
            category="Sports",
            topic="Fair Play",
            topic_slug="no_slots",
            duration_min=5,
        ),
        body="Welcome everyone. Thank you.",
        file_path="data/templates/sports/no_slots.md",
    )
    coverage_ratio, missing_entities, missing_groups = analyze_slot_coverage(
        template_document=document, chunks=[], chunk_embeddings=None, retriever=None
    )

    decision = _template_decision(
        coverage_ratio=coverage_ratio,
        missing_entities=missing_entities,
        missing_groups=missing_groups,
    )

    assert decision.can_generate is True


def test_turn1_unclear_free_topic_asks_for_the_topic_without_the_llm() -> None:
    client = _turn1_client(_asking_payload(sufficient=True))

    decision = _free_decision("help me write a speech", client=client)

    assert decision.topic_clear is False
    assert decision.can_generate is False
    assert decision.missing_items == ["speech topic"]
    assert "**specific topic**" in decision.reply_message
    assert "generate" not in decision.reply_message.lower()
    assert client.mock_calls == []


def test_turn1_clear_short_free_topic_keeps_asking() -> None:
    client = _turn1_client(_asking_payload(sufficient=False, topic_clear=False))

    decision = _free_decision("Coral reefs", client=client)

    assert decision.topic_clear is True
    assert decision.can_generate is False
    assert decision.used_llm is True
    assert decision.missing_items == ["target audience"]
    assert decision.reply_message == "Who is your **target audience**?"
    assert client.chat.completions.create.call_count == 1
    system_prompt, user_prompt = _sent_prompts(client)
    assert '"sufficient": bool' in system_prompt
    assert "otherwise never tell the user to click Generate" in system_prompt
    assert "Mode: Free-topic speech" in user_prompt


@pytest.mark.parametrize(
    ("words", "expected"),
    [(FREE_TOPIC_TURN1_READY_WORDS - 1, False), (FREE_TOPIC_TURN1_READY_WORDS, True)],
)
def test_turn1_free_topic_word_threshold_counts_words_with_a_letter(
    words: int, expected: bool
) -> None:
    prompt = " ".join(["coral"] * words) + " 2024 - 35"
    client = _turn1_client(_asking_payload(sufficient=False))

    decision = _free_decision(prompt, client=client)

    assert decision.can_generate is expected
    assert decision.reply_message.endswith(_READY_HINT) is expected


@pytest.mark.parametrize(
    "material",
    [
        {"files_loaded": ["notes.txt"]},
        {"chunks": [DocumentChunk(chunk_id=1, heading="Notes", page=1, content="Reefs.")]},
    ],
)
def test_turn1_free_topic_with_material_may_generate_and_says_so(
    material: dict[str, object],
) -> None:
    client = _turn1_client(_asking_payload(sufficient=False))

    decision = _free_decision("", client=client, **material)

    assert decision.can_generate is True
    assert decision.reply_message == f"Who is your **target audience**? {_READY_HINT}"
    system_prompt, _ = _sent_prompts(client)
    assert "never tell the user" not in system_prompt.lower()


def test_turn1_llm_sufficient_true_allows_generate_without_repeating_the_hint() -> None:
    reply = "We are set on **coral reefs**. Generate when ready."
    client = _turn1_client({"sufficient": True, "missing_items": [], "reply_message": reply})

    decision = _free_decision("Coral reefs", client=client)

    assert decision.can_generate is True
    assert decision.missing_items == []
    assert decision.reply_message == reply


@pytest.mark.parametrize("flag", ["true", 1, None])
def test_turn1_only_a_boolean_sufficient_flag_counts(flag: object) -> None:
    client = _turn1_client(_asking_payload(sufficient=flag))

    assert _free_decision("Coral reefs", client=client).can_generate is False


def _failing_clients() -> list[MagicMock | None]:
    raising = MagicMock()
    raising.chat.completions.create.side_effect = RuntimeError("groq down")
    return [
        None,
        raising,
        _turn1_client("{broken json"),
        _turn1_client("[]"),
        _turn1_client({"sufficient": True, "reply_message": "  "}),
    ]


@pytest.mark.parametrize("client", _failing_clients())
def test_turn1_llm_failure_falls_back_to_the_deterministic_rule(
    client: MagicMock | None,
) -> None:
    short = _free_decision("Coral reefs", client=client)
    with_file = _free_decision("", files_loaded=["notes.txt"], client=client)
    template = _template_decision(missing_entities=["entity_audience_type"], client=client)

    assert (short.can_generate, short.used_llm) == (False, False)
    assert "**" in short.reply_message
    assert "generate" not in short.reply_message.lower()
    assert (with_file.can_generate, with_file.used_llm) == (True, False)
    assert with_file.missing_items == []
    assert "generate it right now" in with_file.reply_message
    assert (template.can_generate, template.used_llm) == (False, False)
    assert "**audience type**" in template.reply_message


def test_turn1_exhausted_llm_budget_falls_back_without_a_call() -> None:
    limiter = MagicMock()
    limiter.wait_time_s.return_value = 3600.0
    client = _turn1_client(_asking_payload(sufficient=True))

    decision = _free_decision("Coral reefs", client=client, limiter=limiter)

    assert (decision.can_generate, decision.used_llm) == (False, False)
    assert client.mock_calls == []
