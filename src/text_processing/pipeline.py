"""WP-B4 & WP-B5 (Member 3): 8-Stage Script Generation Pipeline, Cache, Jobs, and Script Store."""

import hashlib
import uuid
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any

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
from .sanitizer import sanitize_chunks, sanitize_text
from .template_engine import TemplateEngine, validate_assembled_script
from .template_store import TemplateStore


class ScriptGenerationPipeline:
    """End-to-end coordinator for the 8-stage Script Generation workflow (Brief §5.2)."""

    def __init__(
        self,
        template_store: TemplateStore | None = None,
        moderator: ContentModerator | None = None,
        template_engine: TemplateEngine | None = None,
        llm_generator: ScriptGenerator | None = None,
        max_cache_size: int = 64,
        max_scripts_per_user: int = 50,
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
        self.max_cache_size = max_cache_size
        self.max_scripts_per_user = max_scripts_per_user
        self._jobs: dict[str, ScriptJobState] = {}
        self._cache: OrderedDict[str, GeneratedScript] = OrderedDict()
        self._saved_scripts: dict[str, dict[str, Any]] = {}

    def create_job(self, user_id: str = "anonymous") -> ScriptJobState:
        """Create and register a new background job state in memory (Brief §5.5)."""
        job_id = str(uuid.uuid4())
        job = ScriptJobState(job_id=job_id, user_id=user_id, status="queued", progress=0)
        self._jobs[job_id] = job
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
    def _build_cache_key(request: ScriptGenerationRequest, chunks: list[DocumentChunk]) -> str:
        chunk_text = "\n".join(f"{c.page}:{c.heading}:{c.content}" for c in chunks)
        raw = "|".join(
            [
                request.user_id.strip(),
                request.topic.strip().lower(),
                (request.category or "").strip().lower(),
                str(request.duration_min),
                (request.greeting or "").strip(),
                chunk_text,
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
        if request.pdf_path or request.raw_text:
            try:
                if request.pdf_path:
                    validate_pdf_file(request.pdf_path)
                raw_chunks = parse_input_to_chunks(
                    pdf_path=request.pdf_path,
                    raw_text=request.raw_text,
                )
                chunks = sanitize_chunks(raw_chunks)
                if not chunks:
                    raise ScriptGenerationError(
                        error_code="no_text_layer",
                        message="No extractable text found in the provided document.",
                        status_code=422,
                    )
            except DocumentParserError as exc:
                no_text = exc.error_code in ("empty_pdf", "no_text_layer")
                error_code = "no_text_layer" if no_text else "invalid_pdf"
                raise ScriptGenerationError(
                    error_code=error_code,
                    message=exc.message,
                    status_code=422,
                ) from exc

        # Stage 4: Content Moderation on topic, greeting, and extracted chunks
        self._update_job(job_id, "moderating", 35)
        parts = [sanitize_text(request.topic)]
        if request.greeting:
            parts.append(sanitize_text(request.greeting))
        parts.extend(c.content for c in chunks[:20])
        self.moderator.assert_safe("\n".join(parts), user_id=request.user_id)

        # Check LRU cache (D-10)
        cache_key = self._build_cache_key(request, chunks)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return deepcopy(self._cache[cache_key])

        # Stage 5 & 6: Route between Template Branch (6T) and Free-Topic LLM Branch (6L)
        self._update_job(job_id, "generating", 65)
        template_doc = self.template_store.get(request.topic)
        if template_doc is not None and request.category:
            cat_norm = request.category.strip().lower()
            if cat_norm not in (
                template_doc.metadata.category.lower(),
                template_doc.metadata.category_slug.lower(),
            ):
                template_doc = None

        if template_doc is not None:
            result = self.template_engine.fill_template(template_doc, chunks=chunks or None)
        else:
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

    def save_script(
        self,
        user_id: str,
        title: str,
        script: str,
        duration_min: int | None = None,
        source: str = "user",
    ) -> dict[str, Any]:
        """Moderate and save a script under `user_id` with per-user cap (D-08, Brief §5.8)."""
        clean_title = sanitize_text(title).strip() or "Untitled Script"
        clean_script = sanitize_text(script).strip()
        if not clean_script:
            raise ScriptGenerationError("output_invalid", "Script text must not be empty.", 422)
        self.moderator.assert_safe(f"{clean_title}\n{clean_script}", user_id=user_id)
        user_items = [s for s in self._saved_scripts.values() if s["user_id"] == user_id]
        if len(user_items) >= self.max_scripts_per_user:
            raise ScriptGenerationError(
                "rate_limited",
                f"Maximum saved scripts limit ({self.max_scripts_per_user}) reached.",
                status_code=429,
            )
        script_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": script_id,
            "user_id": user_id,
            "title": clean_title,
            "script": clean_script,
            "word_count": len(clean_script.split()),
            "duration_min": duration_min,
            "source": source,
        }
        self._saved_scripts[script_id] = entry
        return dict(entry)

    def list_scripts(self, user_id: str) -> list[dict[str, Any]]:
        """List saved scripts belonging exclusively to `user_id`."""
        return [dict(s) for s in self._saved_scripts.values() if s["user_id"] == user_id]

    def get_script(self, script_id: str, user_id: str) -> dict[str, Any] | None:
        """Return saved script if owned by `user_id`, else None."""
        item = self._saved_scripts.get(script_id)
        if item and item["user_id"] == user_id:
            return dict(item)
        return None

    def delete_script(self, script_id: str, user_id: str) -> bool:
        """Delete saved script if owned by `user_id`."""
        item = self._saved_scripts.get(script_id)
        if item and item["user_id"] == user_id:
            del self._saved_scripts[script_id]
            return True
        return False


