"""Unit tests for 0-LLM-token TemplateStore.suggest_topics()."""

from typing import Any

import numpy as np

from src.app import constants
from src.text_processing.contracts import TemplateDocument, TopicMetadata
from src.text_processing.template_store import (
    DEFAULT_SUGGEST_MIN_SCORE,
    DEFAULT_SUGGEST_TOP_K,
    TemplateStore,
)


class _FakeModel:
    """Deterministic unit-vector encoder keyed by keyword buckets."""

    def __init__(self) -> None:
        self.encode_calls: list[list[str]] = []

    def encode(
        self,
        texts: list[str],
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        self.encode_calls.append(list(texts))
        vectors = []
        for text in texts:
            low = text.lower()
            vec = np.array(
                [
                    1.0 if any(k in low for k in ("coral", "reef", "ocean", "marine")) else 0.0,
                    1.0 if any(k in low for k in ("forest", "tree", "rainforest")) else 0.0,
                    1.0 if any(k in low for k in ("wolf", "predator", "keystone")) else 0.0,
                    1.0 if any(k in low for k in ("migratory", "bird", "flyway")) else 0.0,
                    1.0 if any(k in low for k in ("fox", "urban")) else 0.0,
                    1.0 if any(k in low for k in ("quantum", "blockchain")) else 0.0,
                ],
                dtype=np.float32,
            )
            norm = float(np.linalg.norm(vec))
            vectors.append(vec / norm if norm > 0 else vec)
        return np.vstack(vectors)


class _FakeRetriever:
    def __init__(self, model: Any) -> None:
        self._model = model

    def get_model(self) -> Any:
        return self._model

    @staticmethod
    def _encode(model: Any, texts: list[str]) -> np.ndarray:
        return model.encode(texts)


def _build_store() -> TemplateStore:
    store = TemplateStore()
    entries = [
        ("wildlife", "Wildlife", "coral_reef_restoration_10m", "Coral Reef Restoration", 10),
        ("wildlife", "Wildlife", "ocean_acidification_10m", "Ocean Acidification Threats", 10),
        ("wildlife", "Wildlife", "rainforest_canopy_10m", "Rainforest Canopy Loss", 10),
        ("wildlife", "Wildlife", "keystone_wolves_10m", "Keystone Wolves Recovery", 10),
        ("wildlife", "Wildlife", "migratory_birds_10m", "Migratory Bird Flyways", 10),
        ("wildlife", "Wildlife", "urban_foxes_10m", "Urban Fox Adaptation", 10),
        ("wildlife", "Wildlife", "coral_reef_short_5m", "Coral Reef Basics", 5),
        ("sports", "Sports", "cycling_drafting_10m", "Aerodynamic Cycling Drafting", 10),
    ]
    for cat_slug, cat_name, stem, topic, dur in entries:
        tid = f"{cat_slug}/{stem}"
        meta = TopicMetadata(
            template_id=tid,
            category_slug=cat_slug,
            category=cat_name,
            topic=topic,
            topic_slug=stem,
            duration_min=dur,
        )
        store._by_id[tid] = TemplateDocument(meta, "Body text.", f"{tid}.md")
        store._by_topic_lower[topic.lower()] = store._by_id[tid]
    return store


def test_suggest_constants_match_app_constants_toml() -> None:
    cfg = constants.load_constants()["script"]
    assert DEFAULT_SUGGEST_TOP_K == cfg["topic_suggest_top_k"]
    assert DEFAULT_SUGGEST_MIN_SCORE == cfg["topic_suggest_min_score"]


def test_suggest_topics_returns_top_5_filtered_by_category_and_duration() -> None:
    store = _build_store()
    model = _FakeModel()
    retriever = _FakeRetriever(model)

    res = store.suggest_topics("Wildlife", 10, "saving coral reefs in the ocean", retriever)
    assert res.recommend_free_topic is False
    assert len(res.suggestions) == 5
    assert all(s.category_slug == "wildlife" and s.duration_min == 10 for s in res.suggestions)
    assert res.suggestions[0].template_id in {
        "wildlife/coral_reef_restoration_10m",
        "wildlife/ocean_acidification_10m",
    }
    assert res.suggestions[0].is_strong_match is True
    scores = [s.score for s in res.suggestions]
    assert scores == sorted(scores, reverse=True)
    payload = res.to_dict()
    assert payload["recommend_free_topic"] is False
    assert len(payload["suggestions"]) == 5


def test_suggest_topics_caches_template_embeddings_across_queries() -> None:
    store = _build_store()
    model = _FakeModel()
    retriever = _FakeRetriever(model)

    store.suggest_topics("wildlife", 10, "coral reefs", retriever)
    # First call: 1 batch for 6 candidate templates + 1 batch for query
    assert len(model.encode_calls) == 2
    assert len(model.encode_calls[0]) == 6

    store.suggest_topics("wildlife", 10, "rainforest trees", retriever)
    # Second call: only query is encoded (candidate embeddings reused from cache)
    assert len(model.encode_calls) == 3
    assert model.encode_calls[2] == ["rainforest trees"]


def test_suggest_topics_recommends_free_topic_when_no_strong_match() -> None:
    store = _build_store()
    retriever = _FakeRetriever(_FakeModel())

    res = store.suggest_topics(
        "wildlife", 10, "quantum blockchain cryptography", retriever, min_score=0.5
    )
    assert res.recommend_free_topic is True
    assert len(res.suggestions) == 3
    assert all(not s.is_strong_match for s in res.suggestions)


def test_suggest_topics_empty_query_returns_first_top_k_candidates() -> None:
    store = _build_store()
    retriever = _FakeRetriever(_FakeModel())

    res = store.suggest_topics("wildlife", 10, "   ", retriever, top_k=4)
    assert res.recommend_free_topic is False
    assert len(res.suggestions) == 4
    assert all(s.score == 0.0 for s in res.suggestions)


def test_suggest_topics_lexical_fallback_when_embedding_model_unavailable() -> None:
    store = _build_store()
    retriever = _FakeRetriever(model=None)

    res = store.suggest_topics("wildlife", 10, "keystone wolves recovery", retriever)
    assert res.recommend_free_topic is False
    assert res.suggestions[0].template_id == "wildlife/keystone_wolves_10m"
    assert res.suggestions[0].is_strong_match is True


def test_suggest_topics_returns_empty_and_free_topic_for_unknown_category() -> None:
    store = _build_store()
    retriever = _FakeRetriever(_FakeModel())

    res = store.suggest_topics("nonexistent_category", 10, "anything", retriever)
    assert res.suggestions == []
    assert res.recommend_free_topic is True
