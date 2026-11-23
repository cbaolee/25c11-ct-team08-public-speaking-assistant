"""WP-B2 (Member 2): Semantic Chunk Retrieval and Embedding Singleton.

Responsibilities (Brief §5.6):
- Load `all-MiniLM-L6-v2` as a process-wide singleton (shared with Semantic scoring)
- Encode `DocumentChunk` items once per document with L2 normalization
- Retrieve top-k chunks by cosine similarity for each template slot or script section
"""

from __future__ import annotations

import logging
import re
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

from .contracts import DocumentChunk, ParagraphCitation

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    {
        "about",
        "across",
        "after",
        "against",
        "also",
        "among",
        "around",
        "are",
        "because",
        "been",
        "before",
        "being",
        "between",
        "both",
        "but",
        "can",
        "could",
        "does",
        "during",
        "each",
        "first",
        "for",
        "from",
        "furthermore",
        "good",
        "has",
        "have",
        "having",
        "here",
        "how",
        "however",
        "into",
        "its",
        "more",
        "most",
        "morning",
        "not",
        "now",
        "only",
        "other",
        "our",
        "out",
        "over",
        "same",
        "should",
        "show",
        "shows",
        "some",
        "such",
        "thank",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "today",
        "toward",
        "towards",
        "under",
        "very",
        "was",
        "Welcome",
        "welcome",
        "were",
        "what",
        "when",
        "where",
        "whereas",
        "which",
        "while",
        "who",
        "will",
        "with",
        "within",
        "without",
        "would",
        "you",
        "your",
    }
)


def _extract_content_tokens(text: str) -> set[str]:
    """Return lowercase content words (length >= 3 or numeric) excluding stopwords."""
    raw = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {t for t in raw if (len(t) >= 3 or t.isdigit()) and t not in _STOPWORDS}


def _is_verbatim_inline_fact(query_or_para: str, chunk_text: str) -> bool:
    """Return True when a short inline fact (1-4 content tokens) is verbatim in *chunk_text*."""
    q_tokens = _extract_content_tokens(query_or_para)
    c_tokens = _extract_content_tokens(chunk_text)
    return bool(q_tokens and len(q_tokens) <= 4 and q_tokens <= c_tokens)


def _lexical_overlap_score(query_or_para: str, chunk_text: str) -> float:
    """Compute content-token recall of *query_or_para* supported by *chunk_text*."""
    q_tokens = _extract_content_tokens(query_or_para)
    c_tokens = _extract_content_tokens(chunk_text)
    if not q_tokens or not c_tokens:
        return 0.0
    shared = q_tokens & c_tokens
    if not shared:
        return 0.0
    if _is_verbatim_inline_fact(query_or_para, chunk_text):
        return 1.0
    if len(shared) < 2:
        return 0.0
    # Require >=3 shared content tokens on standard paragraphs (>=10 content tokens) to reach 0.25,
    # preventing 2 shared topic-name words (e.g. "tasmanian" + "thylacine") from false cites.
    return len(shared) / min(len(q_tokens), 10)

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
        min_score: float | None = None,
    ) -> list[DocumentChunk]:
        """Return up to *k* chunks most relevant to *query* by cosine similarity."""
        if not chunks or k <= 0:
            return []

        model = self.get_model()
        if model is None:
            if min_score is None:
                return chunks[:k]
            scored = [
                (_lexical_overlap_score(query, f"{c.heading}: {c.content}"), idx, c)
                for idx, c in enumerate(chunks)
            ]
            scored.sort(key=lambda item: (-item[0], item[1]))
            return [c for score, _, c in scored[:k] if score >= min_score]

        if chunk_embeddings is None or chunk_embeddings.shape[0] != len(chunks):
            chunk_embeddings = self.encode_chunks(chunks)
        if chunk_embeddings is None:
            return chunks[:k]

        query_vec = self._encode(model, [query])
        scores: NDArray[np.float32] = (chunk_embeddings @ query_vec.T).squeeze()
        scores = np.atleast_1d(scores)
        top_indices = np.argsort(scores)[::-1][:k]

        if min_score is not None:
            return [chunks[int(i)] for i in top_indices if float(scores[int(i)]) >= min_score]
        return [chunks[int(i)] for i in top_indices]


# ---------------------------------------------------------------------------
# Deterministic citation verification
# ---------------------------------------------------------------------------


def verify_paragraph_citation(
    paragraph_index: int,
    reported_chunk_ids: list[int],
    retrieved_chunks: list[DocumentChunk],
    *,
    paragraph_text: str | None = None,
    retriever: SemanticRetriever | None = None,
    chunk_embeddings_by_id: dict[int, NDArray[np.float32]] | None = None,
    min_support_score: float = 0.52,
) -> ParagraphCitation:
    """Deterministically verify LLM-reported chunk IDs and content support.

    If a reported ``chunk_id`` exists in *retrieved_chunks* (and, when
    *paragraph_text* is supplied, its content both semantically and lexically
    supports the paragraph), the citation is ``"cited"``. Otherwise it is
    downgraded to ``"uncited"``.
    """
    by_id = {c.chunk_id: c for c in retrieved_chunks}
    seen: set[int] = set()
    candidates: list[DocumentChunk] = []
    for cid in reported_chunk_ids:
        if cid in by_id and cid not in seen:
            seen.add(cid)
            candidates.append(by_id[cid])

    if not candidates:
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
        )

    # Backward-compatible ID-only check when paragraph_text is not provided
    if paragraph_text is None or not paragraph_text.strip():
        chosen = candidates[0]
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=chosen.heading,
            page=chosen.page if (chosen.page is not None and chosen.page > 0) else None,
            status="cited",
            chunk_id=chosen.chunk_id,
        )

    clean_para = paragraph_text.strip()
    active_retriever = retriever or SemanticRetriever()
    model = active_retriever.get_model()
    para_vec: NDArray[np.float32] | None = None
    if model is not None:
        try:
            para_vec = active_retriever._encode(model, [clean_para])[0]
        except Exception:
            para_vec = None

    min_lexical_support = min(0.25, min_support_score)
    best_chunk: DocumentChunk | None = None
    best_score = -1.0
    for chunk in candidates:
        chunk_full = f"{chunk.heading}: {chunk.content}"
        if _is_verbatim_inline_fact(clean_para, chunk_full):
            score = 1.0
        else:
            lex_score = _lexical_overlap_score(clean_para, chunk_full)
            if para_vec is not None:
                c_vec = (chunk_embeddings_by_id or {}).get(chunk.chunk_id)
                if c_vec is None:
                    try:
                        c_vec = active_retriever._encode(model, [chunk_full])[0]
                    except Exception:
                        c_vec = None
                sem_score = float(np.dot(c_vec, para_vec)) if c_vec is not None else -1.0
                # Require BOTH semantic similarity >= min_support_score AND factual lexical overlap
                # >= 0.25 so same-topic paragraphs that only share 1-2 topic words are rejected.
                score = sem_score if lex_score >= min_lexical_support else -1.0
            else:
                score = lex_score

        if score > best_score:
            best_score = score
            best_chunk = chunk

    if best_chunk is not None and best_score >= min_support_score:
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=best_chunk.heading,
            page=best_chunk.page if (best_chunk.page is not None and best_chunk.page > 0) else None,
            status="cited",
            chunk_id=best_chunk.chunk_id,
        )

    return ParagraphCitation(
        paragraph=paragraph_index,
        heading=None,
        page=None,
        status="uncited",
        chunk_id=None,
    )


def align_script_citations(
    script_text: str,
    chunks: list[DocumentChunk],
    existing_citations: list[ParagraphCitation] | None = None,
    *,
    retriever: SemanticRetriever | None = None,
    min_support_score: float = 0.52,
) -> list[ParagraphCitation]:
    """Align and verify citations for every paragraph of *script_text* against *chunks*.

    Used after template assembly and paragraph polishing so that fixed-prose template
    paragraphs or paragraphs enriched with chat notes / user feedback receive accurate
    ``"cited"`` or ``"uncited"`` badges.
    """
    if not chunks or not script_text or not script_text.strip():
        return list(existing_citations or [])

    paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
    if not paragraphs:
        return list(existing_citations or [])

    active_retriever = retriever or SemanticRetriever()
    chunk_embeddings = active_retriever.encode_chunks(chunks)
    chunk_embeddings_by_id = (
        {c.chunk_id: chunk_embeddings[i] for i, c in enumerate(chunks)}
        if (chunk_embeddings is not None and len(chunk_embeddings) == len(chunks))
        else None
    )
    existing_by_para = {
        c.paragraph: c for c in (existing_citations or []) if c.status == "cited"
    }

    aligned: list[ParagraphCitation] = []
    for idx, para_text in enumerate(paragraphs, start=1):
        prev = existing_by_para.get(idx)
        if prev is not None and prev.chunk_id is not None:
            rechecked = verify_paragraph_citation(
                paragraph_index=idx,
                reported_chunk_ids=[prev.chunk_id],
                retrieved_chunks=chunks,
                paragraph_text=para_text,
                retriever=active_retriever,
                chunk_embeddings_by_id=chunk_embeddings_by_id,
                min_support_score=min_support_score,
            )
            if rechecked.status == "cited":
                aligned.append(rechecked)
                continue

        top_candidates = active_retriever.retrieve_top_k(
            para_text,
            chunks,
            k=2,
            chunk_embeddings=chunk_embeddings,
            min_score=min_support_score,
        )
        citation = verify_paragraph_citation(
            paragraph_index=idx,
            reported_chunk_ids=[c.chunk_id for c in top_candidates],
            retrieved_chunks=top_candidates,
            paragraph_text=para_text,
            retriever=active_retriever,
            chunk_embeddings_by_id=chunk_embeddings_by_id,
            min_support_score=min_support_score,
        )
        aligned.append(citation)
    return aligned
