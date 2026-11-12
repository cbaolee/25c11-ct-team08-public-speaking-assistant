"""WP-B2 (Member 2): Semantic Chunk Retrieval and Deterministic Citation Verification.

Responsibilities (Brief §5.6):
- Load `all-MiniLM-L6-v2` as a process-wide singleton (shared with Semantic scoring)
- Encode `DocumentChunk` items once per document with L2 normalization
- Retrieve top-k chunks by cosine similarity for each template slot or script section
- Deterministically verify LLM-reported `source_chunk_ids` against retrieved chunks
"""

from typing import Any

from .contracts import DocumentChunk, ParagraphCitation


class SemanticRetriever:
    """Singleton-backed semantic retriever over `DocumentChunk` lists (Brief §5.6)."""

    _shared_model: Any = None

    @classmethod
    def get_model(cls) -> Any:
        """Lazily load `all-MiniLM-L6-v2` once per process.

        TODO (Member 2 - WP-B2):
        Load `SentenceTransformer('all-MiniLM-L6-v2')` and cache in `cls._shared_model`.
        """
        return cls._shared_model

    def retrieve_top_k(
        self,
        query: str,
        chunks: list[DocumentChunk],
        k: int = 3,
    ) -> list[DocumentChunk]:
        """Return up to `k` chunks most relevant to `query` by cosine similarity.

        TODO (Member 2 - WP-B2):
        1. Encode `chunks` and `query` using `self.get_model()` with normalized vectors.
        2. Rank by dot product (cosine similarity) and return top `k`.
        Fallback in skeleton: returns the first `k` chunks deterministically.
        """
        if not chunks or k <= 0:
            return []
        return chunks[:k]


def verify_paragraph_citation(
    paragraph_index: int,
    reported_chunk_ids: list[int],
    retrieved_chunks: list[DocumentChunk],
) -> ParagraphCitation:
    """Deterministically verify LLM-reported chunk IDs against `retrieved_chunks` (Brief §5.6).

    If valid -> status="cited" with `{heading, page}` from the first matched chunk.
    If invalid or empty -> status="uncited" with `heading=None, page=None`.
    """
    by_id = {c.chunk_id: c for c in retrieved_chunks}
    for cid in reported_chunk_ids:
        if cid in by_id:
            matched = by_id[cid]
            return ParagraphCitation(
                paragraph=paragraph_index,
                heading=matched.heading,
                page=matched.page,
                status="cited",
                chunk_id=matched.chunk_id,
            )
    return ParagraphCitation(
        paragraph=paragraph_index,
        heading=None,
        page=None,
        status="uncited",
        chunk_id=None,
    )

