"""Unit tests for WP-B2: SemanticRetriever."""

from __future__ import annotations

import re
import sys
import types
import zlib

import numpy as np
import pytest

from src.text_processing.contracts import DocumentChunk, SentenceCitation
from src.text_processing.parser import parse_input_to_chunks
from src.text_processing.retrieval import (
    NLIVerifier,
    SemanticRetriever,
    _build_source_dict,
    _extract_best_excerpt,
    _is_verbatim_inline_fact,
    _split_paragraph_sentences,
    align_script_citations,
    verify_paragraph_citation,
)


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
    NLIVerifier._shared_model = None
    NLIVerifier._load_attempted = False
    yield mock_instance
    SemanticRetriever._shared_model = None
    SemanticRetriever._load_attempted = False
    NLIVerifier._shared_model = None
    NLIVerifier._load_attempted = False


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

    def test_retrieve_top_k_min_score_filters_unrelated_chunks(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        retriever = SemanticRetriever()
        filtered = retriever.retrieve_top_k(
            "amphibian populations tropical regions",
            sample_chunks,
            k=3,
            min_score=0.25,
        )
        assert [c.chunk_id for c in filtered] == [2]

        unrelated = retriever.retrieve_top_k(
            "quantum cryptography blockchain",
            sample_chunks,
            k=3,
            min_score=0.25,
        )
        assert unrelated == []


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

    def test_verify_citation_rejects_unrelated_paragraph_text(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks,
            paragraph_text=(
                "Good morning everyone, today we will explore medieval architecture "
                "and gothic cathedrals across Western Europe."
            ),
            min_support_score=0.25,
        )
        assert citation.status == "uncited"
        assert citation.chunk_id is None
        assert citation.heading is None

    def test_verify_citation_accepts_supported_paragraph_and_inline_fact(
        self, sample_chunks: list[DocumentChunk]
    ) -> None:
        supported = verify_paragraph_citation(
            paragraph_index=2,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks,
            paragraph_text=(
                "Field evidence shows a severe decline in amphibian populations "
                "throughout tropical regions."
            ),
            min_support_score=0.25,
        )
        assert supported.status == "cited"
        assert supported.chunk_id == 2
        assert supported.heading == "Results"

        inline_fact = verify_paragraph_citation(
            paragraph_index=3,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks,
            paragraph_text="tropical regions",
            min_support_score=0.25,
        )
        assert inline_fact.status == "cited"
        assert inline_fact.chunk_id == 2

    def test_align_script_citations_with_chat_note_chunks_page_zero(self) -> None:
        chat_chunks = [
            DocumentChunk(
                chunk_id=1,
                heading="Chat note #1 · Overview",
                page=0,
                content=(
                    "Overview\nThe Tasmanian tiger was a dog-like marsupial distinguished "
                    "by dark stripes across its back, a stiff tail, and a wide jaw gape."
                ),
            ),
            DocumentChunk(
                chunk_id=2,
                heading="Chat note #2 · Historically found across",
                page=0,
                content=(
                    "Historically found across:\nTasmania\nMainland Australia\n"
                    "Papua New Guinea\nIt survived longest in Tasmania due to "
                    "isolation from dingoes."
                ),
            ),
        ]
        # Same-topic paragraph that only mentions "Tasmanian" and "thylacine" without using
        # facts from either chat note must NOT be falsely cited (same-topic leakage guard).
        script = (
            "Inside the cage paces a marsupial with dark stripes across its back, "
            "a stiff tail, and an unusually wide jaw gape.\n\n"
            "Historically it lived across Tasmania, Mainland Australia, and Papua New Guinea, "
            "surviving longest in Tasmania due to isolation from dingoes.\n\n"
            "In 1936 the Tasmanian government passed a law protecting the thylacine "
            "just fifty-nine days before the last captive animal died on a concrete floor."
        )
        citations = align_script_citations(script, chat_chunks, min_support_score=0.52)
        assert len(citations) == 3
        assert citations[0].status == "cited"
        assert citations[0].heading == "Chat note #1 · Overview"
        assert citations[0].page is None
        assert citations[1].status == "cited"
        assert citations[1].heading == "Chat note #2 · Historically found across"
        assert citations[1].page is None
        assert citations[2].status == "uncited"


class _FakeBinaryNLIModel:
    """2-class NLI mock mimicking MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary."""

    def __init__(self, scorer) -> None:
        self._scorer = scorer
        self.config = types.SimpleNamespace(id2label={0: "entailment", 1: "not_entailment"})

    def predict(self, pairs: list[tuple[str, str]], **_: object) -> np.ndarray:
        rows = []
        for premise, hypothesis in pairs:
            p_ent = float(self._scorer(premise, hypothesis))
            # Convert probability into logits [log(p), log(1-p)]
            p_clamped = min(max(p_ent, 1e-4), 1.0 - 1e-4)
            rows.append([np.log(p_clamped), np.log(1.0 - p_clamped)])
        return np.array(rows, dtype=np.float32)


class _FakeThreeClassNLIModel:
    """3-class NLI mock mimicking cross-encoder/nli-deberta-v3-xsmall."""

    def __init__(self, scorer) -> None:
        self._scorer = scorer
        self.config = types.SimpleNamespace(
            id2label={0: "contradiction", 1: "entailment", 2: "neutral"}
        )

    def predict(self, pairs: list[tuple[str, str]], **_: object) -> np.ndarray:
        return np.array([self._scorer(p, h) for p, h in pairs], dtype=np.float32)


class TestNLICitationAndMultiHop:
    """Tests for sentence-level NLI, paraphrase acceptance, contradiction guard, and multi-hop."""

    def test_nli_accepts_paraphrase_without_lexical_overlap_and_rejects_contradiction(
        self, sample_chunks: list[DocumentChunk], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _scorer(premise: str, hypothesis: str) -> float:
            if "vanishing rapidly across equatorial" in hypothesis and "amphibian" in premise:
                return 0.92  # Paraphrase entailed
            if "booming rapidly" in hypothesis or "increased by 80%" in hypothesis:
                return 0.03  # Contradiction / fabricated stat rejected
            return 0.05

        fake_nli = NLIVerifier("mock-binary")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        # Paraphrase with near-zero lexical overlap passes via NLI semantic inference
        paraphrased = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks,
            paragraph_text=(
                "Let us look closely at the ecological crisis. "
                "Frogs and toads are vanishing rapidly across equatorial rainforests."
            ),
            nli_verifier=fake_nli,
        )
        assert paraphrased.status == "cited"
        assert paraphrased.chunk_id == 2
        assert paraphrased.page == 3
        assert paraphrased.sources == [
            {
                "chunk_id": 2,
                "heading": "Results",
                "page": 3,
                "excerpt": (
                    "Severe decline observed in amphibian populations across tropical regions."
                ),
                "source_kind": "file",
                "source_msg_id": None,
                "source_file": None,
            }
        ]
        assert len(paraphrased.sentences) == 2
        assert paraphrased.sentences[0].status == "uncited"
        assert paraphrased.sentences[0].sources == []
        assert paraphrased.sentences[1].status == "cited"
        assert paraphrased.sentences[1].sources == paraphrased.sources

        # Contradiction sharing exact lexical words is rejected by NLI
        contradicted = verify_paragraph_citation(
            paragraph_index=2,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks,
            paragraph_text="Amphibian populations across tropical regions increased by 80%.",
            nli_verifier=fake_nli,
        )
        assert contradicted.status == "uncited"
        assert contradicted.sources == []

    def test_three_class_nli_blocks_high_contradiction_even_if_another_sentence_entails(
        self, sample_chunks: list[DocumentChunk], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _scorer(_premise: str, hypothesis: str) -> list[float]:
            if "declined" in hypothesis:
                return [0.02, 0.88, 0.10]  # [contradiction, entailment, neutral]
            return [0.85, 0.05, 0.10]  # Strong contradiction in 2nd sentence

        fake_nli = NLIVerifier("mock-3class")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeThreeClassNLIModel(_scorer)),
        )

        mixed_contradiction = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[2],
            retrieved_chunks=sample_chunks,
            paragraph_text=(
                "Amphibian populations declined in tropical areas. "
                "However, the exact same survey proved amphibian populations doubled there."
            ),
            nli_verifier=fake_nli,
        )
        assert mixed_contradiction.status == "uncited"

    def test_clause_splitting_records_multiple_sources_in_one_paragraph(
        self, sample_chunks: list[DocumentChunk], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _scorer(premise: str, hypothesis: str) -> float:
            low_h = hypothesis.lower()
            # Whole compound sentence isn't entailed by either single chunk alone
            if "while" in low_h:
                return 0.30
            if "amphibian populations" in low_h and "Results:" in premise:
                return 0.91
            if "urgent conservation policy" in low_h and "Conclusion:" in premise:
                return 0.89
            return 0.05

        fake_nli = NLIVerifier("mock-clause")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[2, 4],
            retrieved_chunks=sample_chunks,
            paragraph_text=(
                "Amphibian populations suffered severe declines in tropical zones, "
                "while urgent conservation policy reforms are required to reverse the trend."
            ),
            nli_verifier=fake_nli,
        )
        assert citation.status == "cited"
        assert citation.chunk_id == 2
        assert len(citation.sources) == 2
        assert {s["page"] for s in citation.sources} == {3, 5}

    def test_combined_top2_premise_resolves_true_multihop_synthesis(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            DocumentChunk(
                chunk_id=1,
                heading="Expedition Log",
                page=1,
                content=(
                    "The Vu Quang biological survey team collected rare bovid "
                    "specimens in May 1992."
                ),
            ),
            DocumentChunk(
                chunk_id=2,
                heading="Genetic Analysis",
                page=4,
                content=(
                    "DNA sequencing of the collected Vu Quang bovid specimens "
                    "confirmed a new genus, Pseudoryx."
                ),
            ),
        ]

        def _scorer(premise: str, _hypothesis: str) -> float:
            # Only entails when BOTH chunks are combined in the premise
            if "Expedition Log:" in premise and "Genetic Analysis:" in premise:
                return 0.88
            return 0.32

        fake_nli = NLIVerifier("mock-multihop")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[1, 2],
            retrieved_chunks=chunks,
            paragraph_text=(
                "Specimens gathered during the May 1992 Vu Quang survey were genetically "
                "confirmed as an entirely new bovid genus called Pseudoryx."
            ),
            nli_verifier=fake_nli,
        )
        assert citation.status == "cited"
        assert len(citation.sources) == 2
        assert [s["page"] for s in citation.sources] == [1, 4]

    def test_parser_subchunking_and_inline_fact_proximity(self) -> None:
        long_section = "# Field Results\n" + " ".join(
            [
                f"Sentence {i} documents important camera trap wildlife observations in the valley."
                for i in range(40)
            ]
        )
        sub_chunks = parse_input_to_chunks(
            raw_text=long_section, max_chunk_words=180, chunk_overlap_words=30
        )
        assert len(sub_chunks) >= 3
        assert all(c.heading == "Field Results" and c.page == 1 for c in sub_chunks)
        assert all(len(c.content.split()) <= 180 for c in sub_chunks)

        # Contiguous inline fact passes; scattered words or long repetition fails
        chunk_str = (
            "Results: Severe decline observed in amphibian populations "
            "across tropical regions in 2019."
        )
        assert _is_verbatim_inline_fact("tropical regions", chunk_str) is True
        assert _is_verbatim_inline_fact("2019", chunk_str) is True
        assert _is_verbatim_inline_fact("severe regions", chunk_str) is False
        assert _is_verbatim_inline_fact(" ".join(["tropical"] * 30), chunk_str) is False

    def test_binary_nli_clause_split_blocks_half_fabricated_numeric_clause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            DocumentChunk(
                chunk_id=1,
                heading="Cinema Acoustics",
                page=2,
                content=(
                    "Dolby Atmos debuted in 2012 with Pixar's Brave and supports "
                    "up to 128 discrete audio objects."
                ),
            )
        ]

        def _scorer(_premise: str, hypothesis: str) -> float:
            # Whole sentence fails because of fabricated 10,000; first clause alone entails
            if "10,000" in hypothesis:
                return 0.01
            if "debuted in 2012" in hypothesis:
                return 0.94
            return 0.02

        fake_nli = NLIVerifier("mock-half-contra")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[1],
            retrieved_chunks=chunks,
            paragraph_text=(
                "Dolby Atmos debuted in 2012 with Pixar's Brave "
                "and supports 10,000 discrete audio objects."
            ),
            nli_verifier=fake_nli,
        )
        assert citation.status == "uncited"


class TestSentenceLevelCitationsAndExcerpts:
    """Tests for Contract D: sentence splitting, excerpts, dedup, source caps, and alignment."""

    def test_abbreviation_and_decimal_safe_sentence_splitting(self) -> None:
        para = (
            "Good morning, everyone. "
            "Dr. Smith, Mr. Lee, Mrs. Park, Ms. Tran, and Prof. Wu met in the U.S. "
            "and U.K. to compare Fig. 2 and No. 5, e.g. 3.5 solar grids vs. 4.2% wind "
            "gains, i.e. clean power cited by Chen et al. in 2024. "
            "Thank you for listening!"
        )
        sentences = _split_paragraph_sentences(para)
        assert len(sentences) == 3
        assert sentences[0] == "Good morning, everyone."
        assert sentences[1].startswith("Dr. Smith")
        assert "et al. in 2024." in sentences[1]
        assert sentences[2] == "Thank you for listening!"

    def test_extract_best_excerpt_overlap_and_word_boundary_truncation(self) -> None:
        long_second_sentence = (
            "In 2023 the coastal coral reef survey documented 42 percent bleaching recovery "
            "across northern marine sanctuaries after strict thermal runoff protections were "
            "enforced by regional fisheries boards throughout the archipelago."
        )
        chunk = DocumentChunk(
            chunk_id=10,
            heading="Marine Survey",
            page=4,
            content=(
                "Introduction covers unrelated terrestrial pine forests.\n"
                f"{long_second_sentence} "
                "Finally, budget appendices list equipment costs."
            ),
            source_kind="file",
            source_file="marine_report.pdf",
        )
        excerpt = _extract_best_excerpt(
            "The 2023 survey recorded 42 percent coral bleaching recovery.",
            chunk,
            max_chars=180,
        )
        assert len(excerpt) <= 180
        assert excerpt.endswith("...")
        assert excerpt.startswith("In 2023 the coastal coral reef survey documented 42 percent")
        # Truncated cleanly at a word boundary (no partial word before "...")
        stem = excerpt[:-3]
        assert long_second_sentence.startswith(stem)
        next_char = long_second_sentence[len(stem)]
        assert next_char.isspace() or next_char in ",.;:"

        src = _build_source_dict(chunk, excerpt)
        assert src == {
            "chunk_id": 10,
            "heading": "Marine Survey",
            "page": 4,
            "excerpt": excerpt,
            "source_kind": "file",
            "source_msg_id": None,
            "source_file": "marine_report.pdf",
        }

    def test_three_sentence_paragraph_per_sentence_sources_sorted_nli(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            DocumentChunk(
                chunk_id=1,
                heading="Report Alpha",
                page=2,
                content=(
                    "Solar capacity expanded rapidly. "
                    "Solar microgrids cut rural outages by 45% in 2023."
                ),
                source_kind="file",
                source_file="energy.pdf",
            ),
            DocumentChunk(
                chunk_id=2,
                heading="Chat note #1",
                page=0,
                content="Solar microgrids reduced rural outages by 45% in 2023 field trials.",
                source_kind="chat",
                source_msg_id="msg-101",
            ),
            DocumentChunk(
                chunk_id=3,
                heading="Storage Appendix",
                page=6,
                content="Lithium-iron batteries store excess solar energy for 12 hours.",
                source_kind="file",
                source_file="storage.pdf",
            ),
        ]

        def _scorer(premise: str, hypothesis: str) -> float:
            if "Good morning" in hypothesis:
                return 0.02
            if "outages by 45%" in hypothesis:
                if "Chat note #1" in premise:
                    return 0.95  # Higher score -> must sort first
                if "Report Alpha" in premise:
                    return 0.82
            if "12 hours" in hypothesis and "Storage Appendix" in premise:
                return 0.90
            return 0.04

        fake_nli = NLIVerifier("mock-3sent")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        para = (
            "Good morning, everyone. "
            "Solar microgrids cut rural outages by 45% in 2023. "
            "Lithium-iron batteries store excess solar energy for 12 hours."
        )
        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[1, 2, 3],
            retrieved_chunks=chunks,
            paragraph_text=para,
            nli_verifier=fake_nli,
        )
        assert citation.status == "cited"
        assert len(citation.sentences) == 3

        s0, s1, s2 = citation.sentences
        assert isinstance(s0, SentenceCitation)
        assert s0.sentence_index == 0
        assert s0.text == "Good morning, everyone."
        assert s0.status == "uncited"
        assert s0.sources == []

        assert s1.sentence_index == 1
        assert s1.status == "cited"
        assert len(s1.sources) == 2
        # Sorted by score descending: chunk 2 (0.95) before chunk 1 (0.82)
        assert [s["chunk_id"] for s in s1.sources] == [2, 1]
        assert s1.sources[0]["source_kind"] == "chat"
        assert s1.sources[0]["source_msg_id"] == "msg-101"
        assert s1.sources[0]["page"] is None
        assert s1.sources[1]["source_file"] == "energy.pdf"
        assert all(len(s["excerpt"]) <= 180 and s["excerpt"] for s in s1.sources)
        assert "45%" in s1.sources[1]["excerpt"]

        assert s2.sentence_index == 2
        assert s2.status == "cited"
        assert [s["chunk_id"] for s in s2.sources] == [3]
        assert s2.sources[0]["source_file"] == "storage.pdf"

        # align_script_citations also preserves sentence-level citations and excerpts
        aligned = align_script_citations(para, chunks, [citation], nli_verifier=fake_nli)
        assert len(aligned) == 1
        assert len(aligned[0].sentences) == 3
        assert aligned[0].sentences[0].status == "uncited"
        assert [s["chunk_id"] for s in aligned[0].sentences[1].sources] == [2, 1]
        assert [s["chunk_id"] for s in aligned[0].sentences[2].sources] == [3]

    def test_three_sentence_paragraph_fallback_mode(self) -> None:
        chunks = [
            DocumentChunk(
                chunk_id=1,
                heading="Survey A",
                page=1,
                content="Solar microgrids cut rural outages by 45 percent across island villages.",
                source_kind="file",
                source_file="a.pdf",
            ),
            DocumentChunk(
                chunk_id=2,
                heading="Survey B",
                page=2,
                content="Solar microgrids reduced rural outages in island villages during 2023.",
                source_kind="file",
                source_file="b.pdf",
            ),
            DocumentChunk(
                chunk_id=3,
                heading="Battery C",
                page=3,
                content="Lithium iron phosphate batteries store surplus solar power overnight.",
                source_kind="file",
                source_file="c.pdf",
            ),
        ]
        para = (
            "Good morning, everyone. "
            "Solar microgrids cut rural outages by 45 percent across island villages. "
            "Lithium iron phosphate batteries store surplus solar power overnight."
        )
        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[1, 2, 3],
            retrieved_chunks=chunks,
            paragraph_text=para,
            min_support_score=0.52,
        )
        assert citation.status == "cited"
        assert len(citation.sentences) == 3
        assert citation.sentences[0].status == "uncited"
        assert citation.sentences[0].sources == []
        assert citation.sentences[1].status == "cited"
        assert {s["chunk_id"] for s in citation.sentences[1].sources} == {1, 2}
        assert citation.sentences[2].status == "cited"
        assert [s["chunk_id"] for s in citation.sentences[2].sources] == [3]

    def test_deduplicates_subchunks_with_same_provenance_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = [
            DocumentChunk(
                chunk_id=10,
                heading="Energy Policy",
                page=3,
                content="Sub-chunk one mentions solar targets in general terms.",
                source_kind="file",
                source_file="policy.pdf",
            ),
            DocumentChunk(
                chunk_id=11,
                heading="Energy Policy",
                page=3,
                content="Sub-chunk two specifies solar targets reached 60 gigawatts in 2024.",
                source_kind="file",
                source_file="policy.pdf",
            ),
            # Distinct chat message ID must NOT be collapsed with chunk 12
            DocumentChunk(
                chunk_id=12,
                heading="Chat note",
                page=0,
                content="Solar targets reached 60 gigawatts in 2024 according to grid data.",
                source_kind="chat",
                source_msg_id="msg-a",
            ),
            DocumentChunk(
                chunk_id=13,
                heading="Chat note",
                page=0,
                content="Grid data confirmed solar targets reached 60 gigawatts in 2024.",
                source_kind="chat",
                source_msg_id="msg-b",
            ),
        ]

        def _scorer(premise: str, _hypothesis: str) -> float:
            if "Sub-chunk two" in premise:
                return 0.93
            if "Sub-chunk one" in premise:
                return 0.78
            if "Grid data confirmed" in premise:
                return 0.85
            if "according to grid data" in premise:
                return 0.80
            return 0.1

        fake_nli = NLIVerifier("mock-dedup")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[10, 11, 12, 13],
            retrieved_chunks=chunks,
            paragraph_text="Solar targets reached 60 gigawatts in 2024.",
            nli_verifier=fake_nli,
        )
        assert citation.status == "cited"
        assert len(citation.sentences) == 1
        sent_sources = citation.sentences[0].sources
        # Sub-chunks 10 and 11 share (file, None, "Energy Policy", 3) -> keep higher-scoring 11 only
        assert [s["chunk_id"] for s in sent_sources] == [11, 13, 12]
        assert "60 gigawatts" in sent_sources[0]["excerpt"]

    def test_caps_sources_per_sentence_at_five(self, monkeypatch: pytest.MonkeyPatch) -> None:
        chunks = [
            DocumentChunk(
                chunk_id=i,
                heading=f"Section {i}",
                page=i,
                content=f"Ocean temperatures rose 1.2 degrees in decade {i}.",
                source_kind="file",
                source_file=f"doc_{i}.pdf",
            )
            for i in range(1, 8)
        ]

        def _scorer(premise: str, _hypothesis: str) -> float:
            for i in range(1, 8):
                if f"Section {i}:" in premise:
                    return 0.70 + 0.03 * i
            return 0.05

        fake_nli = NLIVerifier("mock-cap5")
        monkeypatch.setattr(
            NLIVerifier,
            "get_model",
            classmethod(lambda cls, name=None: _FakeBinaryNLIModel(_scorer)),
        )

        citation = verify_paragraph_citation(
            paragraph_index=1,
            reported_chunk_ids=[1, 2, 3, 4, 5, 6, 7],
            retrieved_chunks=chunks,
            paragraph_text="Ocean temperatures rose 1.2 degrees across recorded decades.",
            nli_verifier=fake_nli,
        )
        assert citation.status == "cited"
        assert len(citation.sentences) == 1
        sent_sources = citation.sentences[0].sources
        assert len(sent_sources) == 5
        assert [s["chunk_id"] for s in sent_sources] == [7, 6, 5, 4, 3]
