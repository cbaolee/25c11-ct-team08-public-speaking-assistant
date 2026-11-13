"""WP-B2 (Member 2): Semantic Chunk Retrieval and Embedding Singleton.

Responsibilities (Brief §5.6):
- Load `all-MiniLM-L6-v2` as a process-wide singleton (shared with Semantic scoring)
- Encode `DocumentChunk` items once per document with L2 normalization
- Retrieve top-k chunks by cosine similarity for each template slot or script section
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

from .contracts import DocumentChunk, ParagraphCitation

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton embedding model
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()


class SemanticRetriever:
    """Singleton-backed semantic retriever over ``DocumentChunk`` lists (Brief §5.6).

    The embedding model (``all-MiniLM-L6-v2``) is loaded **once per process** and
    shared with any other module that calls ``SemanticRetriever.get_model()``.
    """

    _shared_model: Any = None
    _load_attempted: bool = False

    @classmethod
    def get_model(cls) -> Any:
        """Lazily load ``all-MiniLM-L6-v2`` once per process (thread-safe).

        Returns the ``SentenceTransformer`` instance stored in ``cls._shared_model``.
        If ``sentence-transformers`` is not installed the method returns ``None`` and
        the retriever falls back to first-k deterministic ordering.
        """
        if cls._shared_model is not None:
            return cls._shared_model
        if cls._load_attempted:
            return None

        with _model_lock:
            if cls._shared_model is not None:
                return cls._shared_model
            if cls._load_attempted:
                return None
            cls._load_attempted = True
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading all-MiniLM-L6-v2 embedding model …")
                cls._shared_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Embedding model loaded.")
            except Exception:
                logger.warning(
                    "sentence-transformers not available — "
                    "falling back to deterministic first-k retrieval.",
                    exc_info=True,
                )
        return cls._shared_model

    # ------------------------------------------------------------------
    # Encoding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode(model: Any, texts: list[str]) -> NDArray[np.float32]:
        """Encode *texts* with L2-normalised vectors (unit length)."""
        vecs: NDArray[np.float32] = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vecs

    # ------------------------------------------------------------------
    # Top-k retrieval
    # ------------------------------------------------------------------

    def encode_chunks(
        self,
        chunks: list[DocumentChunk],
    ) -> NDArray[np.float32] | None:
        """Return L2-normalised embeddings for *chunks*, or ``None`` on failure."""
        model = self.get_model()
        if model is None or not chunks:
            return None
        texts = [f"{c.heading}: {c.content}" for c in chunks]
        return self._encode(model, texts)

    def retrieve_top_k(
        self,
        query: str,
        chunks: list[DocumentChunk],
        k: int = 3,
        *,
        chunk_embeddings: NDArray[np.float32] | None = None,
    ) -> list[DocumentChunk]:
        """Return up to *k* chunks most relevant to *query* by cosine similarity."""
        if not chunks or k <= 0:
            return []

        model = self.get_model()
        if model is None:
            return chunks[:k]

        if chunk_embeddings is None or chunk_embeddings.shape[0] != len(chunks):
            chunk_embeddings = self.encode_chunks(chunks)
        if chunk_embeddings is None:
            return chunks[:k]

        query_vec = self._encode(model, [query])
        scores: NDArray[np.float32] = (chunk_embeddings @ query_vec.T).squeeze()
        scores = np.atleast_1d(scores)
        top_indices = np.argsort(scores)[::-1][:k]

        return [chunks[int(i)] for i in top_indices]


# ---------------------------------------------------------------------------
# Deterministic citation verification (skeleton for next PR)
# ---------------------------------------------------------------------------


def verify_paragraph_citation(
    paragraph_index: int,
    reported_chunk_ids: list[int],
    retrieved_chunks: list[DocumentChunk],
) -> ParagraphCitation:
    """Deterministically verify LLM-reported chunk IDs against `retrieved_chunks` (Brief §5.6)."""
    return ParagraphCitation(
        paragraph=paragraph_index,
        heading=None,
        page=None,
        status="uncited",
        chunk_id=None,
    )
