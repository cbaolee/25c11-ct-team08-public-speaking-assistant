"""Unit tests for WP-B2: SemanticRetriever."""

from __future__ import annotations

import re
import sys
import types
import zlib

import numpy as np
import pytest

from src.text_processing.contracts import DocumentChunk
from src.text_processing.retrieval import SemanticRetriever, verify_paragraph_citation


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
    """Mock sentence_transformers globally for retrieval tests."""
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
def sample_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            chunk_id=0,
            heading="Introduction",
            page=1,
            content="Overview of climate change impacts on biodiversity and global habitats.",
        ),
        DocumentChunk(
            chunk_id=1,
            heading="Methods",
            page=2,
            content="Field survey protocols and statistical methodology used in data analysis.",
        ),
        DocumentChunk(
            chunk_id=2,
            heading="Results",
            page=3,
            content="Severe decline observed in amphibian populations across tropical regions.",
        ),
        DocumentChunk(
            chunk_id=3,
            heading="Discussion",
            page=4,
            content="Habitat loss and rising temperature correlates with vulnerability.",
        ),
        DocumentChunk(
            chunk_id=4,
            heading="Conclusion",
            page=5,
            content="Urgent conservation policy changes needed to reverse trends.",
        ),
    ]


class TestSemanticRetriever:
    """Tests for SemanticRetriever embedding and ranking."""

    def test_retrieve_top_k_empty_chunks(self) -> None:
        retriever = SemanticRetriever()
        assert retriever.retrieve_top_k("test query", [], k=3) == []

    def test_retrieve_top_k_k_zero(self, sample_chunks: list[DocumentChunk]) -> None:
        retriever = SemanticRetriever()
        assert retriever.retrieve_top_k("test query", sample_chunks, k=0) == []

    def test_retrieve_top_k_k_greater_than_chunks(self, sample_chunks: list[DocumentChunk]) -> None:
        retriever = SemanticRetriever()
        result = retriever.retrieve_top_k("biodiversity", sample_chunks, k=10)
        assert len(result) == len(sample_chunks)

    def test_retrieve_top_k_deterministic_fallback(
        self, sample_chunks: list[DocumentChunk], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(SemanticRetriever, "get_model", classmethod(lambda cls: None))
        retriever = SemanticRetriever()
        result = retriever.retrieve_top_k("any query", sample_chunks, k=3)
        assert [c.chunk_id for c in result] == [0, 1, 2]

    def test_encode_chunks_returns_correct_shape(self, sample_chunks: list[DocumentChunk]) -> None:
        retriever = SemanticRetriever()
        embeddings = retriever.encode_chunks(sample_chunks)
        assert embeddings is not None
        assert embeddings.shape == (len(sample_chunks), 384)
        for vec in embeddings:
            assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-5)

    def test_encode_chunks_empty(self) -> None:
        retriever = SemanticRetriever()
        assert retriever.encode_chunks([]) is None

    def test_encode_chunks_when_model_none(
        self, sample_chunks: list[DocumentChunk], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(SemanticRetriever, "get_model", classmethod(lambda cls: None))
        retriever = SemanticRetriever()
        assert retriever.encode_chunks(sample_chunks) is None

    def test_retrieve_top_k_with_model(self, sample_chunks: list[DocumentChunk]) -> None:
        retriever = SemanticRetriever()
        result = retriever.retrieve_top_k(
            "amphibian population decline research findings",
            sample_chunks,
            k=2,
        )
        assert len(result) == 2
        top_ids = [c.chunk_id for c in result]
        assert 2 in top_ids

    def test_retrieve_top_k_single_chunk(self) -> None:
        retriever = SemanticRetriever()
        single = [DocumentChunk(chunk_id=42, heading="H", page=1, content="Amphibians.")]
        result = retriever.retrieve_top_k("amphibian", single, k=3)
        assert len(result) == 1
        assert result[0].chunk_id == 42

    def test_retrieve_top_k_with_precomputed_embeddings(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        retriever = SemanticRetriever()
        embeddings = retriever.encode_chunks(sample_chunks)
        assert embeddings is not None
        result = retriever.retrieve_top_k(
            "conservation policy",
            sample_chunks,
            k=2,
            chunk_embeddings=embeddings,
        )
        assert len(result) == 2
        top_ids = [c.chunk_id for c in result]
        assert 4 in top_ids

    def test_singleton_model_shared(self) -> None:
        m1 = SemanticRetriever.get_model()
        m2 = SemanticRetriever.get_model()
        assert m1 is m2


# ---------------------------------------------------------------------------
# Citation Verification Tests
# ---------------------------------------------------------------------------


class TestVerifyParagraphCitation:
    """Tests for deterministic citation verification against retrieved chunks."""

    def test_valid_citation_exact_match(self, sample_chunks: list[DocumentChunk]) -> None:
        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks[:3],
        )
        assert citation.status == "cited"
        assert citation.paragraph == 1
        assert citation.heading == "Results"
        assert citation.page == 3
        assert citation.chunk_id == 2

    def test_valid_citation_multiple_reported_takes_first_match(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        citation = verify_paragraph_citation(
            paragraph_index=2,
            reported_chunk_ids=[999, 1, 0],
            retrieved_chunks=sample_chunks[:3],
        )
        assert citation.status == "cited"
        assert citation.chunk_id == 1
        assert citation.heading == "Methods"

    def test_invalid_citation_hallucinated_chunk_id(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        citation = verify_paragraph_citation(
            paragraph_index=3,
            reported_chunk_ids=[999],
            retrieved_chunks=sample_chunks[:3],
        )
        assert citation.status == "uncited"
        assert citation.chunk_id is None
        assert citation.heading is None
        assert citation.page is None

    def test_empty_reported_chunk_ids_marks_uncited(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[],
            retrieved_chunks=sample_chunks,
        )
        assert citation.status == "uncited"
        assert citation.chunk_id is None

    def test_empty_retrieved_chunks_marks_uncited(self) -> None:
        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[1, 2],
            retrieved_chunks=[],
        )
        assert citation.status == "uncited"
        assert citation.chunk_id is None

    def test_paragraph_index_preserved(self, sample_chunks: list[DocumentChunk]) -> None:
        for idx in (1, 5, 42):
            citation = verify_paragraph_citation(
                paragraph_index=idx,
                reported_chunk_ids=[0],
                retrieved_chunks=sample_chunks,
            )
            assert citation.paragraph == idx
