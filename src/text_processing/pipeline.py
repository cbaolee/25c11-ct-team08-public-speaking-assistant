"""WP-B4 & WP-B5 (Member 3): 8-Stage Script Generation Pipeline and In-Memory Job Manager.

Responsibilities (Brief §5.2, §5.5, §5.7):
- Execute the 8-stage pipeline:
  1. Validate input (PDF / raw_text)
  2. Parse into `DocumentChunk[]`
  3. Sanitize chunks
  4. Content Moderation
  5. Route: Template branch (6T) if topic matches `TemplateStore`, else LLM branch (6L)
  6. Generate + verify citations
  7. Post-check (`{{ }}`, word count, punctuation)
  8. Return `GeneratedScript`
- Manage in-memory background jobs (`POST /api/generate-script` -> `202 {job_id}`)
"""

import uuid

from .contracts import (
    DocumentChunk,
    GeneratedScript,
    ParagraphCitation,
    ScriptGenerationError,
    ScriptGenerationRequest,
    ScriptJobState,
)
from .generator import ScriptGenerator
from .moderation import ContentModerator
from .parser import DocumentParserError, parse_input_to_chunks, validate_pdf_file
from .sanitizer import sanitize_chunks, sanitize_text
from .template_engine import TemplateEngine
from .template_store import TemplateStore


class ScriptGenerationPipeline:
    """End-to-end coordinator for the 8-stage Script Generation workflow (Brief §5.2)."""

    def __init__(
        self,
        template_store: TemplateStore | None = None,
        moderator: ContentModerator | None = None,
        template_engine: TemplateEngine | None = None,
        llm_generator: ScriptGenerator | None = None,
    ) -> None:
        self.template_store = template_store or TemplateStore()
        self.moderator = moderator or ContentModerator()
        self.template_engine = template_engine or TemplateEngine()
        self.llm_generator = llm_generator or ScriptGenerator()
        self._jobs: dict[str, ScriptJobState] = {}

    def create_job(self, user_id: str = "anonymous") -> ScriptJobState:
        """Create and register a new background job state in memory (Brief §5.5)."""
        job_id = str(uuid.uuid4())
        job = ScriptJobState(job_id=job_id, user_id=user_id, status="queued", progress=0)
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> ScriptJobState | None:
        """Look up an in-memory job by `job_id`."""
        return self._jobs.get(job_id)

    def run(self, request: ScriptGenerationRequest) -> GeneratedScript:
        """Execute stages 1 through 8 synchronously (can be invoked inside a background task).

        TODO (Member 3 - WP-B4 & WP-B5):
        1. Add LRU cache lookup by `(sha256(request), user_id)`.
        2. Expand Branch 6L (`self.llm_generator`) for multi-section 5/10/15/20 min scripts.
        3. Update job progress percentages across stages when called via background runner.
        """
        # Stage 1, 2, 3: Validate, Parse, and Sanitize input document (if provided)
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
                error_code = "no_text_layer" if exc.error_code == "empty_pdf" else "invalid_pdf"
                raise ScriptGenerationError(
                    error_code=error_code,
                    message=exc.message,
                    status_code=422,
                ) from exc

        # Stage 4: Content Moderation on topic and extracted chunks
        combined_input = "\n".join([ sanitize_text(request.topic), *(c.content for c in chunks) ])
        self.moderator.assert_safe(combined_input, user_id=request.user_id)

        # Stage 5: Route between Template Branch (6T) and Free-Topic LLM Branch (6L)
        template_doc = self.template_store.get(request.topic)
        if template_doc is not None:
            # Stage 6T & 7: Template Engine
            return self.template_engine.fill_template(template_doc, chunks=chunks or None)

        # Stage 6L: Free-Topic LLM Generation (Member 3 to expand to multi-section by duration_min)
        if not chunks:
            chunks = [
                DocumentChunk(chunk_id=1, heading=request.topic, page=1, content=request.topic)
            ]
        poc_result = self.llm_generator.generate_script(chunks=chunks, topic=request.topic)
        citations = [
            ParagraphCitation(
                paragraph=i + 1,
                heading=c.get("heading"),
                page=c.get("page"),
                status="cited" if request.pdf_path or request.raw_text else "uncited",
            )
            for i, c in enumerate(poc_result.citations)
        ]
        return GeneratedScript(
            script=poc_result.script,
            word_count=poc_result.word_count,
            duration_min=request.duration_min,
            source="llm",
            template_id=None,
            models_used=[poc_result.model_used],
            citations=citations,
            flags=[] if (request.pdf_path or request.raw_text) else ["uncited"],
        )

