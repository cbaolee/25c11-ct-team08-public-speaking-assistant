"""Unit tests for Hybrid Source-Material vs. Casual/Instruction Chat Classifier."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.text_processing.chat_session import ChatSessionState, ChatSessionStore
from src.text_processing.contracts import (
    DocumentChunk,
    GeneratedScript,
    ScriptGenerationRequest,
)
from src.text_processing.moderation import ContentModerator
from src.text_processing.pipeline import ScriptGenerationPipeline, _build_chat_note_chunks
from src.text_processing.retrieval import SemanticRetriever, align_script_citations
from src.text_processing.source_classifier import (
    classify_user_message,
    extract_citable_source_text,
)


class TestClassifyUserMessage:
    """Tests covering clearly casual, clearly editing, clearly citable, and borderline inputs."""

    @pytest.mark.parametrize(
        "msg",
        [
            "",
            "   ",
            "hi",
            "Hello there!",
            "thanks",
            "Thank you so much!",
            "ok sounds good",
            "looks great",
            "I'm happy",
            "I am really happy today!",
            "I feel a bit nervous about giving this speech tomorrow.",
            "That makes me so happy!",
            "Can you help me with this?",
            "What do you think?",
            "I don't know what to say",
            "done",
            "generate",
        ],
    )
    def test_clearly_casual_messages_are_never_citable(self, msg: str) -> None:
        res = classify_user_message(msg)
        assert res.citable is False
        assert res.category == "casual_chat"
        assert extract_citable_source_text(msg) is None

    @pytest.mark.parametrize(
        "msg",
        [
            "make it shorter",
            "Please make the opening more dramatic and punchy.",
            "Use a warmer, more conversational tone.",
            "Shorten the conclusion and remove technical jargon.",
            "Add a humorous hook at the beginning.",
            "Focus more on university students in the audience.",
            "Change the style to sound more formal.",
            "Too wordy",
            "Write a fresh variation of this speech (attempt #2): vary wording and hooks.",
        ],
    )
    def test_editing_instructions_are_never_citable(self, msg: str) -> None:
        res = classify_user_message(msg)
        assert res.citable is False
        assert res.category == "editing_instruction"
        assert extract_citable_source_text(msg) is None

    @pytest.mark.parametrize(
        "msg",
        [
            "According to the 2023 WHO report, depression affects 5% of adults worldwide.",
            (
                "Overview\nThe Tasmanian tiger was a dog-like marsupial distinguished "
                "by dark stripes across its back, a stiff tail, and a wide jaw gape."
            ),
            (
                "Historically found across:\nTasmania\nMainland Australia\n"
                "Papua New Guinea\nIt survived longest in Tasmania due to "
                "isolation from dingoes."
            ),
            "After Copenhagen added 150 km of protected bike lanes, commuter injuries fell by 28%.",
            (
                "Hydrothermal vent ecosystems survive without sunlight because chemosynthetic "
                "bacteria convert hydrogen sulfide into organic nutrients."
            ),
            "The Saola was discovered in 1992 in Vu Quang Nature Reserve in Vietnam.",
            'A 2021 clinical trial ( Patel et al., 2021 ) measured a 34% drop in recovery time.',
        ],
    )
    def test_clearly_citable_source_material_is_accepted(self, msg: str) -> None:
        res = classify_user_message(msg)
        assert res.citable is True
        assert res.category == "source_material"
        extracted = extract_citable_source_text(msg)
        assert extracted is not None
        assert len(extracted.split()) >= 4

    def test_borderline_happy_thing_casual_remark_rejected(self) -> None:
        """Regression guard for the prompt's exact failure case ('happy thing' <- 'I'm happy')."""
        for remark in (
            "I'm happy",
            "I am happy about this happy thing",
            "Talking about happy things makes me feel great!",
        ):
            decision = classify_user_message(remark)
            assert decision.citable is False
            assert extract_citable_source_text(remark) is None

        chunks = _build_chat_note_chunks(["I'm happy", "I feel happy today!", "make it shorter"])
        assert chunks == []

    def test_borderline_semantic_prototype_fail_closed_margin(self, monkeypatch) -> None:
        """Verify Layer 2 rejects borderline text when source margin < semantic_margin."""

        class FakeEmbeddingModel:
            pass

        fake_model = FakeEmbeddingModel()
        retriever = SemanticRetriever()
        monkeypatch.setattr(SemanticRetriever, "get_model", classmethod(lambda cls: fake_model))

        # Controlled embeddings: prototypes vs borderline query with narrow margin (0.02 < 0.05)
        src_keys = (
            "According to",
            "species is",
            "Empirical",
            "Historically",
            "Researchers",
            "Case study",
            "mechanism",
            "Critics",
            "Key findings",
            "Economic",
        )
        ins_keys = (
            "shorter",
            "tone",
            "hook",
            "Rewrite",
            "Focus",
            "punchier",
            "formal",
            "simplify",
        )
        cas_keys = ("happy", "Thank", "Hello", "Okay", "nervous", "Awesome", "not sure", "Great")

        def _fake_encode(_model: object, texts: list[str]) -> np.ndarray:
            vecs = []
            for t in texts:
                if any(k in t for k in src_keys):
                    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
                elif any(k in t for k in ins_keys):
                    v = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                elif any(k in t for k in cas_keys):
                    v = np.array([0.0, 0.0, 1.0], dtype=np.float32)
                else:
                    # Borderline query almost equidistant between source (0.71) and casual (0.70)
                    v = np.array([0.71, 0.10, 0.70], dtype=np.float32)
                v = v / np.linalg.norm(v)
                vecs.append(v)
            return np.array(vecs, dtype=np.float32)

        monkeypatch.setattr(SemanticRetriever, "_encode", staticmethod(_fake_encode))

        res = classify_user_message(
            "People often share personal opinions when discussing everyday habits together.",
            retriever=retriever,
            semantic_min_score=0.38,
            semantic_margin=0.05,
        )
        assert res.layer == "semantic"
        assert res.citable is False

    def test_mixed_message_sentence_level_filtering(self) -> None:
        mixed_1 = (
            "Thanks! Make it shorter and more dramatic. "
            "Also mention that the Saola was discovered in 1992 in Vu Quang Nature Reserve."
        )
        extracted_1 = extract_citable_source_text(mixed_1)
        assert extracted_1 is not None
        assert "Thanks" not in extracted_1
        assert "Make it shorter" not in extracted_1
        assert "Saola was discovered in 1992 in Vu Quang Nature Reserve" in extracted_1

        mixed_2 = (
            "Make it shorter, and include that global coral reef cover declined by 50% since 1950."
        )
        extracted_2 = extract_citable_source_text(mixed_2)
        assert extracted_2 is not None
        assert "Make it shorter" not in extracted_2
        assert "50%" in extracted_2
        assert "1950" in extracted_2

        # Comma-less short mixed sentence keeps the factual clause and strips imperative prefix
        mixed_no_comma = "Make it shorter and mention that Saola was found in 1992."
        extracted_3 = extract_citable_source_text(mixed_no_comma)
        assert extracted_3 is not None
        assert "Make it shorter" not in extracted_3
        assert "Saola was found in 1992" in extracted_3

    def test_multiline_casual_and_numeric_edit_instructions_rejected(self) -> None:
        multiline_casual = "My thoughts\nI like dogs\nVery cute"
        assert extract_citable_source_text(multiline_casual) is None

        numeric_edit = classify_user_message("Make it 5 minutes long")
        assert numeric_edit.citable is False
        assert numeric_edit.category == "editing_instruction"

    def test_duplicate_chat_notes_are_deduplicated(self) -> None:
        note = "According to the 2023 WHO report, depression affects 5% of adults worldwide."
        chunks = _build_chat_note_chunks([note, "  " + note + "  ", "thanks!"])
        assert len(chunks) == 1
        assert chunks[0].heading == "Chat note #1"


class TestPipelineChatCitationFiltering:
    """End-to-end check that pipeline passes instructions to LLM but only cites source facts."""

    def test_pipeline_keeps_casual_and_editing_in_context_but_never_cites_them(self) -> None:
        session_store = ChatSessionStore()
        sid = "sess-casual-guard"
        doc_chunk = DocumentChunk(
            chunk_id=1,
            heading="Field Survey",
            page=2,
            content="Camera traps recorded 14 snow leopards at 4,200 meters elevation in 2022.",
        )
        session = ChatSessionState(
            session_id=sid,
            user_id="u1",
            category="free",
            duration_min=5,
            initial_prompt="I'm happy today, please write a speech about snow leopards!",
            user_notes=[
                "I'm happy!",
                "thanks so much",
                "make it shorter and warmer",
            ],
            chunks=[doc_chunk],
        )
        session_store.put(session)

        captured_chunks: list[DocumentChunk] = []
        captured_chat_ctx: list[str | None] = []

        mock_gen = MagicMock()

        def _fake_gen(
            topic: str,
            duration_min: int = 5,
            chunks: list[DocumentChunk] | None = None,
            greeting: str | None = None,
            user_feedback: str | None = None,
            chat_context: str | None = None,
        ) -> GeneratedScript:
            captured_chunks.extend(chunks or [])
            captured_chat_ctx.append(chat_context)
            script_text = (
                "It is a happy thing to feel happy today as we begin our talk.\n\n"
                "Camera traps recorded 14 snow leopards at 4,200 meters elevation in 2022. "
                + " ".join(["conservation"] * 580)
            )
            cites = align_script_citations(script_text, list(chunks or []))
            return GeneratedScript(
                script=script_text,
                word_count=len(script_text.split()),
                duration_min=duration_min,
                source="llm",
                template_id=None,
                models_used=["mock"],
                citations=cites,
            )

        mock_gen.generate_free_topic_script.side_effect = _fake_gen

        pipeline = ScriptGenerationPipeline(
            moderator=ContentModerator(enable_llama_guard=False),
            llm_generator=mock_gen,
            session_store=session_store,
        )
        res = pipeline.run(
            ScriptGenerationRequest(
                topic="Snow Leopard Conservation",
                category="free",
                duration_min=5,
                user_id="u1",
                session_id=sid,
                user_feedback="Keep the ending brief please.",
            )
        )

        # 1. Editing/casual messages WERE forwarded in chat_context so LLM obeys instructions
        assert captured_chat_ctx[0] is not None
        assert "make it shorter" in captured_chat_ctx[0]
        assert "Keep the ending brief" in captured_chat_ctx[0]

        # 2. ZERO chat-note chunks were created from casual/editing messages — only the PDF chunk!
        assert len(captured_chunks) == 1
        assert captured_chunks[0].heading == "Field Survey"
        assert captured_chunks[0].page == 2

        # 3. Paragraph 1 ("happy thing to feel happy today") is UNCITED, Paragraph 2 is CITED to p.2
        assert res.citations[0].status == "uncited"
        assert res.citations[1].status == "cited"
        assert res.citations[1].page == 2
        assert res.citations[1].heading == "Field Survey"
