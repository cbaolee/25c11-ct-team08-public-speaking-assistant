"""WP-B2 (Member 2): Semantic Chunk Retrieval and NLI Citation Verification.

Responsibilities (Brief §5.6 + Citation Grounding Upgrade):
- Load ``all-MiniLM-L6-v2`` as a process-wide singleton for fast top-k retrieval
- Load ``MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary`` (or configured 2/3-class
  Cross-Encoder NLI model) as a singleton for sentence-level semantic inference
- Support clause splitting and combined Top-2 premise NLI for multi-hop synthesis
- Populate backward-compatible multi-source ``ParagraphCitation.sources``
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

from src.app.constants import CONSTANTS

from .contracts import DocumentChunk, ParagraphCitation, SentenceCitation
from .sanitizer import sanitize_text

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_DEFAULT_NLI_MODEL = str(
    CONSTANTS["script"].get(
        "citation_nli_model",
        "MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli-ling-binary",
    )
)
_NLI_ENTAILMENT_MIN = float(CONSTANTS["script"].get("citation_nli_entailment_min", 0.65))
_NLI_CONTRADICTION_MAX = float(CONSTANTS["script"].get("citation_nli_contradiction_max", 0.35))
_MULTIHOP_MIN_RETRIEVAL_SCORE = float(
    CONSTANTS["script"].get("citation_multihop_min_retrieval_score", 0.35)
)
_RETRIEVAL_MIN_SCORE = float(CONSTANTS["script"].get("retrieval_min_score", 0.25))
_MAX_EXCERPT_CHARS = int(CONSTANTS["script"].get("citation_max_excerpt_chars", 180))
_MAX_SOURCES_PER_SENTENCE = int(
    CONSTANTS["script"].get("citation_max_sources_per_sentence", 5)
)

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

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_ABBREV_RE = re.compile(
    r"(?i:\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|St|Fig|Vol|vs|etc|approx|Inc|Ltd|Co|U\.S|U\.K|e\.g|i\.e|a\.m|p\.m|et\s+al)\.)"
    r"|\bNo\."
)
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:;\s+|,\s+(?:while|whereas|however|although|though|yet|but|and)\s+|\s+(?:while|whereas|and)\s+)",
    re.IGNORECASE,
)


def _extract_content_tokens(text: str) -> set[str]:
    """Return lowercase content words (length >= 3 or numeric) excluding stopwords."""
    raw = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {t for t in raw if (len(t) >= 3 or t.isdigit()) and t not in _STOPWORDS}


def _extract_ordered_content_tokens(text: str) -> list[str]:
    """Return ordered lowercase content words (length >= 3 or numeric) excluding stopwords."""
    raw = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [t for t in raw if (len(t) >= 3 or t.isdigit()) and t not in _STOPWORDS]


def _is_verbatim_inline_fact(query_or_para: str, chunk_text: str) -> bool:
    """Return True when a short inline slot/phrase (<=8 words, 1-4 content tokens) is in chunk.

    Requires contiguous phrase match or ordered proximity (window <= len + 3) rather than
    scattered bag-of-words membership across the whole chunk.
    """
    raw_words = re.findall(r"[a-zA-Z0-9]+", query_or_para.lower())
    if not raw_words or len(raw_words) > 8:
        return False
    q_ordered = _extract_ordered_content_tokens(query_or_para)
    if not q_ordered or len(q_ordered) > 4:
        return False

    norm_q = " ".join(raw_words)
    norm_c = " ".join(re.findall(r"[a-zA-Z0-9]+", chunk_text.lower()))
    if re.search(rf"\b{re.escape(norm_q)}\b", norm_c):
        return True

    # Ordered proximity check on content tokens (handles minor articles/prepositions in between)
    c_words = re.findall(r"[a-zA-Z0-9]+", chunk_text.lower())
    if len(q_ordered) == 1:
        tok = q_ordered[0]
        return tok in c_words

    max_span = len(q_ordered) + 3
    first_tok = q_ordered[0]
    for start_idx, word in enumerate(c_words):
        if word != first_tok:
            continue
        window = c_words[start_idx : start_idx + max_span]
        pos = 0
        matched_all = True
        for target in q_ordered[1:]:
            try:
                rel = window.index(target, pos + 1)
                pos = rel
            except ValueError:
                matched_all = False
                break
        if matched_all:
            return True
    return False


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


def _split_paragraph_sentences(paragraph_text: str) -> list[str]:
    """Split paragraph into sentences in order without splitting abbreviations or decimals."""
    text = (paragraph_text or "").strip()
    if not text or not re.search(r"[a-zA-Z0-9]", text):
        return []

    protected_dots: set[int] = {m.end() - 1 for m in _ABBREV_RE.finditer(text)}
    parts: list[str] = []
    start = 0
    for match in _SENTENCE_SPLIT_RE.finditer(text):
        punct_idx = match.start() - 1
        if punct_idx in protected_dots:
            continue
        segment = text[start : match.start()].strip()
        if segment:
            parts.append(segment)
        start = match.end()

    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_clauses(sentence: str) -> list[str]:
    """Split a compound sentence into substantive sub-clauses for multi-source attribution."""
    clauses = [c.strip(" ,;.") for c in _CLAUSE_SPLIT_RE.split(sentence) if c.strip(" ,;.")]
    if len(clauses) < 2:
        return []
    return [c for c in clauses if len(_extract_content_tokens(c)) >= 3]


def _excerpt_overlap_score(sentence_text: str, candidate_text: str) -> tuple[int, int, float]:
    """Score keyword + numeric overlap between *sentence_text* and *candidate_text*."""
    q_tokens = _extract_content_tokens(sentence_text)
    c_tokens = _extract_content_tokens(candidate_text)
    q_nums = set(re.findall(r"\d+(?:\.\d+)?", sentence_text.replace(",", "")))
    c_nums = set(re.findall(r"\d+(?:\.\d+)?", candidate_text.replace(",", "")))
    kw_hits = len(q_tokens & c_tokens)
    num_hits = len(q_nums & c_nums)
    weighted = kw_hits + 2 * num_hits
    union_size = len(q_tokens | c_tokens) or 1
    return (weighted, num_hits, kw_hits / union_size)


def _truncate_at_word_boundary(text: str, max_chars: int) -> str:
    """Truncate normalized plain text at a word boundary within *max_chars*."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]

    budget = max_chars - 3
    clipped = text[:budget]
    if not text[budget].isspace():
        last_space = clipped.rfind(" ")
        if last_space > 0:
            clipped = clipped[:last_space]
    clipped = clipped.rstrip(" ,;:")
    return f"{clipped}..."


def _extract_best_excerpt(
    sentence_text: str,
    chunk: DocumentChunk,
    max_chars: int = _MAX_EXCERPT_CHARS,
) -> str:
    """Pick the best-matching sentence from sanitized *chunk.content* within *max_chars*."""
    cleaned_content = sanitize_text(chunk.content or "")
    if not cleaned_content:
        return ""
    chunk_sentences = _split_paragraph_sentences(cleaned_content)
    if len(chunk_sentences) <= 1:
        best = chunk_sentences[0] if chunk_sentences else cleaned_content
    else:
        best = max(
            enumerate(chunk_sentences),
            key=lambda item: (_excerpt_overlap_score(sentence_text, item[1]), -item[0]),
        )[1]
    normalized = " ".join(best.split())
    return _truncate_at_word_boundary(normalized, max_chars)


def _build_source_dict(chunk: DocumentChunk, excerpt: str) -> dict[str, Any]:
    """Return a normalized Contract-D source dictionary for *chunk* and *excerpt*."""
    norm_page = chunk.page if (chunk.page is not None and chunk.page > 0) else None
    raw_kind = getattr(chunk, "source_kind", None)
    source_file = getattr(chunk, "source_file", None)
    if chunk.page == 0 and source_file is None:
        source_kind = "chat"
    elif raw_kind in ("file", "chat"):
        source_kind = raw_kind
    else:
        source_kind = "chat" if chunk.page == 0 else "file"
    return {
        "chunk_id": chunk.chunk_id,
        "heading": chunk.heading,
        "page": norm_page,
        "excerpt": excerpt,
        "source_kind": source_kind,
        "source_msg_id": getattr(chunk, "source_msg_id", None),
        "source_file": source_file,
    }


def _source_dedup_key(src: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (src["source_kind"], src["source_msg_id"], src["heading"], src["page"])


def _build_sentence_sources(
    sentence_text: str,
    scored_chunks: list[tuple[float, int, DocumentChunk]],
    *,
    max_sources: int = _MAX_SOURCES_PER_SENTENCE,
) -> list[dict[str, Any]]:
    """Sort by score descending, deduplicate by (kind, msg_id, heading, page), and cap."""
    ranked = sorted(
        scored_chunks,
        key=lambda item: (
            -item[0],
            -_excerpt_overlap_score(sentence_text, item[2].content)[0],
            item[1],
        ),
    )
    seen_keys: set[tuple[Any, Any, Any, Any]] = set()
    sources: list[dict[str, Any]] = []
    for _, _, ch in ranked:
        excerpt = _extract_best_excerpt(sentence_text, ch, max_chars=_MAX_EXCERPT_CHARS)
        src = _build_source_dict(ch, excerpt)
        key = _source_dedup_key(src)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        sources.append(src)
        if len(sources) >= max_sources:
            break
    return sources


def _build_paragraph_sources_from_sentences(
    sentence_entries: list[tuple[str, list[tuple[float, int, DocumentChunk]]]],
) -> list[dict[str, Any]]:
    """Aggregate best-scored deduplicated sources across all cited sentences in a paragraph."""
    flat_ranked: list[tuple[float, int, str, DocumentChunk]] = []
    for sent_text, scored_chunks in sentence_entries:
        for score, order_idx, ch in scored_chunks:
            flat_ranked.append((score, order_idx, sent_text, ch))
    flat_ranked.sort(
        key=lambda item: (
            -item[0],
            -_excerpt_overlap_score(item[2], item[3].content)[0],
            item[1],
        )
    )
    seen_keys: set[tuple[Any, Any, Any, Any]] = set()
    sources: list[dict[str, Any]] = []
    for _, _, sent_text, ch in flat_ranked:
        excerpt = _extract_best_excerpt(sent_text, ch, max_chars=_MAX_EXCERPT_CHARS)
        src = _build_source_dict(ch, excerpt)
        key = _source_dedup_key(src)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        sources.append(src)
    return sources


# ---------------------------------------------------------------------------
# Singleton Bi-Encoder embedding model (Retrieval)
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

        Tries local HuggingFace cache first to avoid unnecessary Hub HTTP checks or
        offline retry stalls, falling back to Hub download when allowed.
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
                try:
                    cls._shared_model = SentenceTransformer(
                        "all-MiniLM-L6-v2", local_files_only=True
                    )
                except TypeError:
                    # Lightweight test mocks may not accept local_files_only
                    cls._shared_model = SentenceTransformer("all-MiniLM-L6-v2")
                except Exception:
                    if os.environ.get("HF_HUB_OFFLINE") == "1":
                        raise
                    cls._shared_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Embedding model loaded.")
            except Exception:
                logger.warning(
                    "sentence-transformers not available — "
                    "falling back to deterministic lexical retrieval.",
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
# Singleton Cross-Encoder NLI model (Semantic Inference)
# ---------------------------------------------------------------------------

_nli_lock = threading.Lock()


def _softmax_rows(logits: NDArray[np.floating[Any]]) -> NDArray[np.float64]:
    arr = np.asarray(logits, dtype=np.float64)
    shifted = arr - np.max(arr, axis=-1, keepdims=True)
    exp_arr = np.exp(shifted)
    denom = np.sum(exp_arr, axis=-1, keepdims=True)
    denom = np.where(denom == 0.0, 1.0, denom)
    return exp_arr / denom


class NLIVerifier:
    """Singleton Cross-Encoder NLI verifier supporting both 2-class and 3-class NLI models."""

    _shared_model: Any = None
    _shared_model_name: str | None = None
    _load_attempted: bool = False

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or _DEFAULT_NLI_MODEL

    @classmethod
    def get_model(cls, model_name: str | None = None) -> Any:
        """Lazily load configured Cross-Encoder NLI model once per process."""
        target = model_name or _DEFAULT_NLI_MODEL
        if cls._shared_model is not None and cls._shared_model_name == target:
            return cls._shared_model
        if cls._load_attempted and cls._shared_model_name == target:
            return None

        with _nli_lock:
            if cls._shared_model is not None and cls._shared_model_name == target:
                return cls._shared_model
            if cls._load_attempted and cls._shared_model_name == target:
                return None
            cls._load_attempted = True
            cls._shared_model_name = target
            cls._shared_model = None
            try:
                from sentence_transformers import CrossEncoder

                is_offline = (
                    os.environ.get("HF_HUB_OFFLINE") == "1"
                    or os.environ.get("TRANSFORMERS_OFFLINE") == "1"
                )
                cached_cfg: str | None = None
                try:
                    from huggingface_hub import try_to_load_from_cache

                    res = try_to_load_from_cache(target, "config.json")
                    if isinstance(res, str):
                        cached_cfg = res
                except Exception:
                    cached_cfg = None

                if is_offline and cached_cfg is None:
                    raise OSError(f"Offline mode and {target} is not cached locally.")

                logger.info("Loading Cross-Encoder NLI model %s …", target)
                if cached_cfg is not None:
                    try:
                        cls._shared_model = CrossEncoder(
                            target,
                            model_kwargs={"local_files_only": True},
                            processor_kwargs={"local_files_only": True},
                        )
                    except TypeError:
                        try:
                            cls._shared_model = CrossEncoder(
                                target,
                                model_kwargs={"local_files_only": True},
                                tokenizer_kwargs={"local_files_only": True},
                            )
                        except TypeError:
                            cls._shared_model = CrossEncoder(target)
                else:
                    cls._shared_model = CrossEncoder(target)
                logger.info("Cross-Encoder NLI model loaded.")
            except Exception:
                logger.warning(
                    "Cross-Encoder NLI model (%s) unavailable — "
                    "falling back to Bi-Encoder + lexical citation verification.",
                    target,
                )
        return cls._shared_model

    @staticmethod
    def _resolve_label_indices(model: Any, num_classes: int) -> tuple[int, int | None]:
        """Dynamically inspect ``id2label`` to support 2-class and 3-class NLI models."""
        cfg = getattr(getattr(model, "model", None), "config", None) or getattr(
            model, "config", None
        )
        id2label = getattr(cfg, "id2label", None) if cfg is not None else None
        if isinstance(id2label, dict) and id2label:
            norm_map = {int(k): str(v).strip().lower() for k, v in id2label.items()}
            entail_idx: int | None = None
            contra_idx: int | None = None
            for idx, label in norm_map.items():
                if label == "entailment":
                    entail_idx = idx
                elif label == "contradiction":
                    contra_idx = idx
            if entail_idx is not None:
                return entail_idx, contra_idx

        # Standard fallbacks if a mock/custom model omits id2label:
        # 2-class MoritzLaurer binary models: 0=entailment, 1=not_entailment
        # 3-class cross-encoder/nli-* models: 0=contradiction, 1=entailment, 2=neutral
        if num_classes == 2:
            return 0, None
        return 1, 0

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[tuple[float, float]] | None:
        """Return ``[(p_entailment, p_contradiction), ...]`` for ``(premise, hypothesis)`` pairs."""
        if not pairs:
            return []
        model = self.get_model(self.model_name)
        if model is None:
            return None

        try:
            raw = model.predict(
                pairs,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except TypeError:
            raw = model.predict(pairs)
        except Exception:
            logger.warning("NLIVerifier.predict failed; using fallback verifier.", exc_info=True)
            return None

        arr = np.asarray(raw, dtype=np.float64)
        if arr.ndim == 1:
            # Single-score binary output (either probability in [0,1] or logit)
            if np.all((arr >= 0.0) & (arr <= 1.0)):
                probs_1d = arr
            else:
                probs_1d = 1.0 / (1.0 + np.exp(-arr))
            return [(float(p), 0.0) for p in probs_1d]

        num_classes = arr.shape[-1]
        # Convert logits to probabilities unless already normalized
        row_sums = np.sum(arr, axis=-1)
        if np.all((arr >= 0.0) & (arr <= 1.0)) and np.allclose(row_sums, 1.0, atol=1e-3):
            probs = arr
        else:
            probs = _softmax_rows(arr)

        entail_idx, contra_idx = self._resolve_label_indices(model, num_classes)
        results: list[tuple[float, float]] = []
        for row in probs:
            p_ent = float(row[entail_idx])
            p_con = float(row[contra_idx]) if contra_idx is not None else 0.0
            results.append((p_ent, p_con))
        return results


# ---------------------------------------------------------------------------
# Deterministic & NLI citation verification
# ---------------------------------------------------------------------------


def _verify_with_nli(
    paragraph_index: int,
    clean_para: str,
    candidates: list[DocumentChunk],
    nli: NLIVerifier,
    retriever: SemanticRetriever,
    chunk_embeddings_by_id: dict[int, NDArray[np.float32]] | None,
    entailment_min: float,
    contradiction_max: float,
    *,
    sentence_candidate_cids: list[set[int]] | None = None,
    sentence_embeddings: NDArray[np.float32] | None = None,
    round2a_max_chunks_per_sentence: int = 3,
) -> ParagraphCitation | None:
    """Run Round 1 (sentence-level) + Round 2 (clause & Top-2 multi-hop) NLI verification.

    Returns ``None`` only when the NLI model is unavailable so the caller can fall back.
    When *sentence_candidate_cids* is provided (by ``align_script_citations``), each sentence
    is scored only against its own relevant candidate chunks rather than the Cartesian product
    of every chunk recalled for other sentences in the paragraph.
    """
    sentences = _split_paragraph_sentences(clean_para)
    if not sentences:
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
            sources=[],
        )

    chunk_texts = {c.chunk_id: f"{c.heading}: {c.content}" for c in candidates}

    # Pre-filter out completely off-topic chunks (cosine < 0.20) when real embeddings are
    # available, and cache sentence/chunk vectors for reuse across Round 1, 2A, and 2B.
    emb_model = retriever.get_model()
    s_vecs: NDArray[np.float32] | None = None
    local_c_vecs: dict[int, NDArray[np.float32]] = dict(chunk_embeddings_by_id or {})
    eligible_cids: set[int] = {c.chunk_id for c in candidates}
    if emb_model is not None and not type(emb_model).__name__.startswith("Mock"):
        try:
            if (
                sentence_embeddings is not None
                and len(sentence_embeddings) == len(sentences)
            ):
                s_vecs = sentence_embeddings
            else:
                s_vecs = retriever._encode(emb_model, sentences)
            missing_chunks = [ch for ch in candidates if ch.chunk_id not in local_c_vecs]
            if missing_chunks:
                missing_vecs = retriever._encode(
                    emb_model, [chunk_texts[ch.chunk_id] for ch in missing_chunks]
                )
                for ch, vec in zip(missing_chunks, missing_vecs, strict=True):
                    local_c_vecs[ch.chunk_id] = vec
            eligible_cids = set()
            for ch in candidates:
                c_vec = local_c_vecs[ch.chunk_id]
                max_sim = float(np.max(s_vecs @ c_vec))
                if max_sim >= 0.20:
                    eligible_cids.add(ch.chunk_id)
        except Exception:
            s_vecs = None
            eligible_cids = {c.chunk_id for c in candidates}

    active_candidates = [c for c in candidates if c.chunk_id in eligible_cids]
    if not active_candidates:
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
            sources=[],
            sentences=[
                SentenceCitation(sentence_index=i, text=s, status="uncited", sources=[])
                for i, s in enumerate(sentences)
            ],
        )
    candidates = active_candidates

    # Precompute sentence x candidate similarity matrix once when real embeddings are available.
    sim_matrix: NDArray[np.float32] | None = None
    if s_vecs is not None and all(ch.chunk_id in local_c_vecs for ch in candidates):
        c_mat = np.stack([local_c_vecs[ch.chunk_id] for ch in candidates], axis=0)
        sim_matrix = s_vecs @ c_mat.T

    # Determine per-sentence candidate indices to avoid scoring unrelated chunks across sentences.
    use_per_sent_cids = (
        sentence_candidate_cids is not None
        and len(sentence_candidate_cids) == len(sentences)
    )
    all_c_indices = list(range(len(candidates)))
    per_sent_c_indices: list[list[int]] = []
    for s_idx in range(len(sentences)):
        if use_per_sent_cids:
            allowed_ids = sentence_candidate_cids[s_idx]  # type: ignore[index]
            c_indices = [
                c_idx for c_idx, ch in enumerate(candidates) if ch.chunk_id in allowed_ids
            ]
        elif sim_matrix is not None:
            # On direct multi-sentence calls, skip chunks unrelated to this sentence (sim < 0.20);
            # single-sentence calls keep all paragraph-eligible chunks.
            if len(sentences) > 1:
                c_indices = [
                    c_idx
                    for c_idx in all_c_indices
                    if float(sim_matrix[s_idx, c_idx]) >= 0.20
                ]
            else:
                c_indices = all_c_indices
        else:
            c_indices = all_c_indices
        per_sent_c_indices.append(c_indices)

    # Round 1: Batch all eligible (candidate_chunk, sentence) pairs in one predict() call
    r1_pairs: list[tuple[str, str]] = []
    r1_index: list[tuple[int, int]] = []  # (cand_idx, sent_idx)
    for s_idx, sent in enumerate(sentences):
        for c_idx in per_sent_c_indices[s_idx]:
            r1_pairs.append((chunk_texts[candidates[c_idx].chunk_id], sent))
            r1_index.append((c_idx, s_idx))

    if not r1_pairs:
        # Ensure NLI model availability check still triggers fallback when NLI is unavailable.
        if nli.get_model(nli.model_name) is None:
            return None
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
            sources=[],
            sentences=[
                SentenceCitation(sentence_index=i, text=s, status="uncited", sources=[])
                for i, s in enumerate(sentences)
            ],
        )

    r1_scores = nli.score_pairs(r1_pairs)
    if r1_scores is None:
        return None  # Signal caller to use Bi-Encoder + lexical fallback

    best_entail_by_cid: dict[int, float] = {c.chunk_id: 0.0 for c in candidates}
    max_contra_by_cid: dict[int, float] = {c.chunk_id: 0.0 for c in candidates}
    sent_supported = [False] * len(sentences)
    sent_chunk_scores: list[dict[int, float]] = [{} for _ in sentences]

    for (c_idx, s_idx), (p_ent, p_con) in zip(r1_index, r1_scores, strict=True):
        cid = candidates[c_idx].chunk_id
        if p_ent > best_entail_by_cid[cid]:
            best_entail_by_cid[cid] = p_ent
        if p_con > max_contra_by_cid[cid]:
            max_contra_by_cid[cid] = p_con
        if p_ent >= entailment_min and p_con < contradiction_max:
            sent_supported[s_idx] = True
            sent_chunk_scores[s_idx][cid] = max(sent_chunk_scores[s_idx].get(cid, 0.0), p_ent)

    accepted_scores: dict[int, float] = {
        c.chunk_id: best_entail_by_cid[c.chunk_id]
        for c in candidates
        if best_entail_by_cid[c.chunk_id] >= entailment_min
        and max_contra_by_cid[c.chunk_id] < contradiction_max
    }

    # Round 2A: Clause splitting for compound sentences that missed Round 1
    unsupported_indices = [
        i for i, ok in enumerate(sent_supported) if not ok and per_sent_c_indices[i]
    ]
    if unsupported_indices:
        clauses_by_sent: dict[int, list[str]] = {}
        clause_pairs: list[tuple[str, str]] = []
        clause_meta: list[tuple[int, int, int]] = []  # (cand_idx, sent_idx, clause_idx)
        for s_idx in unsupported_indices:
            clauses = _split_clauses(sentences[s_idx])
            if not clauses:
                continue
            clauses_by_sent[s_idx] = clauses
            sent_cands = per_sent_c_indices[s_idx]
            if (
                sim_matrix is not None
                and round2a_max_chunks_per_sentence > 0
                and len(sent_cands) > round2a_max_chunks_per_sentence
            ):
                sent_cands = sorted(
                    sent_cands,
                    key=lambda ci: float(sim_matrix[s_idx, ci]),
                    reverse=True,
                )[:round2a_max_chunks_per_sentence]
            for cl_idx, clause in enumerate(clauses):
                for c_idx in sent_cands:
                    clause_pairs.append((chunk_texts[candidates[c_idx].chunk_id], clause))
                    clause_meta.append((c_idx, s_idx, cl_idx))

        if clause_pairs:
            clause_scores = nli.score_pairs(clause_pairs)
            if clause_scores is not None:
                supported_clauses: set[tuple[int, int]] = set()
                score_lookup: dict[tuple[int, int, int], tuple[float, float]] = {}
                for (c_idx, s_idx, cl_idx), (p_ent, p_con) in zip(
                    clause_meta, clause_scores, strict=True
                ):
                    score_lookup[(c_idx, s_idx, cl_idx)] = (p_ent, p_con)
                    cid = candidates[c_idx].chunk_id
                    if (
                        p_ent >= entailment_min
                        and p_con < contradiction_max
                        and max_contra_by_cid[cid] < contradiction_max
                    ):
                        supported_clauses.add((s_idx, cl_idx))

                for (c_idx, s_idx, cl_idx), (p_ent, p_con) in zip(
                    clause_meta, clause_scores, strict=True
                ):
                    cid = candidates[c_idx].chunk_id
                    if not (
                        p_ent >= entailment_min
                        and p_con < contradiction_max
                        and max_contra_by_cid[cid] < contradiction_max
                    ):
                        continue
                    # Guard for 2-class NLI: reject if an unsupported sibling clause in the same
                    # sentence introduces ungrounded numbers on the same chunk topic.
                    c_norm_nums = set(re.findall(r"\d+", chunk_texts[cid].replace(",", "")))
                    c_toks = _extract_content_tokens(chunk_texts[cid])
                    has_conflicting_sibling = False
                    for sib_idx, sib_text in enumerate(clauses_by_sent.get(s_idx, [])):
                        if sib_idx == cl_idx or (s_idx, sib_idx) in supported_clauses:
                            continue
                        sib_nums = set(re.findall(r"\d+", sib_text.replace(",", "")))
                        sib_ent, sib_con = score_lookup.get((c_idx, s_idx, sib_idx), (0.0, 0.0))
                        if sib_con >= contradiction_max or (
                            bool(sib_nums - c_norm_nums)
                            and bool(_extract_content_tokens(sib_text) & c_toks)
                            and sib_ent < 0.15
                        ):
                            has_conflicting_sibling = True
                            break
                    if not has_conflicting_sibling:
                        accepted_scores[cid] = max(accepted_scores.get(cid, 0.0), p_ent)
                        sent_supported[s_idx] = True
                        sent_chunk_scores[s_idx][cid] = max(
                            sent_chunk_scores[s_idx].get(cid, 0.0), p_ent
                        )

    # Round 2B: Combined Top-2 Premise NLI for multi-hop synthesis across two chunks
    still_unsupported = [
        i
        for i, ok in enumerate(sent_supported)
        if not ok and len(_extract_content_tokens(sentences[i])) >= 3
    ]
    if still_unsupported and len(candidates) >= 2:
        multihop_pairs: list[tuple[str, str]] = []
        multihop_cands: list[tuple[int, DocumentChunk, DocumentChunk]] = []

        for s_idx in still_unsupported:
            sent = sentences[s_idx]
            ranked: list[tuple[float, DocumentChunk]] = []
            if sim_matrix is not None:
                ranked = [
                    (float(sim_matrix[s_idx, c_idx]), candidates[c_idx])
                    for c_idx in range(len(candidates))
                ]
            elif emb_model is not None:
                try:
                    s_vec = (
                        s_vecs[s_idx]
                        if (s_vecs is not None and s_idx < len(s_vecs))
                        else retriever._encode(emb_model, [sent])[0]
                    )
                    for ch in candidates:
                        c_vec = local_c_vecs.get(ch.chunk_id)
                        if c_vec is None:
                            c_vec = retriever._encode(emb_model, [chunk_texts[ch.chunk_id]])[0]
                            local_c_vecs[ch.chunk_id] = c_vec
                        sim = float(np.dot(c_vec, s_vec))
                        ranked.append((sim, ch))
                except Exception:
                    ranked = []

            if not ranked:
                ranked = [
                    (_lexical_overlap_score(sent, chunk_texts[ch.chunk_id]), ch)
                    for ch in candidates
                ]

            ranked.sort(key=lambda item: item[0], reverse=True)
            (sim1, top1), (sim2, top2) = ranked[0], ranked[1]
            if (
                sim1 >= _MULTIHOP_MIN_RETRIEVAL_SCORE
                and sim2 >= _MULTIHOP_MIN_RETRIEVAL_SCORE
                and max_contra_by_cid[top1.chunk_id] < contradiction_max
                and max_contra_by_cid[top2.chunk_id] < contradiction_max
            ):
                combined_premise = (
                    f"{chunk_texts[top1.chunk_id]}\n\n{chunk_texts[top2.chunk_id]}"
                )
                multihop_pairs.append((combined_premise, sent))
                multihop_cands.append((s_idx, top1, top2))

        if multihop_pairs:
            mh_scores = nli.score_pairs(multihop_pairs)
            if mh_scores is not None:
                for (s_idx, top1, top2), (p_ent, p_con) in zip(
                    multihop_cands, mh_scores, strict=True
                ):
                    if p_ent >= entailment_min and p_con < contradiction_max:
                        # Discount slightly vs direct single-chunk entailment so single-chunk
                        # primary ordering wins ties cleanly
                        mh_score = p_ent * 0.98
                        accepted_scores[top1.chunk_id] = max(
                            accepted_scores.get(top1.chunk_id, 0.0), mh_score
                        )
                        accepted_scores[top2.chunk_id] = max(
                            accepted_scores.get(top2.chunk_id, 0.0), mh_score * 0.99
                        )
                        sent_supported[s_idx] = True
                        sent_chunk_scores[s_idx][top1.chunk_id] = max(
                            sent_chunk_scores[s_idx].get(top1.chunk_id, 0.0), mh_score
                        )
                        sent_chunk_scores[s_idx][top2.chunk_id] = max(
                            sent_chunk_scores[s_idx].get(top2.chunk_id, 0.0), mh_score * 0.99
                        )

    cand_order = {c.chunk_id: idx for idx, c in enumerate(candidates)}
    cand_by_id = {c.chunk_id: c for c in candidates}
    sentence_citations: list[SentenceCitation] = []
    paragraph_entries: list[tuple[str, list[tuple[float, int, DocumentChunk]]]] = []

    for s_idx, sent_text in enumerate(sentences):
        scored_for_sent = [
            (score, cand_order[cid], cand_by_id[cid])
            for cid, score in sent_chunk_scores[s_idx].items()
            if max_contra_by_cid.get(cid, 0.0) < contradiction_max
        ]
        if scored_for_sent:
            sent_sources = _build_sentence_sources(sent_text, scored_for_sent)
            sentence_citations.append(
                SentenceCitation(
                    sentence_index=s_idx,
                    text=sent_text,
                    status="cited",
                    sources=sent_sources,
                )
            )
            paragraph_entries.append((sent_text, scored_for_sent))
        else:
            sentence_citations.append(
                SentenceCitation(
                    sentence_index=s_idx,
                    text=sent_text,
                    status="uncited",
                    sources=[],
                )
            )

    if not paragraph_entries or not accepted_scores:
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
            sources=[],
            sentences=sentence_citations,
        )

    sources = _build_paragraph_sources_from_sentences(paragraph_entries)
    primary = sources[0]

    return ParagraphCitation(
        paragraph=paragraph_index,
        heading=primary["heading"],
        page=primary["page"],
        status="cited",
        chunk_id=primary["chunk_id"],
        sources=sources,
        sentences=sentence_citations,
    )


def verify_paragraph_citation(
    paragraph_index: int,
    reported_chunk_ids: list[int],
    retrieved_chunks: list[DocumentChunk],
    *,
    paragraph_text: str | None = None,
    retriever: SemanticRetriever | None = None,
    nli_verifier: NLIVerifier | None = None,
    chunk_embeddings_by_id: dict[int, NDArray[np.float32]] | None = None,
    sentence_candidate_cids: list[set[int]] | None = None,
    sentence_embeddings: NDArray[np.float32] | None = None,
    min_support_score: float = 0.52,
    nli_entailment_min: float = _NLI_ENTAILMENT_MIN,
    nli_contradiction_max: float = _NLI_CONTRADICTION_MAX,
) -> ParagraphCitation:
    """Verify LLM-reported chunk IDs and semantic entailment support.

    Uses sentence/clause-level Cross-Encoder NLI (with Top-2 multi-hop fallback) when
    available, gracefully degrading to sentence-aware Bi-Encoder + lexical verification
    when NLI weights are unavailable or mocked in unit tests.
    """
    by_id = {c.chunk_id: c for c in retrieved_chunks}
    seen: set[int] = set()
    candidates: list[DocumentChunk] = []
    for cid in reported_chunk_ids:
        if cid in by_id and cid not in seen:
            seen.add(cid)
            candidates.append(by_id[cid])

    if not candidates:
        uncited_sents = (
            [
                SentenceCitation(sentence_index=i, text=s, status="uncited", sources=[])
                for i, s in enumerate(_split_paragraph_sentences(paragraph_text))
            ]
            if (paragraph_text and paragraph_text.strip())
            else []
        )
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
            sources=[],
            sentences=uncited_sents,
        )

    # Backward-compatible ID-only check when paragraph_text is not provided
    if paragraph_text is None or not paragraph_text.strip():
        chosen = candidates[0]
        src = _build_source_dict(chosen, _extract_best_excerpt("", chosen))
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=src["heading"],
            page=src["page"],
            status="cited",
            chunk_id=src["chunk_id"],
            sources=[src],
            sentences=[],
        )

    clean_para = paragraph_text.strip()

    # Fast-path for short verbatim inline fact slots (<=8 words, 1-4 content tokens)
    inline_matches = [
        chunk
        for chunk in candidates
        if _is_verbatim_inline_fact(clean_para, f"{chunk.heading}: {chunk.content}")
    ]
    if inline_matches:
        sentences = _split_paragraph_sentences(clean_para) or [clean_para]
        sentence_citations: list[SentenceCitation] = []
        sent_entries: list[tuple[str, list[tuple[float, int, DocumentChunk]]]] = []
        for s_idx, sent in enumerate(sentences):
            matched_scored = [
                (1.0, order_idx, ch)
                for order_idx, ch in enumerate(candidates)
                if _is_verbatim_inline_fact(sent, f"{ch.heading}: {ch.content}")
                or (len(sentences) == 1 and ch in inline_matches)
            ]
            if matched_scored:
                sent_sources = _build_sentence_sources(sent, matched_scored)
                sentence_citations.append(
                    SentenceCitation(
                        sentence_index=s_idx,
                        text=sent,
                        status="cited",
                        sources=sent_sources,
                    )
                )
                sent_entries.append((sent, matched_scored))
            else:
                sentence_citations.append(
                    SentenceCitation(
                        sentence_index=s_idx,
                        text=sent,
                        status="uncited",
                        sources=[],
                    )
                )
        para_sources = _build_paragraph_sources_from_sentences(sent_entries)
        if para_sources:
            primary = para_sources[0]
            return ParagraphCitation(
                paragraph=paragraph_index,
                heading=primary["heading"],
                page=primary["page"],
                status="cited",
                chunk_id=primary["chunk_id"],
                sources=para_sources,
                sentences=sentence_citations,
            )

    active_retriever = retriever or SemanticRetriever()
    active_nli = nli_verifier or NLIVerifier()
    nli_result = _verify_with_nli(
        paragraph_index=paragraph_index,
        clean_para=clean_para,
        candidates=candidates,
        nli=active_nli,
        retriever=active_retriever,
        chunk_embeddings_by_id=chunk_embeddings_by_id,
        entailment_min=nli_entailment_min,
        contradiction_max=nli_contradiction_max,
        sentence_candidate_cids=sentence_candidate_cids,
        sentence_embeddings=sentence_embeddings,
    )
    if nli_result is not None:
        return nli_result

    # Fallback path: sentence-aware Bi-Encoder cosine + lexical overlap
    model = active_retriever.get_model()
    sentences = _split_paragraph_sentences(clean_para)
    if not sentences:
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=None,
            page=None,
            status="uncited",
            chunk_id=None,
            sources=[],
            sentences=[],
        )

    sent_vecs: list[NDArray[np.float32]] | None = None
    chunk_vecs: dict[int, NDArray[np.float32]] = dict(chunk_embeddings_by_id or {})
    if model is not None:
        try:
            encoded = active_retriever._encode(model, sentences)
            sent_vecs = [encoded[i] for i in range(len(sentences))]
            for chunk in candidates:
                if chunk.chunk_id not in chunk_vecs:
                    chunk_vecs[chunk.chunk_id] = active_retriever._encode(
                        model, [f"{chunk.heading}: {chunk.content}"]
                    )[0]
        except Exception:
            sent_vecs = None

    min_lexical_support = min(0.25, min_support_score)
    sentence_citations = []
    paragraph_entries: list[tuple[str, list[tuple[float, int, DocumentChunk]]]] = []

    for s_idx, sent in enumerate(sentences):
        # Guard against multi-sentence greetings (e.g., "Good morning, everyone.") matching
        # a single incidental word in a chunk via verbatim-inline check.
        sent_tokens = _extract_content_tokens(sent)
        if not sent_tokens or (len(sentences) > 1 and len(sent_tokens) < 2):
            sentence_citations.append(
                SentenceCitation(sentence_index=s_idx, text=sent, status="uncited", sources=[])
            )
            continue

        scored_for_sent: list[tuple[float, int, DocumentChunk]] = []
        for order_idx, chunk in enumerate(candidates):
            chunk_full = f"{chunk.heading}: {chunk.content}"
            lex_score = _lexical_overlap_score(sent, chunk_full)
            if sent_vecs is not None:
                c_vec = chunk_vecs.get(chunk.chunk_id)
                sem_score = float(np.dot(c_vec, sent_vecs[s_idx])) if c_vec is not None else -1.0
                score = sem_score if lex_score >= min_lexical_support else -1.0
            else:
                score = lex_score
            if score >= min_support_score:
                scored_for_sent.append((score, order_idx, chunk))

        if scored_for_sent:
            sent_sources = _build_sentence_sources(sent, scored_for_sent)
            sentence_citations.append(
                SentenceCitation(
                    sentence_index=s_idx,
                    text=sent,
                    status="cited",
                    sources=sent_sources,
                )
            )
            paragraph_entries.append((sent, scored_for_sent))
        else:
            sentence_citations.append(
                SentenceCitation(
                    sentence_index=s_idx,
                    text=sent,
                    status="uncited",
                    sources=[],
                )
            )

    if paragraph_entries:
        para_sources = _build_paragraph_sources_from_sentences(paragraph_entries)
        primary = para_sources[0]
        return ParagraphCitation(
            paragraph=paragraph_index,
            heading=primary["heading"],
            page=primary["page"],
            status="cited",
            chunk_id=primary["chunk_id"],
            sources=para_sources,
            sentences=sentence_citations,
        )

    return ParagraphCitation(
        paragraph=paragraph_index,
        heading=None,
        page=None,
        status="uncited",
        chunk_id=None,
        sources=[],
        sentences=sentence_citations,
    )


def align_script_citations(
    script_text: str,
    chunks: list[DocumentChunk],
    existing_citations: list[ParagraphCitation] | None = None,
    *,
    reported_ids_by_para: dict[int, list[int]] | None = None,
    retriever: SemanticRetriever | None = None,
    nli_verifier: NLIVerifier | None = None,
    chunk_embeddings: NDArray[np.float32] | None = None,
    min_support_score: float = 0.52,
) -> list[ParagraphCitation]:
    """Align and verify citations for every paragraph of *script_text* against *chunks*.

    Evaluates LLM-reported chunk IDs (via *reported_ids_by_para* or *existing_citations*)
    plus per-sentence top retrieved candidates using a single batched Bi-Encoder pass so
    every sentence is verified against only its own relevant chunks.
    """
    if not chunks or not script_text or not script_text.strip():
        return list(existing_citations or [])

    paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
    if not paragraphs:
        return list(existing_citations or [])

    active_retriever = retriever or SemanticRetriever()
    active_nli = nli_verifier or NLIVerifier()
    if chunk_embeddings is not None and len(chunk_embeddings) == len(chunks):
        resolved_chunk_embeddings: NDArray[np.float32] | None = chunk_embeddings
    else:
        resolved_chunk_embeddings = active_retriever.encode_chunks(chunks)
    chunk_embeddings_by_id = (
        {c.chunk_id: resolved_chunk_embeddings[i] for i, c in enumerate(chunks)}
        if (resolved_chunk_embeddings is not None and len(resolved_chunk_embeddings) == len(chunks))
        else None
    )
    chunks_by_id = {c.chunk_id: c for c in chunks}
    existing_by_para = {
        c.paragraph: c for c in (existing_citations or []) if c.status == "cited"
    }
    candidate_min_score = min(_RETRIEVAL_MIN_SCORE, min_support_score)
    per_sent_min_score = min(0.20, candidate_min_score)

    para_sentences: list[list[str]] = [_split_paragraph_sentences(p) for p in paragraphs]

    # Single batched Bi-Encoder pass for all sentences across the entire script when real
    # embeddings are available — avoids O(sentences) separate encode() calls and enables
    # exact per-sentence candidate filtering before Cross-Encoder NLI.
    emb_model = active_retriever.get_model()
    use_batched_embs = (
        resolved_chunk_embeddings is not None
        and emb_model is not None
        and not type(emb_model).__name__.startswith("Mock")
    )
    para_sent_vecs: list[NDArray[np.float32] | None] = [None] * len(paragraphs)
    para_sent_sims: list[NDArray[np.float32] | None] = [None] * len(paragraphs)
    if use_batched_embs:
        flat_sents = [sent for sents in para_sentences for sent in sents]
        if flat_sents:
            try:
                all_sent_vecs = active_retriever._encode(emb_model, flat_sents)
                all_sims = all_sent_vecs @ resolved_chunk_embeddings.T  # type: ignore[union-attr]
                offset = 0
                for p_i, sents in enumerate(para_sentences):
                    n_s = len(sents)
                    if n_s:
                        para_sent_vecs[p_i] = all_sent_vecs[offset : offset + n_s]
                        para_sent_sims[p_i] = all_sims[offset : offset + n_s]
                        offset += n_s
            except Exception:
                use_batched_embs = False

    aligned: list[ParagraphCitation] = []
    for p_i, para_text in enumerate(paragraphs):
        idx = p_i + 1
        candidate_chunks: list[DocumentChunk] = []
        seen_cids: set[int] = set()
        prior_cids: set[int] = set()

        prev = existing_by_para.get(idx)
        if prev is not None:
            if prev.chunk_id is not None and prev.chunk_id in chunks_by_id:
                seen_cids.add(prev.chunk_id)
                prior_cids.add(prev.chunk_id)
                candidate_chunks.append(chunks_by_id[prev.chunk_id])
            for src in prev.sources:
                scid = src.get("chunk_id")
                if isinstance(scid, int) and scid in chunks_by_id and scid not in seen_cids:
                    seen_cids.add(scid)
                    prior_cids.add(scid)
                    candidate_chunks.append(chunks_by_id[scid])

        if reported_ids_by_para:
            for rcid in reported_ids_by_para.get(idx, ()):
                if isinstance(rcid, int) and rcid in chunks_by_id:
                    prior_cids.add(rcid)
                    if rcid not in seen_cids:
                        seen_cids.add(rcid)
                        candidate_chunks.append(chunks_by_id[rcid])

        sentences = para_sentences[p_i]
        sent_sims = para_sent_sims[p_i]
        sent_candidate_cids: list[set[int]] | None = None

        if use_batched_embs and sent_sims is not None and sentences:
            sent_candidate_cids = []
            top_k = max(3, _MAX_SOURCES_PER_SENTENCE)
            for s_idx in range(len(sentences)):
                row = sent_sims[s_idx]
                ranked_idx = np.argsort(row)[::-1]
                s_cids: set[int] = set()
                for c_pos in ranked_idx:
                    score = float(row[int(c_pos)])
                    if score < candidate_min_score:
                        break
                    ch = chunks[int(c_pos)]
                    s_cids.add(ch.chunk_id)
                    if ch.chunk_id not in seen_cids:
                        seen_cids.add(ch.chunk_id)
                        candidate_chunks.append(ch)
                    if len(s_cids) >= top_k:
                        break
                # Always include LLM-reported / prior chunks that meet minimum relevance for
                # this sentence (or all prior chunks on single-sentence paragraphs).
                for p_cid in prior_cids:
                    if p_cid in s_cids:
                        continue
                    c_pos_match = next(
                        (i for i, ch in enumerate(chunks) if ch.chunk_id == p_cid), None
                    )
                    if c_pos_match is not None and (
                        len(sentences) == 1 or float(row[c_pos_match]) >= per_sent_min_score
                    ):
                        s_cids.add(p_cid)
                sent_candidate_cids.append(s_cids)
        else:
            for ch in active_retriever.retrieve_top_k(
                para_text,
                chunks,
                k=max(3, _MAX_SOURCES_PER_SENTENCE),
                chunk_embeddings=resolved_chunk_embeddings,
                min_score=candidate_min_score,
            ):
                if ch.chunk_id not in seen_cids:
                    seen_cids.add(ch.chunk_id)
                    candidate_chunks.append(ch)

            if len(sentences) >= 2 and len(chunks) > len(candidate_chunks):
                for sent in sentences:
                    for ch in active_retriever.retrieve_top_k(
                        sent,
                        chunks,
                        k=_MAX_SOURCES_PER_SENTENCE,
                        chunk_embeddings=resolved_chunk_embeddings,
                        min_score=candidate_min_score,
                    ):
                        if ch.chunk_id not in seen_cids:
                            seen_cids.add(ch.chunk_id)
                            candidate_chunks.append(ch)

        citation = verify_paragraph_citation(
            paragraph_index=idx,
            reported_chunk_ids=[c.chunk_id for c in candidate_chunks],
            retrieved_chunks=candidate_chunks,
            paragraph_text=para_text,
            retriever=active_retriever,
            nli_verifier=active_nli,
            chunk_embeddings_by_id=chunk_embeddings_by_id,
            sentence_candidate_cids=sent_candidate_cids,
            sentence_embeddings=para_sent_vecs[p_i],
            min_support_score=min_support_score,
        )
        aligned.append(citation)
    return aligned
