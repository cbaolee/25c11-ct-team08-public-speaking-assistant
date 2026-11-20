"""Unit tests for Phase 1: ChatSessionState, ChatSessionStore, and minimal-token gathering."""

from __future__ import annotations

import re
import sys
import threading
import time
import types
import zlib
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.text_processing.chat_session import (
    GROUP_COUNTER,
    GROUP_EVIDENCE,
    GROUP_MAIN,
    READY_MESSAGE,
    ChatSessionState,
    ChatSessionStore,
    analyze_slot_coverage,
    build_followup_reply,
    check_ready_to_generate,
    classify_argument_slot,
    group_uncovered_slots,
    ingest_upload_file,
)
from src.text_processing.contracts import (
    DocumentChunk,
    TemplateDocument,
    TopicMetadata,
)
from src.text_processing.parser import DocumentParserError
from src.text_processing.retrieval import SemanticRetriever


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

    def test_layer_2_hard_interaction_cap(self) -> None:
        # Even with 0 coverage and missing entities, 2 turns triggers ready
        is_ready = check_ready_to_generate(
            selected_template_id="sports/sample",
            missing_entities=["entity_target", "entity_name"],
            coverage_ratio=0.1,
            gather_turns=2,
        )
        assert is_ready is True

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

    def test_gather_turns_cap_returns_ready_message(self) -> None:
        reply = build_followup_reply(
            topic="Marathon Pacing",
            ready_to_generate=False,
            missing_entities=["entity_name"],
            missing_groups=[GROUP_MAIN],
            gather_turns=2,
        )
        assert reply == READY_MESSAGE

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


