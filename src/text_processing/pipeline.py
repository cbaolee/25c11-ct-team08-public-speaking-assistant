"""WP-B4 & WP-B5 (Member 3): 8-Stage Script Generation Pipeline, Cache, and Jobs.

Saved scripts live in the `scripts` table (`/api/scripts*` in src/app/main.py), not here.
"""

import hashlib
import logging
import re
import uuid
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

from src.app.constants import CONSTANTS

from .chat_session import ChatSessionStore, chat_session_store
from .contracts import (
    DocumentChunk,
    GeneratedScript,
    JobStatus,
    ScriptGenerationError,
    ScriptGenerationRequest,
    ScriptJobState,
)
from .generator import ScriptGenerator
from .moderation import ContentModerator
from .parser import DocumentParserError, parse_input_to_chunks, validate_pdf_file
from .retrieval import align_script_citations
from .sanitizer import sanitize_chunks, sanitize_text
from .template_engine import (
    TemplateEngine,
    polish_script_paragraphs,
    validate_assembled_script,
)
from .template_store import TemplateStore

logger = logging.getLogger(__name__)
_CITATION_MIN_SUPPORT_SCORE = float(CONSTANTS["script"].get("citation_min_support_score", 0.52))
_AUTO_REGEN_FEEDBACK_PREFIX = "write a fresh variation of this speech"


def _build_chat_note_chunks(
    notes: list[str],
    start_chunk_id: int = 1,
    min_words: int = 8,
) -> list[DocumentChunk]:
    """Turn substantive user chat notes into in-memory citable chunks (`page=0`)."""
    note_chunks: list[DocumentChunk] = []
    note_num = 0
    for raw_note in notes:
        cleaned = sanitize_text(raw_note).strip()
        if len(cleaned.split()) < min_words:
            continue
        note_num += 1
        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
        label = f"Chat note #{note_num}"
        if len(lines) > 1:
            first_line = re.sub(r"^[#*\-\s]+|[:.\s]+$", "", lines[0]).strip()
            if 1 <= len(first_line.split()) <= 5 and len(first_line) <= 36:
                label = f"Chat note #{note_num} · {first_line}"
        note_chunks.append(
            DocumentChunk(
                chunk_id=start_chunk_id + len(note_chunks),
                heading=label,
                page=0,
                content=cleaned,
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
        max_cache_size: int = 64,
    ) -> None:
        if template_store is None:
            store = TemplateStore()
            store.load()
            self.template_store = store
        else:
            self.template_store = template_store
        self.moderator = moderator or ContentModerator()
        self.template_engine = template_engine or TemplateEngine()
        self.llm_generator = llm_generator or ScriptGenerator()
        self.session_store = session_store or chat_session_store
        self.max_cache_size = max_cache_size
        self.max_jobs_capacity = 128
        self._jobs: OrderedDict[str, ScriptJobState] = OrderedDict()
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

    def create_job(self, user_id: str = "anonymous") -> ScriptJobState:
        """Create and register a new background job state in memory (Brief §5.5)."""
        job_id = str(uuid.uuid4())
        job = ScriptJobState(job_id=job_id, user_id=user_id, status="queued", progress=0)
        self._jobs[job_id] = job
        self._evict_jobs_if_needed()
        return job

    def get_job(self, job_id: str) -> ScriptJobState | None:
        """Look up an in-memory job by `job_id`."""
        return self._jobs.get(job_id)

    def _update_job(self, job_id: str | None, status: JobStatus, progress: int) -> None:
        if job_id and job_id in self._jobs:
            job = self._jobs[job_id]
            job.status = status
            job.progress = progress

    @staticmethod
    def _build_cache_key(
        request: ScriptGenerationRequest,
        chunks: list[DocumentChunk],
        chat_context: str | None = None,
    ) -> str:
        chunk_text = "\n".join(f"{c.page}:{c.heading}:{c.content}" for c in chunks)
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
        if not request.topic or not request.topic.strip():
            raise ScriptGenerationError(
                "output_invalid", "Topic must not be empty.", status_code=422
            )

        # Stage 1, 2, 3: Validate, Parse, and Sanitize input document (if provided)
        self._update_job(job_id, "extracting", 15)
        chunks: list[DocumentChunk] = []
        chat_parts: list[str] = []
        citable_notes: list[str] = []
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
                        if len(cleaned_prompt.split()) >= 15:
                            citable_notes.append(cleaned_prompt)
                if sess.user_notes:
                    for note in sess.user_notes:
                        cleaned_note = sanitize_text(note).strip()
                        if cleaned_note:
                            chat_parts.append(cleaned_note)
                            citable_notes.append(cleaned_note)
        if request.user_feedback and request.user_feedback.strip():
            cleaned_fb = sanitize_text(request.user_feedback).strip()
            is_auto_regen = cleaned_fb.lower().startswith(_AUTO_REGEN_FEEDBACK_PREFIX)
            if cleaned_fb and not is_auto_regen:
                if not chat_parts or chat_parts[-1] != cleaned_fb:
                    chat_parts.append(cleaned_fb)
                    citable_notes.append(cleaned_fb)
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
            note_chunks = _build_chat_note_chunks(
                citable_notes,
                start_chunk_id=len(chunks) + 1,
            )
            chunks.extend(note_chunks)

        # Stage 4: Content Moderation on topic, greeting, user_feedback, chat_context, and chunks
        self._update_job(job_id, "moderating", 35)
        parts = [sanitize_text(request.topic)]
        if request.greeting:
            parts.append(sanitize_text(request.greeting))
        if request.user_feedback:
            parts.append(sanitize_text(request.user_feedback))
        if effective_chat_context:
            parts.append(effective_chat_context)
        parts.extend(c.content for c in chunks[:20])
        self.moderator.assert_safe("\n".join(parts), user_id=request.user_id)

        # Persist safe Regenerate prompt into session notes so context accumulates across turns
        if sess is not None and pending_feedback_note:
            sess.user_notes.append(pending_feedback_note)
            self.session_store.put(sess)

        # Check LRU cache (D-10)
        cache_key = self._build_cache_key(request, chunks, chat_context=effective_chat_context)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return deepcopy(self._cache[cache_key])

        # Stage 5 & 6: Route between Template Branch (6T) and Free-Topic LLM Branch (6L)
        self._update_job(job_id, "generating", 65)
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

        if template_doc is not None:
            kwargs: dict[str, str] = {}
            if request.user_feedback:
                kwargs["user_feedback"] = request.user_feedback
            if effective_chat_context:
                kwargs["chat_context"] = effective_chat_context
            try:
                result = self.template_engine.fill_template(
                    template_doc, chunks=chunks or None, **kwargs
                )
            except TypeError:
                result = self.template_engine.fill_template(template_doc, chunks=chunks or None)

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
                    retriever=retriever,
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
                    **kwargs,
                )
            except TypeError:
                result = self.llm_generator.generate_free_topic_script(
                    topic=request.topic,
                    duration_min=request.duration_min,
                    chunks=chunks or None,
                    greeting=request.greeting,
                )

        # Stage 7: Post-validation and D-13 20-minute audio evaluation warning
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
                "20-minute scripts may approach the 22-minute (1320s) evaluation audio limit."
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
            job = ScriptJobState(job_id=job_id, user_id=request.user_id)
            self._jobs[job_id] = job
            self._evict_jobs_if_needed()
        try:
            result = self.run(request, job_id=job_id)
            job.status = "completed"
            job.progress = 100
            job.result = result
        except ScriptGenerationError as exc:
            job.status = "failed"
            job.error_code = exc.error_code
            job.error_message = exc.message
        except Exception as exc:
            job.status = "failed"
            job.error_code = "generation_unavailable"
            job.error_message = str(exc)
        finally:
            if cleanup_pdf and request.pdf_path:
                Path(request.pdf_path).unlink(missing_ok=True)
        return job
