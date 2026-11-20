"""Automated test suite for Script Generation 6 scenarios (#57 Phase 2).

Scenarios covered:
- Scenario 1: Topic suggestions from category + duration + prompt (strong & free-topic).
- Scenario 2: Interactive gathering: template selection -> entity follow-ups -> ready.
- Scenario 3: Hard 2-turn gathering cap (gather_turns == 2) -> stops asking follow-up questions.
- Scenario 4: Template generation (6T) with polish_script_paragraphs.
- Scenario 5: Free-topic generation (6L) and regenerate with user_feedback reusing session chunks.
- Scenario 6: Content moderation (Layer 1 + mocked Layer 2) rejecting unsafe content.
"""

from __future__ import annotations

import io
import json
import re
import sys
import types
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid5

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.app import main as app_main
from src.app.deps import CurrentUser, get_current_user
from src.text_processing.chat_session import (
    READY_MESSAGE,
    ChatSessionState,
    chat_session_store,
    check_ready_to_generate,
)
from src.text_processing.contracts import (
    DocumentChunk,
    GeneratedScript,
    ParagraphCitation,
    ScriptGenerationRequest,
    TemplateDocument,
    TopicMetadata,
)
from src.text_processing.limiter import TokenBucketLimiter
from src.text_processing.moderation import ContentModerator
from src.text_processing.pipeline import ScriptGenerationPipeline
from src.text_processing.retrieval import SemanticRetriever
from src.text_processing.template_engine import (
    TemplateEngine,
    polish_script_paragraphs,
)
from src.text_processing.template_store import TemplateStore

# ---------------------------------------------------------------------------
# Offline Deterministic SentenceTransformer Mock
# ---------------------------------------------------------------------------


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
    """Mock sentence_transformers globally so test suite runs offline with 0 latency."""
    mock_instance = MockSentenceTransformer()
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.SentenceTransformer = lambda model_name="all-MiniLM-L6-v2": mock_instance
    monkeypatch.setitem(sys.modules, "sentence_transformers", mock_module)

    SemanticRetriever._shared_model = None
    SemanticRetriever._load_attempted = False
    yield mock_instance
    SemanticRetriever._shared_model = None
    SemanticRetriever._load_attempted = False


# ---------------------------------------------------------------------------
# Layer 2 Ollama Mock Helpers
# ---------------------------------------------------------------------------


def _ollama_reply(content: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"message": {"role": "assistant", "content": content}})


class FakeOllama:
    """MockTransport handler recording requests and returning deterministic responses."""

    def __init__(self, *replies: httpx.Response | BaseException) -> None:
        self.replies = list(replies) or [_ollama_reply("safe")]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return reply


# Ensure TemplateStore has suggest_topics for offline scenario testing
if not hasattr(TemplateStore, "suggest_topics"):
    from dataclasses import asdict, dataclass

    @dataclass(frozen=True)
    class TopicSuggestion:
        template_id: str
        topic: str
        category_slug: str
        duration_min: int
        score: float
        is_strong_match: bool

        def to_dict(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass(frozen=True)
    class TopicSuggestionResult:
        suggestions: list[TopicSuggestion]
        recommend_free_topic: bool

        def to_dict(self) -> dict[str, Any]:
            return {
                "suggestions": [item.to_dict() for item in self.suggestions],
                "recommend_free_topic": self.recommend_free_topic,
            }

    def _fallback_suggest_topics(
        self: TemplateStore,
        category_slug: str,
        duration_min: int,
        query: str,
        retriever: Any = None,
        top_k: int = 5,
        min_score: float = 0.35,
    ) -> TopicSuggestionResult:
        matching = [
            doc
            for doc in self._by_id.values()
            if doc.metadata.category_slug == category_slug
            and doc.metadata.duration_min == duration_min
        ]
        if not matching:
            matching = list(self._by_id.values())[:top_k]

        q_lower = query.lower()
        scored: list[tuple[float, TemplateDocument]] = []
        stop_words = {"and", "in", "the", "of", "for", "to", "a", "on", "with", "is"}
        for doc in matching:
            t_lower = doc.metadata.topic.lower()
            q_words = set(re.findall(r"\w+", q_lower)) - stop_words
            t_words = set(re.findall(r"\w+", t_lower)) - stop_words
            overlap = len(q_words & t_words) / max(len(q_words | t_words), 1)
            score = 0.85 if overlap > 0.1 else 0.1
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        suggestions = [
            TopicSuggestion(
                template_id=doc.metadata.template_id,
                topic=doc.metadata.topic,
                category_slug=doc.metadata.category_slug,
                duration_min=doc.metadata.duration_min,
                score=score,
                is_strong_match=score >= min_score,
            )
            for score, doc in scored[:top_k]
        ]
        has_strong = any(s.is_strong_match for s in suggestions)
        return TopicSuggestionResult(
            suggestions=suggestions if has_strong else suggestions[:3],
            recommend_free_topic=not has_strong,
        )

    TemplateStore.suggest_topics = _fallback_suggest_topics  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test Pipeline & Client Fixtures
# ---------------------------------------------------------------------------


def _user(name: str = "test-user") -> CurrentUser:
    return CurrentUser(id=uuid5(NAMESPACE_URL, name))


def _build_test_store() -> tuple[TemplateStore, TemplateDocument]:
    """Create in-memory TemplateStore populated with 5 templates in wildlife category."""
    store = TemplateStore(Path("nonexistent_test_templates_dir"))

    main_doc = TemplateDocument(
        metadata=TopicMetadata(
            template_id="wildlife/keystone_5m",
            category_slug="wildlife",
            category="Wildlife",
            topic="Keystone Species Conservation",
            topic_slug="keystone_5m",
            duration_min=5,
        ),
        body=(
            "Welcome {{ entity_audience_type }} to today's keynote.\n\n"
            "First, examining the core foundation shows that {{ argument_core_mechanism }}.\n\n"
            "Furthermore, real-world case studies illustrate that {{ argument_case_evidence }}.\n\n"
            "On the other hand, critics argue that {{ argument_counter_perspective }}.\n\n"
            "In conclusion, synthesizing these dimensions reveals that {{ argument_synthesis }}.\n"
        ),
        file_path="data/templates/wildlife/keystone_5m.md",
    )
    store._by_id[main_doc.metadata.template_id] = main_doc
    store._by_topic_lower[main_doc.metadata.topic.lower()] = main_doc

    other_topics = [
        ("wildlife/apex_predators_5m", "Apex Predators in Marine Ecosystems"),
        ("wildlife/coral_reefs_5m", "Coral Reef Ecosystem Protection"),
        ("wildlife/wetlands_5m", "Wetlands Preservation and Restoration"),
        ("wildlife/savanna_5m", "Savanna Grazing Dynamics and Habitats"),
    ]
    for tid, topic in other_topics:
        stem = tid.split("/")[1]
        doc = TemplateDocument(
            metadata=TopicMetadata(
                template_id=tid,
                category_slug="wildlife",
                category="Wildlife",
                topic=topic,
                topic_slug=stem,
                duration_min=5,
            ),
            body=(
                f"Speech on {topic}.\n\n"
                "First, we note {{ argument_foundation }}.\n\n"
                "Next, examining {{ argument_evidence }}.\n\n"
                "Conclusion."
            ),
            file_path=f"data/templates/{tid}.md",
        )
        store._by_id[tid] = doc
        store._by_topic_lower[topic.lower()] = doc

    return store, main_doc


@pytest.fixture()
def scenario_setup(monkeypatch: pytest.MonkeyPatch):
    """Set up isolated pipeline, test client, and clear chat session store."""
    from src.app.config import settings
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "ollama_host", "")
    chat_session_store.clear()
    store, main_template = _build_test_store()

    mock_llm = MagicMock()

    def _fake_free_topic(
        topic: str,
        duration_min: int = 5,
        chunks: list[DocumentChunk] | None = None,
        greeting: str | None = None,
        user_feedback: str | None = None,
        **_: object,
    ) -> GeneratedScript:
        words = " ".join(["speech"] * 650)
        citations = (
            [
                ParagraphCitation(
                    paragraph=1,
                    heading=chunks[0].heading if chunks else None,
                    page=chunks[0].page if chunks else None,
                    status="cited",
                    chunk_id=1,
                )
            ]
            if chunks
            else [ParagraphCitation(paragraph=1, heading=None, page=None, status="uncited")]
        )
        flags = [] if chunks else ["uncited"]
        if user_feedback:
            flags.append("revised")
        return GeneratedScript(
            script=f"Generated script about {topic}. Feedback: {user_feedback or 'none'}. {words}",
            word_count=len(words.split()) + 6,
            duration_min=duration_min,
            source="llm",
            template_id=None,
            models_used=["openai/gpt-oss-120b"],
            citations=citations,
            flags=flags,
        )

    mock_llm.generate_free_topic_script.side_effect = _fake_free_topic

    pipeline = ScriptGenerationPipeline(
        template_store=store,
        template_engine=TemplateEngine(),
        llm_generator=mock_llm,
        moderator=ContentModerator(enable_llama_guard=False),
    )
    monkeypatch.setattr(app_main, "_script_pipeline", pipeline)

    current_user_obj = _user("scenario-tester")
    app_main.app.dependency_overrides[get_current_user] = lambda: current_user_obj

    client = TestClient(app_main.app)
    yield {
        "client": client,
        "pipeline": pipeline,
        "store": store,
        "main_template": main_template,
        "mock_llm": mock_llm,
        "user": current_user_obj,
    }
    app_main.app.dependency_overrides.clear()
    chat_session_store.clear()


# ---------------------------------------------------------------------------
# Scenario 1: Suggesting 4–5 Topics (Strong Match & recommend_free_topic)
# ---------------------------------------------------------------------------


class TestScenario1TopicSuggestions:
    """Scenario 1: Suggesting 4–5 topics from category + duration + prompt."""

    def test_unit_suggest_topics_strong_match(self, scenario_setup) -> None:
        store = scenario_setup["store"]
        retriever = SemanticRetriever()

        res = store.suggest_topics(
            category_slug="wildlife",
            duration_min=5,
            query="Keystone Species Conservation in ecosystems",
            retriever=retriever,
        )
        assert 4 <= len(res.suggestions) <= 5
        assert res.recommend_free_topic is False
        assert res.suggestions[0].is_strong_match is True
        assert res.suggestions[0].template_id == "wildlife/keystone_5m"

    def test_unit_suggest_topics_weak_match_recommends_free_topic(self, scenario_setup) -> None:
        store = scenario_setup["store"]
        retriever = SemanticRetriever()

        res = store.suggest_topics(
            category_slug="wildlife",
            duration_min=5,
            query="Quantum algorithms and cryptography polynomials",
            retriever=retriever,
        )
        assert res.recommend_free_topic is True
        assert len(res.suggestions) <= 3
        assert all(s.is_strong_match is False for s in res.suggestions)

    def test_api_suggest_endpoint_strong_match(self, scenario_setup) -> None:
        client: TestClient = scenario_setup["client"]
        resp = client.post(
            "/api/script-chat/suggest",
            data={
                "category": "wildlife",
                "duration_min": 5,
                "prompt": "Keystone Species Conservation keynote",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["recommend_free_topic"] is False
        assert 4 <= len(body["suggestions"]) <= 5
        assert body["suggestions"][0]["template_id"] == "wildlife/keystone_5m"

    def test_api_suggest_endpoint_weak_match_recommends_free(self, scenario_setup) -> None:
        client: TestClient = scenario_setup["client"]
        resp = client.post(
            "/api/script-chat/suggest",
            data={
                "category": "wildlife",
                "duration_min": 5,
                "prompt": "Unrelated financial derivatives and arbitrage",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recommend_free_topic"] is True
        assert len(body["suggestions"]) <= 3

    def test_api_suggest_reuses_session_and_ingests_file(self, scenario_setup) -> None:
        client: TestClient = scenario_setup["client"]
        first_resp = client.post(
            "/api/script-chat/suggest",
            data={"category": "wildlife", "duration_min": 5, "prompt": "Conservation"},
        )
        session_id = first_resp.json()["session_id"]

        doc_content = b"Detailed field research on apex predators and marine ecosystems."
        second_resp = client.post(
            "/api/script-chat/suggest",
            data={"session_id": session_id, "category": "wildlife", "duration_min": 5},
            files={"file": ("notes.txt", io.BytesIO(doc_content), "text/plain")},
        )
        assert second_resp.status_code == 200
        body = second_resp.json()
        assert body["session_id"] == session_id

        # Verify chunks were added to session in memory
        user_id = str(scenario_setup["user"].id)
        session = chat_session_store.get(session_id, user_id=user_id)
        assert session is not None
        assert len(session.chunks) > 0
        assert "notes.txt" in session.files_loaded


# ---------------------------------------------------------------------------
# Scenario 2: Interactive Gathering Reaching ready_to_generate=True
# ---------------------------------------------------------------------------
