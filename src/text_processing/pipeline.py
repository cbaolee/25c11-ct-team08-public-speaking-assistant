"""WP-B4 & WP-B5 (Member 3): 8-Stage Script Generation Pipeline, Cache, and Jobs.

Saved scripts live in the `scripts` table (`/api/scripts*` in src/app/main.py), not here.
"""

import hashlib
import logging
import re
import time
import uuid
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

from src.app.config import (
    citable_note_min_words,
    citation_min_support_score,
    free_topic_thesis_min_words,
    moderation_max_chunks,
    pipeline_cache_max_size,
    script_jobs_max_capacity,
)
from src.app.constants import CONSTANTS

from .chat_session import ChatSessionStore, append_to_context_window, chat_session_store
from .contracts import (
    ETA_BUFFER_S,
    DocumentChunk,
    GeneratedScript,
    JobStatus,
    ScriptGenerationError,
    ScriptGenerationRequest,
    ScriptJobState,
    compute_script_job_remaining_s,
    compute_script_job_total_s,
    default_script_job_steps,
)
from .generator import ScriptGenerator
from .moderation import ContentModerator
from .parser import (
    DocumentParserError,
    _split_long_chunk_text,
    parse_input_to_chunks,
    validate_pdf_file,
)
from .retrieval import SemanticRetriever, align_script_citations
from .sanitizer import sanitize_chunks, sanitize_text
from .source_classifier import extract_citable_source_text
from .template_engine import (
    TemplateEngine,
    polish_script_paragraphs,
    validate_assembled_script,
)
from .template_store import TemplateStore

logger = logging.getLogger(__name__)
_CITATION_MIN_SUPPORT_SCORE = float(citation_min_support_score)
_CITABLE_NOTE_MIN_WORDS = int(citable_note_min_words)
_FREE_TOPIC_THESIS_MIN_WORDS = int(free_topic_thesis_min_words)
DEFAULT_PIPELINE_CACHE_MAX_SIZE = int(pipeline_cache_max_size)
DEFAULT_SCRIPT_JOBS_CAPACITY = int(script_jobs_max_capacity)
_MODERATION_MAX_CHUNKS = int(moderation_max_chunks)
_AUTO_REGEN_FEEDBACK_PREFIX = "write a fresh variation of this speech"


def _normalize_note_key(text: str) -> str:
    """Normalize a chat note for msg_id lookup and deduplication."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _build_chat_note_chunks(
    notes: list[str],
    start_chunk_id: int = 1,
    min_words: int = 4,
    *,
    retriever: SemanticRetriever | None = None,
    note_msg_ids: dict[str, str] | None = None,
    initial_prompt_msg_id: str | None = None,
) -> list[DocumentChunk]:
    """Turn citable ``source_material`` user notes into in-memory chunks (``page=0``).

    Casual chat ("I'm happy", "thanks") and editing instructions ("make it shorter")
    are filtered out by ``extract_citable_source_text`` so they can never be cited,
    while mixed messages have non-source sentences stripped before chunking.
    """
    note_chunks: list[DocumentChunk] = []
    seen_notes: set[str] = set()
    note_num = 0
    for idx, raw_note in enumerate(notes):
        cleaned = sanitize_text(raw_note).strip()
        if not cleaned:
            continue
        source_only = extract_citable_source_text(cleaned, retriever=retriever)
        if not source_only or len(source_only.split()) < min_words:
            continue
        dedup_key = _normalize_note_key(source_only)
        if dedup_key in seen_notes:
            continue
        seen_notes.add(dedup_key)
        norm_cleaned = _normalize_note_key(cleaned)
        matched_msg_id: str | None = None
        if note_msg_ids:
            matched_msg_id = note_msg_ids.get(norm_cleaned) or note_msg_ids.get(dedup_key)
        if matched_msg_id is None and idx == 0 and initial_prompt_msg_id:
            matched_msg_id = initial_prompt_msg_id
        note_num += 1
        lines = [ln.strip() for ln in source_only.splitlines() if ln.strip()]
        label = f"Chat note #{note_num}"
        if len(lines) > 1:
            first_line = re.sub(r"^[#*\-\s]+|[:.\s]+$", "", lines[0]).strip()
            if 1 <= len(first_line.split()) <= 5 and len(first_line) <= 36:
                label = f"Chat note #{note_num} · {first_line}"
        for part in _split_long_chunk_text(source_only):
            note_chunks.append(
                DocumentChunk(
                    chunk_id=start_chunk_id + len(note_chunks),
                    heading=label,
                    page=0,
                    content=part,
                    source_kind="chat",
                    source_msg_id=matched_msg_id,
                    source_file=None,
                )
            )
    return note_chunks


class ScriptGenerationPipeline:
    """End-to-end coordinator for the 8-stage Script Generation workflow (Brief §5.2)."""

    def __init__(
        self,
        template_store: TemplateStore | None = None,
        moderator: ContentModerator | None = None,
        template_engine: TemplateEngine | None = None,
        llm_generator: ScriptGenerator | None = None,
        session_store: ChatSessionStore | None = None,
        max_cache_size: int = DEFAULT_PIPELINE_CACHE_MAX_SIZE,
    ) -> None:
        if template_store is None:
            store = TemplateStore()
            store.load()
            self.template_store = store
        else:
            self.template_store = template_store
        self.moderator = moderator if moderator is not None else ContentModerator()
        self.template_engine = (
            template_engine if template_engine is not None else TemplateEngine()
        )
        self.llm_generator = (
            llm_generator if llm_generator is not None else ScriptGenerator()
        )
        self.session_store = (
            session_store if session_store is not None else chat_session_store
        )
        self.max_cache_size = max_cache_size
        self.max_jobs_capacity = DEFAULT_SCRIPT_JOBS_CAPACITY
        self._jobs: OrderedDict[str, ScriptJobState] = OrderedDict()
        self._active_since: dict[str, float] = {}  # job_id -> created or first seen active
        self._cache: OrderedDict[str, GeneratedScript] = OrderedDict()

    def _evict_jobs_if_needed(self) -> None:
        """Evict oldest finished jobs when self._jobs exceeds max capacity (128)."""
        while len(self._jobs) > self.max_jobs_capacity:
            finished_keys = [
                jid for jid, j in self._jobs.items() if j.status in ("completed", "failed")
            ]
            if finished_keys:
                del self._jobs[finished_keys[0]]
            else:
                self._jobs.popitem(last=False)

    def create_job(self, user_id: str = "anonymous", duration_min: int = 5) -> ScriptJobState:
        """Create and register a new background job state in memory (Brief §5.5)."""
        job_id = str(uuid.uuid4())
        total_s = compute_script_job_total_s(duration_min, ETA_BUFFER_S)
        job = ScriptJobState(
            job_id=job_id,
            user_id=user_id,
            status="queued",
            progress=0,
            stage="queued",
            steps=default_script_job_steps(),
            eta_buffer_s=ETA_BUFFER_S,
            duration_min=duration_min,
            estimated_total_s=total_s,
            estimated_remaining_s=total_s,
        )
        self._jobs[job_id] = job
        self._active_since[job_id] = time.monotonic()
        self._evict_jobs_if_needed()
        return job

    def get_job(self, job_id: str) -> ScriptJobState | None:
        """Look up an in-memory job by `job_id`."""
        return self._jobs.get(job_id)

    def _update_job(
        self,
        job_id: str | None,
        status: JobStatus,
        progress: int,
        *,
        stage: str | None = None,
    ) -> None:
        if job_id and job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = status
            job.progress = progress
            active_stage = stage or status
            job.stage = active_stage
            found_target = False
            for step in job.steps:
                if step["key"] == active_stage:
                    step["state"] = "running"
                    found_target = True
                elif not found_target:
                    step["state"] = "done"
                elif step["state"] == "running":
                    step["state"] = "done"
            job.estimated_remaining_s = compute_script_job_remaining_s(
                job.steps, job.duration_min, job.eta_buffer_s
            )

    def _resolve_compaction_client(self):
        client = getattr(self.template_engine, "client", None)
        if client is not None:
            return client
        if (
            isinstance(self.llm_generator, ScriptGenerator)
            and self.llm_generator.client is not None
        ):
            return self.llm_generator.client
        return None

    @staticmethod
    def _build_cache_key(
        request: ScriptGenerationRequest,
        chunks: list[DocumentChunk],
        chat_context: str | None = None,
    ) -> str:
        chunk_text = "\n".join(
            f"{c.page}:{c.heading}:{c.source_kind}:"
            f"{c.source_msg_id or ''}:{c.source_file or ''}:{c.content}"
            for c in chunks
        )
        effective_chat = (
            chat_context if chat_context is not None else (request.chat_context or "")
        ).strip()
        raw = "|".join(
            [
                request.user_id.strip(),
                request.topic.strip().lower(),
                (request.category or "").strip().lower(),
                str(request.duration_min),
                (request.greeting or "").strip(),
                chunk_text,
                (request.user_feedback or "").strip().lower(),
                effective_chat.lower(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def run(self, request: ScriptGenerationRequest, job_id: str | None = None) -> GeneratedScript:
        """Execute stages 1 through 8 synchronously with LRU cache and post-validation."""
        self._update_job(job_id, "extracting", 10, stage="validating_input")
        if not request.topic or not request.topic.strip():
            raise ScriptGenerationError(
                "output_invalid", "Topic must not be empty.", status_code=422
            )

        # Stage 1, 2, 3: Validate, Parse, and Sanitize input document (if provided)
        self._update_job(job_id, "extracting", 25, stage="extracting")
        chunks: list[DocumentChunk] = []
        chat_parts: list[str] = []
        citable_notes: list[str] = []
        note_msg_ids: dict[str, str] = {}
        prompt_msg_id_for_chunks: str | None = None
        force_free_topic = False
        sess = None
        pending_feedback_note: str | None = None
        if request.session_id:
            sess = self.session_store.get(request.session_id, user_id=request.user_id)
            if sess:
                force_free_topic = sess.selected_template_id is None
                if sess.chunks:
                    chunks.extend(sess.chunks)
                if sess.initial_prompt and sess.initial_prompt.strip():
                    cleaned_prompt = sanitize_text(sess.initial_prompt).strip()
                    if cleaned_prompt:
                        chat_parts.append(cleaned_prompt)
                        citable_notes.append(cleaned_prompt)
                        sess_prompt_msg_id = getattr(sess, "initial_prompt_msg_id", None)
                        if sess_prompt_msg_id:
                            prompt_msg_id_for_chunks = sess_prompt_msg_id
                            note_msg_ids[_normalize_note_key(cleaned_prompt)] = sess_prompt_msg_id
                raw_note_msg_ids = getattr(sess, "user_note_msg_ids", None)
                if isinstance(raw_note_msg_ids, dict):
                    for norm_k, msg_id_val in raw_note_msg_ids.items():
                        if norm_k and msg_id_val:
                            note_msg_ids[norm_k] = msg_id_val
                # Dual-Track storage separation:
                # Track 1 (chat_parts -> effective_chat_context): bounded context_window +
                # compacted_summary for LLM prompting within token limits.
                if getattr(sess, "compacted_summary", "") and sess.compacted_summary.strip():
                    cleaned_summary = sanitize_text(sess.compacted_summary).strip()
                    if cleaned_summary:
                        chat_parts.append(f"[Session Summary]\n{cleaned_summary}")
                if getattr(sess, "context_window", None):
                    for entry in sess.context_window:
                        cleaned_entry = sanitize_text(entry.text).strip()
                        if cleaned_entry:
                            chat_parts.append(cleaned_entry)
                elif sess.user_notes:
                    for note in sess.user_notes:
                        cleaned_note = sanitize_text(note).strip()
                        if cleaned_note:
                            chat_parts.append(cleaned_note)
                # Track 2 (citable_notes -> source_classifier -> NLI chunks): verbatim raw
                # user_notes only; compacted_summary and file_summary entries never enter here.
                if sess.user_notes:
                    for note in sess.user_notes:
                        cleaned_note = sanitize_text(note).strip()
                        if cleaned_note:
                            citable_notes.append(cleaned_note)
                elif getattr(sess, "context_window", None):
                    for entry in sess.context_window:
                        if getattr(entry, "source", "chat") == "file_summary":
                            continue
                        cleaned_entry = sanitize_text(entry.text).strip()
                        if cleaned_entry:
                            citable_notes.append(cleaned_entry)
        if request.user_feedback and request.user_feedback.strip():
            cleaned_fb = sanitize_text(request.user_feedback).strip()
            is_auto_regen = cleaned_fb.lower().startswith(_AUTO_REGEN_FEEDBACK_PREFIX)
            if cleaned_fb and not is_auto_regen:
                if not chat_parts or chat_parts[-1] != cleaned_fb:
                    chat_parts.append(cleaned_fb)
                    citable_notes.append(cleaned_fb)
                    if request.feedback_msg_id:
                        note_msg_ids[_normalize_note_key(cleaned_fb)] = request.feedback_msg_id
                    if sess is not None:
                        pending_feedback_note = cleaned_fb
        if request.chat_context and request.chat_context.strip():
            cleaned_ctx = sanitize_text(request.chat_context).strip()
            if cleaned_ctx:
                chat_parts.append(cleaned_ctx)
                citable_notes.append(cleaned_ctx)
        effective_chat_context = "\n".join(chat_parts).strip() or None

        if request.pdf_path or request.raw_text:
            try:
                if request.pdf_path:
                    validate_pdf_file(request.pdf_path)
                raw_chunks = parse_input_to_chunks(
                    pdf_path=request.pdf_path,
                    raw_text=request.raw_text,
                )
                sanitized = sanitize_chunks(raw_chunks)
                if not sanitized and not chunks:
                    raise ScriptGenerationError(
                        error_code="no_text_layer",
                        message="No extractable text found in the provided document.",
                        status_code=422,
                    )
                id_offset = len(chunks)
                for idx, chunk in enumerate(sanitized, start=1):
                    chunk.chunk_id = id_offset + idx
                chunks.extend(sanitized)
            except DocumentParserError as exc:
                no_text = exc.error_code in ("empty_pdf", "no_text_layer")
                error_code = "no_text_layer" if no_text else "invalid_pdf"
                raise ScriptGenerationError(
                    error_code=error_code,
                    message=exc.message,
                    status_code=422,
                ) from exc

        if citable_notes:
            active_retriever = getattr(self.template_engine, "retriever", None) or getattr(
                self.llm_generator, "retriever", None
            )
            note_chunks = _build_chat_note_chunks(
                citable_notes,
                start_chunk_id=len(chunks) + 1,
                retriever=active_retriever,
                note_msg_ids=note_msg_ids or None,
                initial_prompt_msg_id=prompt_msg_id_for_chunks,
            )
            chunks.extend(note_chunks)

        # Stage 4: Content Moderation on topic, greeting, user_feedback, chat_context, and chunks
        self._update_job(job_id, "moderating", 40, stage="moderating")
        parts = [sanitize_text(request.topic)]
        if request.greeting:
            parts.append(sanitize_text(request.greeting))
        if request.user_feedback:
            parts.append(sanitize_text(request.user_feedback))
        if effective_chat_context:
            parts.append(effective_chat_context)
        parts.extend(c.content for c in chunks[:_MODERATION_MAX_CHUNKS])
        self.moderator.assert_safe("\n".join(parts), user_id=request.user_id)

        # Persist safe Regenerate prompt into bounded context window so context accumulates safely
        if sess is not None and pending_feedback_note:
            append_to_context_window(
                sess,
                pending_feedback_note,
                turn=sess.gather_turns + 1,
                source="feedback",
                msg_id=request.feedback_msg_id,
                client=self._resolve_compaction_client(),
                limiter=getattr(self.template_engine, "limiter", None),
            )
            self.session_store.put(sess)

        # Check LRU cache (D-10)
        cache_key = self._build_cache_key(request, chunks, chat_context=effective_chat_context)
        if cache_key in self._cache:
            self._update_job(job_id, "generating", 90, stage="validating_output")
            self._cache.move_to_end(cache_key)
            return deepcopy(self._cache[cache_key])

        # Stage 5 & 6: Route between Template Branch (6T) and Free-Topic LLM Branch (6L)
        self._update_job(job_id, "generating", 60, stage="generating")
        template_doc = None
        if (
            not force_free_topic
            and request.category
            and request.category.strip().lower() != "free"
        ):
            template_doc = self.template_store.get(request.topic)
            if template_doc is not None:
                cat_norm = request.category.strip().lower()
                if cat_norm not in (
                    template_doc.metadata.category.lower(),
                    template_doc.metadata.category_slug.lower(),
                ):
                    template_doc = None

        # Reuse precomputed session chunk embeddings (encoding only any newly appended tail chunks)
        reusable_chunk_embeddings = None
        if chunks:
            active_emb_retriever = getattr(self.template_engine, "retriever", None) or getattr(
                self.llm_generator, "retriever", None
            )
            sess_embs = getattr(sess, "chunk_embeddings", None) if sess is not None else None
            sess_n = len(sess.chunks) if (sess is not None and sess.chunks) else 0
            if sess_embs is not None and sess_n > 0 and len(sess_embs) == sess_n:
                if len(chunks) == sess_n:
                    reusable_chunk_embeddings = sess_embs
                elif len(chunks) > sess_n and active_emb_retriever is not None:
                    tail_embs = active_emb_retriever.encode_chunks(chunks[sess_n:])
                    if tail_embs is not None and len(tail_embs) == len(chunks) - sess_n:
                        import numpy as np

                        reusable_chunk_embeddings = np.vstack([sess_embs, tail_embs])
            elif active_emb_retriever is not None:
                reusable_chunk_embeddings = active_emb_retriever.encode_chunks(chunks)

        if template_doc is not None:
            kwargs: dict[str, object] = {}
            if request.user_feedback:
                kwargs["user_feedback"] = request.user_feedback
            if effective_chat_context:
                kwargs["chat_context"] = effective_chat_context
            template_reported_ids: dict[int, list[int]] = {}
            try:
                result = self.template_engine.fill_template(
                    template_doc,
                    chunks=chunks or None,
                    verify_citations=False,
                    chunk_embeddings=reusable_chunk_embeddings,
                    out_reported_ids=template_reported_ids,
                    **kwargs,
                )
            except TypeError:
                try:
                    result = self.template_engine.fill_template(
                        template_doc, chunks=chunks or None, **kwargs
                    )
                except TypeError:
                    result = self.template_engine.fill_template(
                        template_doc, chunks=chunks or None
                    )

            client = getattr(self.template_engine, "client", None)
            if client is None:
                try:
                    from .template_engine import _get_groq_client

                    client = _get_groq_client()
                except Exception:
                    pass
            model_chain = getattr(self.template_engine, "model_chain", None)
            if model_chain is None:
                try:
                    from .template_engine import _get_model_chain

                    model_chain = _get_model_chain()
                except Exception:
                    pass
            limiter = getattr(self.template_engine, "limiter", None)
            try:
                polished = polish_script_paragraphs(
                    result.script,
                    request.topic,
                    client=client,
                    model_chain=model_chain,
                    limiter=limiter,
                    chat_context=effective_chat_context,
                    user_feedback=request.user_feedback,
                )
                if polished and polished.strip() and polished != result.script:
                    result.script = polished
                    result.word_count = len(polished.split())
            except Exception as exc:
                logger.warning("Failed to polish script paragraphs: %s", exc)

            if chunks:
                retriever = getattr(self.template_engine, "retriever", None)
                result.citations = align_script_citations(
                    result.script,
                    chunks,
                    result.citations,
                    reported_ids_by_para=template_reported_ids or None,
                    retriever=retriever,
                    chunk_embeddings=reusable_chunk_embeddings,
                    min_support_score=_CITATION_MIN_SUPPORT_SCORE,
                )
                if any(c.status == "uncited" for c in result.citations):
                    if "uncited" not in result.flags:
                        result.flags.append("uncited")
                elif "uncited" in result.flags:
                    result.flags.remove("uncited")
        else:
            kwargs = {}
            if request.user_feedback:
                kwargs["user_feedback"] = request.user_feedback
            if effective_chat_context:
                kwargs["chat_context"] = effective_chat_context
            try:
                result = self.llm_generator.generate_free_topic_script(
                    topic=request.topic,
                    duration_min=request.duration_min,
                    chunks=chunks or None,
                    greeting=request.greeting,
                    chunk_embeddings=reusable_chunk_embeddings,
                    **kwargs,
                )
            except TypeError:
                try:
                    result = self.llm_generator.generate_free_topic_script(
                        topic=request.topic,
                        duration_min=request.duration_min,
                        chunks=chunks or None,
                        greeting=request.greeting,
                        **kwargs,
                    )
                except TypeError:
                    result = self.llm_generator.generate_free_topic_script(
                        topic=request.topic,
                        duration_min=request.duration_min,
                        chunks=chunks or None,
                        greeting=request.greeting,
                    )

        # Stage 7: Post-validation and 20-minute script audio-limit warning
        self._update_job(job_id, "generating", 90, stage="validating_output")
        eff_duration = result.duration_min or request.duration_min
        issues = validate_assembled_script(result.script, eff_duration)
        if "unresolved_slots" in issues:
            raise ScriptGenerationError(
                "output_invalid",
                "Generated script contains unresolved template placeholders.",
                status_code=422,
            )
        if any(i.startswith("word_count_out_of_range") for i in issues):
            if "word_count_adjusted" not in result.flags:
                result.flags.append("word_count_adjusted")
        if eff_duration == 20:
            if "audio_limit_warning" not in result.flags:
                result.flags.append("audio_limit_warning")
            result.warnings.append(
                "20-minute scripts read slowly may approach the 32-minute evaluation audio limit."
            )

        # Stage 8: Store in LRU cache and return
        self._cache[cache_key] = deepcopy(result)
        if len(self._cache) > self.max_cache_size:
            self._cache.popitem(last=False)
        return result

    def run_job(
        self,
        job_id: str,
        request: ScriptGenerationRequest,
        cleanup_pdf: bool = False,
    ) -> ScriptJobState:
        """Execute `run()` for an in-memory job and record completion or error state."""
        job = self._jobs.get(job_id)
        if job is None:
            total_s = compute_script_job_total_s(request.duration_min, ETA_BUFFER_S)
            job = ScriptJobState(
                job_id=job_id,
                user_id=request.user_id,
                duration_min=request.duration_min,
                estimated_total_s=total_s,
                estimated_remaining_s=total_s,
            )
            self._jobs[job_id] = job
            self._evict_jobs_if_needed()
        try:
            result = self.run(request, job_id=job_id)
            for step in job.steps:
                if step["state"] in ("pending", "running"):
                    step["state"] = "done"
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100
            job.estimated_remaining_s = 0.0
            job.result = result
        except ScriptGenerationError as exc:
            job.status = "failed"
            job.stage = "failed"
            job.estimated_remaining_s = 0.0
            job.error_code = exc.error_code
            job.error_message = exc.message
        except Exception as exc:
            job.status = "failed"
            job.stage = "failed"
            job.estimated_remaining_s = 0.0
            job.error_code = "generation_unavailable"
            job.error_message = str(exc)
        finally:
            if cleanup_pdf and request.pdf_path:
                Path(request.pdf_path).unlink(missing_ok=True)
        return job

    def has_active_job(self, user_id: str, *, now: float | None = None) -> bool:
        """True while `user_id` has a queued or running job in this process.

        A job created `active_job_stale_s` or more ago is ignored as stuck. A job without a
        creation time (not made by `create_job`) is timed from the first call that sees it.
        """
        now = time.monotonic() if now is None else now
        stale_s = CONSTANTS["script_limits"]["active_job_stale_s"]
        # `_jobs` has no lock and worker threads change job states, so read a snapshot. The
        # answer can be out of date at once and knows nothing about other processes.
        active = {
            job.job_id: job.user_id
            for job in tuple(self._jobs.values())
            if job.status in ("queued", "extracting", "moderating", "generating")
        }
        self._active_since = {jid: self._active_since.get(jid, now) for jid in active}
        return any(
            owner == user_id and now - self._active_since[jid] < stale_s
            for jid, owner in active.items()
        )
