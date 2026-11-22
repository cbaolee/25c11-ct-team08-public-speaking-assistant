import json
import logging
import os
import shutil
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.app.config import (
    max_list_page_size,
    max_request_bytes,
    max_saved_scripts,
    max_script_chars,
    max_script_words,
    max_upload_bytes,
    missing_required_settings,
    script_title_max_chars,
    settings,
    validate_list_limits,
)
from src.app.constants import CONSTANTS
from src.app.db.factory import Repos, get_repos
from src.app.db.models import (
    NewScript,
    NewSession,
    ScriptLimitReachedError,
    ScriptPatch,
    ScriptRow,
    ScriptDuplicateBodyError,
    ScriptDuplicateTitleError,
    SessionRow,
    StorageError,
    build_content_hash,
    build_object_path,
    encode_cursor,
)
from src.app.db.session_helpers import (
    compact_session,
    encode_opus,
    merge_series,
    split_series,
)
from src.app.deps import CurrentUser, get_current_user
from src.app.routes import auth as auth_routes
from src.app.routes import baselines, coach, practice
from src.app.routes import profile as profile_routes
from src.app.uploads import BodySizeLimitMiddleware, safe_upload_path, save_upload_limited
from src.audio_processing.contracts import AudioRejected, SttUnavailable, VadParams
from src.audio_processing.evaluate_jobs import EvaluateJobStore, RateLimited, run_evaluate_job
from src.audio_processing.pipeline import evaluate_session
from src.text_processing.chat_session import (
    READY_MESSAGE,
    ChatSessionState,
    analyze_slot_coverage,
    build_followup_reply,
    chat_session_store,
    check_ready_to_generate,
    ingest_upload_file,
)
from src.text_processing.contracts import (
    CATEGORY_SLUG_MAP,
    DocumentChunk,
    ScriptGenerationError,
    ScriptGenerationRequest,
)
from src.text_processing.moderation import DEFAULT_LLAMA_GUARD_MODEL, ContentModerator
from src.text_processing.parser import DocumentParserError
from src.text_processing.pipeline import ScriptGenerationPipeline
from src.text_processing.sanitizer import sanitize_chunks, sanitize_text

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

logger = logging.getLogger(__name__)


def _warmup_script_pipeline() -> None:
    """Pre-load TemplateStore and the local embedding model in the background at startup."""
    try:
        pipeline = get_script_pipeline()
        retriever = getattr(pipeline.template_engine, "retriever", None)
        if retriever is not None:
            retriever.get_model()
    except Exception:
        logger.debug("Background script pipeline warm-up skipped.", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse to start when a required key is missing (fail at startup, not mid-demo)."""
    missing = missing_required_settings(settings)
    if missing:
        logger.critical("Missing required settings in .env: %s", ", ".join(missing))
        raise RuntimeError("Missing required settings in .env: " + ", ".join(missing))
    validate_list_limits(max_list_page_size, max_saved_scripts)
    if not os.getenv("PYTEST_CURRENT_TEST"):
        threading.Thread(target=_warmup_script_pipeline, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_request_bytes)


class RevalidatedStaticFiles(StaticFiles):
    """Static UI files the browser checks again before reuse, so changed CSS/JS is never stale.

    An unchanged file still costs only a 304 (ETag / Last-Modified).
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", RevalidatedStaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app.include_router(auth_routes.router)
app.include_router(profile_routes.router)
app.include_router(baselines.router)
app.include_router(practice.router)
app.include_router(coach.router)

_script_pipeline: ScriptGenerationPipeline | None = None
_evaluate_jobs = EvaluateJobStore()


def get_script_pipeline() -> ScriptGenerationPipeline:
    """Return the process-wide `ScriptGenerationPipeline` singleton."""
    global _script_pipeline
    if _script_pipeline is None:
        moderator = ContentModerator(
            enable_llama_guard=bool(settings.ollama_host),
            ollama_url=settings.ollama_host or None,
            ollama_api_key=settings.ollama_api_key or None,
            llama_guard_model=settings.guard_model or DEFAULT_LLAMA_GUARD_MODEL,
        )
        _script_pipeline = ScriptGenerationPipeline(moderator=moderator)
    return _script_pipeline


class SaveScriptPayload(BaseModel):
    title: str = Field(default="Untitled Script", max_length=script_title_max_chars)
    body: str


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/config")
async def web_config() -> dict[str, Any]:
    """The [web] section plus the limits and public settings the UI needs (no secrets)."""
    return {
        **CONSTANTS["web"],
        "max_saved_scripts": max_saved_scripts,
        "script_title_max_chars": script_title_max_chars,
        "max_pdf_size_bytes": CONSTANTS["script"]["max_pdf_size_bytes"],
        "max_pdf_pages": CONSTANTS["script"]["max_pdf_pages"],
        "auth": {key: CONSTANTS["auth"][key] for key in ("otp_length", "resend_cooldown_s")},
        "retry": {key: CONSTANTS["retry"][key] for key in (
            "sentence_min_error_ratio", "word_max_seconds", "sentence_max_seconds", "clip_pad_s"
        )},
        "evaluate_job": {key: CONSTANTS["evaluate_job"][key] for key in (
            "poll_interval_ms", "max_wait_s", "stage_weights", "stt_estimate_tau_s",
            "done_close_delay_ms", "announce_step_pct"
        )},
        "coach": {"max_focus_items": CONSTANTS["coach"]["max_focus_items"]},
        "retention": {"insufficient_days": CONSTANTS["retention"]["insufficient_days"]},
    }


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.exception_handler(AudioRejected)
async def audio_rejected_handler(request: Request, exc: AudioRejected):
    """422 `{error_code, message}` when probe or decode refuses the audio file."""
    return JSONResponse(status_code=422, content={"error_code": exc.code, "message": exc.message})


@app.exception_handler(SttUnavailable)
async def stt_unavailable_handler(request: Request, exc: SttUnavailable):
    """503 when every STT provider failed, so the UI can show a clear message."""
    return JSONResponse(
        status_code=503,
        content={
            "error_code": "stt_unavailable",
            "message": "The speech recognition service is not available right now. "
            "Please try again in a few minutes.",
        },
    )


def _delete_session_files(repos: Repos, user_id: UUID, row: SessionRow) -> None:
    """Delete any stored audio/series files for a session."""
    for bucket, path in (
        (settings.audio_bucket, row.audio_path),
        (settings.series_bucket, row.series_path),
    ):
        if not path:
            continue
        repos.files.delete_files(user_id, bucket, [path])


def _prune_old_sessions(repos: Repos, user_id: UUID) -> None:
    """Compact full sessions beyond the newest full set, then drop compact ones beyond the cap."""
    try:
        rows = repos.sessions.list_full_beyond(user_id, keep=settings.retention_full_sessions)
    except Exception:
        logger.exception("Could not list old sessions for user %s", user_id)
        return

    for row in rows:
        try:
            summary, mistakes = compact_session(row.result)
            # Keep paths on the row if cleanup fails so a later prune can retry.
            _delete_session_files(repos, user_id, row)
            if not repos.sessions.save_compact_session(user_id, row.id, summary, mistakes):
                continue
        except Exception:
            logger.exception("Could not prune session %s for user %s", row.id, user_id)

    _delete_old_compact_sessions(repos, user_id)


def _delete_old_compact_sessions(repos: Repos, user_id: UUID) -> None:
    """Delete the oldest compact sessions so at most `max_compact_sessions` remain."""
    try:
        rows = repos.sessions.list_compact_beyond(user_id, keep=settings.max_compact_sessions)
    except Exception:
        logger.exception("Could not list old compact sessions for user %s", user_id)
        return
    for row in rows:
        try:
            _delete_session_files(repos, user_id, row)  # normally none left after compaction
            repos.sessions.delete_session(user_id, row.id)
        except Exception:
            logger.exception("Could not delete compact session %s for user %s", row.id, user_id)


def _save_result_to_history(
    *,
    repos: Repos,
    user_id: UUID,
    script: str,
    result,
    source_audio_path: Path | None,
    baseline_id: UUID | None = None,
    script_id: UUID | None = None,
    topic: str | None = None,
    accent: str | None = None,
) -> str | None:
    session_id = uuid4()
    uploaded_paths: list[tuple[str, str]] = []
    try:
        if result.status == "ok":
            if source_audio_path is None or not source_audio_path.exists():
                raise StorageError("Audio file is missing for session save")
            # Own file name: the upload may already be .webm, FFmpeg refuses to overwrite input
            encoded_path = source_audio_path.parent / f"{session_id}.webm"
            encode_opus(source_audio_path, encoded_path)
            audio_path = build_object_path(user_id, session_id, ".webm")
            audio_bytes = encoded_path.read_bytes()
            repos.files.upload_file(
                user_id,
                settings.audio_bucket,
                audio_path,
                audio_bytes,
                "audio/webm",
                upsert=True,
            )
            uploaded_paths.append((settings.audio_bucket, audio_path))

            result_json = result.model_dump(mode="json")
            result_without_series, series_json = split_series(result_json)
            series_path = build_object_path(user_id, session_id, ".series.json")
            repos.files.upload_file(
                user_id,
                settings.series_bucket,
                series_path,
                json.dumps(series_json, separators=(",", ":")).encode("utf-8"),
                "application/json",
                upsert=True,
            )
            uploaded_paths.append((settings.series_bucket, series_path))
        else:
            result_without_series = result.model_dump(mode="json")
            series_path = None
            audio_path = None

        stt = result_without_series.get("stt") or {}
        session_row = NewSession(
            id=session_id,
            script_snapshot=script,
            status=result.status,
            result=result_without_series,
            result_schema_version=result.schema_version,
            reason=result.reason,
            overall=result.overall,
            label=result.label,
            components=result.components,
            audio_path=audio_path,
            series_path=series_path,
            audio_duration_s=(
                result.audio.get("duration_s") if isinstance(result.audio, dict) else None
            ),
            stt_provider=(stt.get("provider") if isinstance(stt, dict) else None),
            stt_model=(stt.get("model") if isinstance(stt, dict) else None),
            topic=topic,
            accent=accent,
            baseline_id=baseline_id,
            script_id=script_id,
        )
        repos.sessions.create_session(user_id, session_row)
        try:
            _prune_old_sessions(repos, user_id)
        except Exception:
            logger.exception("Could not prune old sessions for user %s", user_id)
        return str(session_id)
    except Exception:
        for bucket, path in uploaded_paths:
            try:
                repos.files.delete_files(user_id, bucket, [path])
            except Exception:
                logger.exception("Failed to clean up uploaded session object in %s bucket", bucket)
        raise


async def _fetch_page(list_rows, user_id: UUID, limit: int, cursor: str | None):
    """One newest-first page from a repo list function, plus the next cursor (None at the end).

    Asks for `limit + 1` rows to know if another page exists. The repo caps `limit` at
    max_list_page_size, so at that limit one extra 1-row call checks the next page.
    Raises the repo's StorageError, or ValueError for a bad cursor.
    """
    rows = await run_in_threadpool(list_rows, user_id, min(limit + 1, max_list_page_size), cursor)
    has_more = len(rows) > limit
    page = rows[:limit]
    if limit == max_list_page_size and len(rows) == limit:
        probe_cursor = encode_cursor(page[-1].created_at, page[-1].id)
        has_more = bool(await run_in_threadpool(list_rows, user_id, 1, probe_cursor))
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    return page, next_cursor


@app.get("/api/sessions")
async def list_sessions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    limit: Annotated[int, Query(ge=1, le=max_list_page_size)] = 10,
    cursor: str | None = None,
):
    """Return a page of the user's session summaries plus a next cursor when more exist."""
    try:
        page, next_cursor = await _fetch_page(repos.sessions.list_sessions, user.id, limit, cursor)
    except StorageError:
        logger.exception("Could not list sessions for user %s", user.id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_cursor"})
    return {
        "items": [row.model_dump(mode="json") for row in page],
        "next_cursor": next_cursor,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Return the full session payload or a compact summary for older sessions."""
    try:
        row = await run_in_threadpool(repos.sessions.get_session, user.id, session_id)
    except StorageError:
        logger.exception("Could not load session %s", session_id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    if row is None:
        return JSONResponse(status_code=404, content={"error": "session_not_found"})

    data = row.model_dump(mode="json", exclude={"user_id", "audio_path", "series_path"})

    if not row.is_compact and row.series_path:
        try:
            series_json = json.loads(
                (
                    await run_in_threadpool(
                        repos.files.download_file,
                        user.id,
                        settings.series_bucket,
                        row.series_path,
                    )
                ).decode("utf-8")
            )
            data["result"] = merge_series(row.result, series_json)
        except (StorageError, json.JSONDecodeError):
            # Files may be gone if a retention run stopped halfway; still return scores.
            logger.exception("Could not load series JSON for session %s", session_id)
            data["media_available"] = False
    if not row.is_compact and row.audio_path:
        try:
            data["audio_url"] = await run_in_threadpool(
                repos.files.create_signed_url,
                user.id,
                settings.audio_bucket,
                row.audio_path,
                settings.signed_url_ttl_s,
            )
        except StorageError:
            logger.exception("Could not create signed URL for session %s", session_id)
            data["media_available"] = False
    data.setdefault("media_available", bool(not row.is_compact and row.audio_path))
    return data


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Delete files and row for a single session; unknown IDs return 404."""
    try:
        row = await run_in_threadpool(repos.sessions.get_session, user.id, session_id)
    except StorageError:
        logger.exception("Could not load session %s for deletion", session_id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    if row is None:
        return JSONResponse(status_code=404, content={"error": "session_not_found"})

    try:
        await run_in_threadpool(_delete_session_files, repos, user.id, row)
    except StorageError:
        logger.exception("Could not delete files for session %s", session_id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    try:
        deleted = await run_in_threadpool(repos.sessions.delete_session, user.id, session_id)
    except StorageError:
        logger.exception("Could not delete session row %s", session_id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    return {"deleted": deleted}


def _validate_script(script: str) -> JSONResponse | None:
    """422 for an empty script or one longer than can be read within the audio limit."""
    if not script.strip():
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "script_empty",
                "message": "The practice text is empty. Choose or write a text first.",
            },
        )
    if len(script) > max_script_chars or len(script.split()) > max_script_words:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "script_too_long",
                "message": f"The practice text is too long (maximum {max_script_words} "
                "words). Please use a shorter text.",
            },
        )
    return None


MAX_TOPIC_CHARS = 200


def _load_profile_accent(repos: Repos, user_id: UUID) -> str | None:
    """The user's target accent for the saved session; None (and a log) if it cannot be read."""
    try:
        profile = repos.profiles.get_profile(user_id)
    except StorageError:
        logger.exception("Could not load profile accent")
        return None
    return profile.target_accent if profile is not None else None


@app.post("/api/evaluate")
async def evaluate_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    audio: Annotated[UploadFile, File()],
    script: Annotated[str, Form()],
    background_tasks: BackgroundTasks,
    script_id: Annotated[str, Form()] = "",
    topic: Annotated[str, Form()] = "",
):
    """
    Score one practice session and save it to the user's history.

    The baseline is loaded from the DB for the current user (any `baseline_profile` field
    a client still sends is ignored). When settings.baseline_required is on and the user has
    no baseline, return 409. `script_id` (optional) must be one of the caller's saved scripts:
    the session links to it, and its topic is used when `topic` is empty. The accent stored
    with the session is the profile's `target_accent`.
    """
    script_error = _validate_script(script)
    if script_error is not None:
        return script_error

    script_row: ScriptRow | None = None
    if script_id.strip():
        try:
            script_uuid = UUID(script_id.strip())
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={
                    "error_code": "invalid_script_id",
                    "message": "The selected script id is not valid.",
                },
            )
        try:
            script_row = await run_in_threadpool(repos.scripts.get_script, user.id, script_uuid)
        except StorageError:
            logger.exception("Could not load script for evaluation")
            return JSONResponse(
                status_code=503,
                content={
                    "error_code": "script_storage_unavailable",
                    "message": "Could not load the selected script. Please try again.",
                },
            )
        if script_row is None:  # missing or another user's script: same answer
            return JSONResponse(
                status_code=404,
                content={
                    "error_code": "script_not_found",
                    "message": "The selected script no longer exists.",
                },
            )
    session_topic = topic.strip()[:MAX_TOPIC_CHARS] or (script_row.title if script_row else None)

    # Default VAD settings
    vad_params = VadParams()

    try:
        baseline_row = await run_in_threadpool(repos.baselines.get_current_baseline, user.id)
    except StorageError:
        logger.exception("Could not load baseline")
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "baseline_unavailable",
                "message": "Could not load the current baseline",
            },
        )
    if baseline_row is None and settings.baseline_required:
        return JSONResponse(
            status_code=409,
            content={
                "error_code": "baseline_required",
                "message": "Record a baseline before practising",
            },
        )
    baseline = baselines.to_baseline_profile(baseline_row) if baseline_row else None

    if _evaluate_jobs.count_active(str(user.id)) >= _evaluate_jobs.limit:
        return JSONResponse(
            status_code=429,
            content={"error_code": "rate_limited", "message": "An evaluation is already running."},
        )

    workdir = Path(tempfile.mkdtemp())
    try:
        audio_path = safe_upload_path(workdir, audio.filename)
        await run_in_threadpool(save_upload_limited, audio, audio_path, max_bytes=max_upload_bytes)
        try:
            job = _evaluate_jobs.create_job(str(user.id), workdir)
        except RateLimited:
            shutil.rmtree(workdir, ignore_errors=True)
            return JSONResponse(
                status_code=429,
                content={"error_code": "rate_limited",
                         "message": "An evaluation is already running."},
            )
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    def evaluate(**callbacks):
        return evaluate_session(audio_path=audio_path, script=script, baseline=baseline,
                                vad_params=vad_params, **callbacks)

    def save(result):
        session_id = None
        save_started = perf_counter()
        try:
            accent = _load_profile_accent(repos, user.id)
            session_id = _save_result_to_history(
                repos=repos, user_id=user.id, script=script, result=result,
                source_audio_path=audio_path, baseline_id=baseline_row.id if baseline_row else None,
                script_id=script_row.id if script_row else None, topic=session_topic, accent=accent,
            )
        except Exception:
            logger.exception("Failed to save evaluation result to session history")
        finally:
            logger.info(
                "Evaluation session save attempt took %.3f seconds", perf_counter() - save_started
            )
        return result.model_copy(
            update={"session_id": session_id, "saved": session_id is not None}
        ).model_dump(mode="json")

    background_tasks.add_task(run_evaluate_job, _evaluate_jobs, job, evaluate, save)
    return JSONResponse(status_code=202, content={"job_id": job.job_id, "status": "queued"})


def _evaluate_job_response(job: dict | None):
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "job_not_found", "message": "Evaluation job not found."},
        )
    return job


@app.get("/api/evaluate/{job_id}")
async def get_evaluate_job(job_id: str, user: Annotated[CurrentUser, Depends(get_current_user)]):
    return _evaluate_job_response(_evaluate_jobs.get(job_id, str(user.id)))


@app.delete("/api/evaluate/{job_id}")
async def cancel_evaluate_job(job_id: str, user: Annotated[CurrentUser, Depends(get_current_user)]):
    return _evaluate_job_response(_evaluate_jobs.cancel(job_id, str(user.id)))


@app.exception_handler(ScriptGenerationError)
async def script_generation_error_handler(_: Request, exc: ScriptGenerationError) -> JSONResponse:
    """Return structured JSON `{error_code, message}` for Script Generation errors (Brief §5.7)."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(ScriptLimitReachedError)
async def script_limit_reached_handler(_: Request, exc: ScriptLimitReachedError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error_code": "script_limit_reached",
            "message": str(exc),
            "limit": exc.limit,
            "count": exc.count,
        },
    )


@app.get("/api/topics")
async def list_topics_endpoint(category: str | None = None) -> dict[str, Any]:
    """Return template topics grouped/filtered by category with `duration_min` (Brief §5.7)."""
    pipeline = get_script_pipeline()
    slug = None
    if category and category.strip():
        raw_cat = category.strip().lower()
        rev_map = {v.lower(): k for k, v in CATEGORY_SLUG_MAP.items()}
        slug = rev_map.get(raw_cat, raw_cat)
    topics = [t.to_dict() for t in pipeline.template_store.list_topics(category_slug=slug)]
    return {"topics": topics, "categories": CATEGORY_SLUG_MAP}


@app.post("/api/generate-script", status_code=202)
async def generate_script_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    topic: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    duration_min: Annotated[int, Form()] = 5,
    greeting: Annotated[str, Form()] = "",
    raw_text: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
    session_id: Annotated[str, Form()] = "",
    user_feedback: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """Queue a background script generation job and return `202 {job_id, status}` (Brief §5.5)."""
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    pdf_path: str | None = None
    if pdf is not None and pdf.filename:
        # Fixed ".pdf" suffix; the parser checks the %PDF- signature and the 25 MB limit.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf_path = tmp_file.name
        await run_in_threadpool(
            save_upload_limited, pdf, Path(pdf_path), max_bytes=max_upload_bytes
        )

    clean_topic = topic.strip()
    clean_session_id = session_id.strip() or None
    clean_feedback = user_feedback.strip() or None

    store = getattr(pipeline, "session_store", chat_session_store)
    if clean_session_id:
        sess = store.get(clean_session_id, user_id=user_id)
        if sess:
            if not clean_topic:
                clean_topic = getattr(sess, "topic", None) or sess.initial_prompt or ""
            if not category and sess.category:
                category = sess.category
            if duration_min == 5 and sess.duration_min:
                duration_min = sess.duration_min

    req = ScriptGenerationRequest(
        topic=clean_topic,
        category=category or None,
        duration_min=duration_min,
        pdf_path=pdf_path,
        raw_text=raw_text or None,
        greeting=greeting or None,
        user_id=user_id,
        session_id=clean_session_id,
        user_feedback=clean_feedback,
    )
    job = pipeline.create_job(user_id=user_id)
    background_tasks.add_task(pipeline.run_job, job.job_id, req, True)
    return {"job_id": job.job_id, "status": job.status}


class SelectTopicPayload(BaseModel):
    session_id: str
    template_id: str | None = None


@app.post("/api/script-chat/suggest")
async def script_chat_suggest_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    category: Annotated[str, Form()] = "",
    duration_min: Annotated[int, Form()] = 5,
    prompt: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
    session_id: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """Suggest 4-5 templates from category, duration, and optional prompt/document."""
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    store = getattr(pipeline, "session_store", chat_session_store)

    clean_prompt = sanitize_text(prompt).strip() if prompt else ""
    if clean_prompt:
        pipeline.moderator.assert_safe(clean_prompt, user_id=user_id)

    file_chunks: list[DocumentChunk] = []
    filename: str = ""
    if file is not None and file.filename:
        filename = file.filename
        file_bytes = await file.read()
        try:
            raw_chunks = ingest_upload_file(file_bytes, filename)
            file_chunks = sanitize_chunks(raw_chunks)
        except DocumentParserError as exc:
            raise ScriptGenerationError(
                error_code=exc.error_code,
                message=exc.message,
                status_code=422,
            ) from exc
        file_text = "\n".join(c.content for c in file_chunks[:20])
        if file_text:
            pipeline.moderator.assert_safe(file_text, user_id=user_id)

    clean_session_id = session_id.strip()
    session = None
    if clean_session_id:
        session = store.get(clean_session_id, user_id=user_id)
        if session is None:
            raise ScriptGenerationError(
                error_code="session_not_found",
                message="Session not found or access denied.",
                status_code=404,
            )

    if session is None:
        session = ChatSessionState(
            session_id=str(uuid4()),
            user_id=user_id,
            category=category,
            duration_min=duration_min,
            initial_prompt=clean_prompt,
        )
    else:
        if category:
            session.category = category
        if duration_min:
            session.duration_min = duration_min
        if clean_prompt:
            session.initial_prompt = clean_prompt

    if file_chunks:
        session.files_loaded.append(filename)
        session.chunks.extend(file_chunks)
        retriever = getattr(pipeline.template_engine, "retriever", None)
        if retriever is not None:
            session.chunk_embeddings = retriever.encode_chunks(session.chunks)

    store.put(session)

    query = clean_prompt
    if not query and session.chunks:
        query = " ".join(c.content for c in session.chunks[:3])

    suggestion_res = pipeline.template_store.suggest_topics(
        category_slug=session.category,
        duration_min=session.duration_min,
        query=query,
        retriever=getattr(pipeline.template_engine, "retriever", None),
    )
    res = suggestion_res.to_dict()
    res["session_id"] = session.session_id
    res["topics"] = list(res["suggestions"])
    res["files_loaded"] = list(session.files_loaded)
    return res


@app.post("/api/script-chat/select-topic")
async def script_chat_select_topic_endpoint(
    payload: SelectTopicPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Store selected template ID and analyze slot coverage or enter free-topic mode."""
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    store = getattr(pipeline, "session_store", chat_session_store)
    session = store.get(payload.session_id, user_id=user_id)
    if session is None:
        raise ScriptGenerationError(
            error_code="session_not_found",
            message=f"Session '{payload.session_id}' not found.",
            status_code=404,
        )

    session.selected_template_id = payload.template_id
    retriever = getattr(pipeline.template_engine, "retriever", None)

    if payload.template_id:
        template_doc = pipeline.template_store.get(payload.template_id)
        if template_doc is None:
            raise ScriptGenerationError(
                error_code="template_not_found",
                message=f"Template '{payload.template_id}' not found.",
                status_code=404,
            )
        session.topic = template_doc.metadata.topic
        cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
            template_document=template_doc,
            chunks=session.chunks,
            chunk_embeddings=session.chunk_embeddings,
            retriever=retriever,
            prompt=session.initial_prompt,
            user_notes=session.user_notes,
        )
        session.coverage_ratio = cov_ratio
        session.missing_entities = missing_entities
        session.missing_groups = missing_groups
        session.ready_to_generate = check_ready_to_generate(
            selected_template_id=session.selected_template_id,
            missing_entities=session.missing_entities,
            coverage_ratio=session.coverage_ratio,
            gather_turns=session.gather_turns,
            files_loaded=session.files_loaded,
            prompt=session.initial_prompt,
            user_notes=session.user_notes,
        )
        client = getattr(pipeline.template_engine, "client", None)
        reply = build_followup_reply(
            topic=session.topic,
            ready_to_generate=session.ready_to_generate,
            missing_entities=session.missing_entities,
            missing_groups=session.missing_groups,
            gather_turns=session.gather_turns,
            client=client,
        )
    else:
        session.selected_template_id = None
        if not session.topic:
            session.topic = session.initial_prompt or session.category or "Custom Speech"
        session.missing_entities = []
        session.missing_groups = []
        session.coverage_ratio = 0.0
        session.ready_to_generate = check_ready_to_generate(
            selected_template_id=None,
            missing_entities=[],
            coverage_ratio=0.0,
            gather_turns=session.gather_turns,
            files_loaded=session.files_loaded,
            prompt=session.initial_prompt,
            user_notes=session.user_notes,
        )
        if session.ready_to_generate:
            reply = READY_MESSAGE
        else:
            reply = (
                "To help craft your free-topic speech, please share your main ideas or "
                "upload reference material (notes or document)."
            )

    store.put(session)
    return {
        "session_id": session.session_id,
        "template_id": session.selected_template_id,
        "selected_template_id": session.selected_template_id,
        "ready_to_generate": session.ready_to_generate, "coverage_ratio": session.coverage_ratio,
        "missing_entities": session.missing_entities, "missing_groups": session.missing_groups,
        "reply_message": reply,
    }


@app.post("/api/script-chat/message")
async def script_chat_message_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session_id: Annotated[str, Form(...)],
    message: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    """Add user notes/documents, re-evaluate slot coverage and 3-layer stop condition."""
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    store = getattr(pipeline, "session_store", chat_session_store)
    session = store.get(session_id, user_id=user_id)
    if session is None:
        raise ScriptGenerationError(
            error_code="session_not_found",
            message=f"Session '{session_id}' not found.",
            status_code=404,
        )

    clean_msg = sanitize_text(message).strip() if message else ""
    if clean_msg:
        pipeline.moderator.assert_safe(clean_msg, user_id=user_id)

    file_chunks: list[DocumentChunk] = []
    if file is not None and file.filename:
        file_bytes = await file.read()
        try:
            raw_chunks = ingest_upload_file(file_bytes, file.filename)
            file_chunks = sanitize_chunks(raw_chunks)
        except DocumentParserError as exc:
            raise ScriptGenerationError(
                error_code=exc.error_code,
                message=exc.message,
                status_code=422,
            ) from exc
        file_text = "\n".join(c.content for c in file_chunks[:20])
        if file_text:
            pipeline.moderator.assert_safe(file_text, user_id=user_id)

    if not clean_msg and not file_chunks:
        raise ScriptGenerationError(
            error_code="empty_input",
            message="Please provide a message or a document.",
            status_code=422,
        )

    if clean_msg:
        session.user_notes.append(clean_msg)
    if file_chunks:
        session.files_loaded.append(file.filename)
        session.chunks.extend(file_chunks)
        retriever = getattr(pipeline.template_engine, "retriever", None)
        if retriever is not None:
            session.chunk_embeddings = retriever.encode_chunks(session.chunks)

    session.gather_turns += 1

    retriever = getattr(pipeline.template_engine, "retriever", None)
    client = getattr(pipeline.template_engine, "client", None)

    if session.selected_template_id:
        template_doc = pipeline.template_store.get(session.selected_template_id)
        if template_doc:
            session.topic = template_doc.metadata.topic
            cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
                template_document=template_doc, chunks=session.chunks,
                chunk_embeddings=session.chunk_embeddings, retriever=retriever,
                prompt=session.initial_prompt, user_notes=session.user_notes,
            )
            session.coverage_ratio = cov_ratio
            session.missing_entities = missing_entities
            session.missing_groups = missing_groups

    session.ready_to_generate = check_ready_to_generate(
        selected_template_id=session.selected_template_id,
        missing_entities=session.missing_entities,
        coverage_ratio=session.coverage_ratio,
        gather_turns=session.gather_turns,
        files_loaded=session.files_loaded,
        prompt=session.initial_prompt,
        user_notes=session.user_notes,
    )

    topic = getattr(session, "topic", None) or session.initial_prompt or "your speech"
    if session.selected_template_id:
        reply = build_followup_reply(
            topic=topic, ready_to_generate=session.ready_to_generate,
            missing_entities=session.missing_entities, missing_groups=session.missing_groups,
            gather_turns=session.gather_turns, client=client,
        )
    else:
        if session.ready_to_generate:
            reply = READY_MESSAGE
        else:
            reply = (
                "Thanks! Please provide more details or upload notes to help prepare your speech."
            )

    store.put(session)
    return {
        "session_id": session.session_id, "reply_message": reply,
        "ready_to_generate": session.ready_to_generate, "coverage_ratio": session.coverage_ratio,
        "missing_entities": session.missing_entities, "missing_groups": session.missing_groups,
        "gather_turns": session.gather_turns, "files_loaded": list(session.files_loaded),
    }


@app.get("/api/generate-script/{job_id}")
async def get_generate_script_job_endpoint(
    job_id: str, user: Annotated[CurrentUser, Depends(get_current_user)]
) -> JSONResponse:
    """Poll status, progress, and result of a script generation job (Brief §5.5)."""
    job = get_script_pipeline().get_job(job_id)
    if job is None or job.user_id != str(user.id):  # another user's job looks missing
        return JSONResponse(
            status_code=404,
            content={"error_code": "job_not_found", "message": f"Job '{job_id}' not found."},
        )
    return JSONResponse(status_code=200, content=job.to_dict())


def _script_error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error_code": error_code, "message": message}
    )


def _script_storage_unavailable() -> JSONResponse:
    return _script_error(
        503,
        "script_storage_unavailable",
        "Saved scripts are not available right now. Please try again.",
    )


def _script_not_found() -> JSONResponse:
    return _script_error(404, "script_not_found", "Script not found.")


def _script_payload(row: ScriptRow) -> dict[str, Any]:
    payload = row.model_dump(mode="json", exclude={"user_id", "content_hash"})
    payload["word_count"] = len(row.body.split())
    return payload


def _script_duplicate(code: str, twin: ScriptRow) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error_code": code,
            "message": (
                f'This text is the same as your saved script "{twin.title}".'
                if code == "script_duplicate_body"
                else f'You already have a saved script named "{twin.title}".'
            ),
            "duplicate_id": str(twin.id),
            "duplicate_title": twin.title,
        },
    )


def _save_script_row(repos: Repos, user_id: UUID, data: NewScript) -> tuple[ScriptRow, bool]:
    """Return (row, created), rejecting duplicate body/title in deterministic order."""
    twin = repos.scripts.find_script_by_hash(user_id, data.content_hash)
    if twin is not None:
        raise ScriptDuplicateBodyError(twin)
    twin = repos.scripts.find_script_by_title(user_id, data.title)
    if twin is not None:
        raise ScriptDuplicateTitleError(twin)
    count = repos.scripts.count_scripts(user_id)
    if count >= max_saved_scripts:
        raise ScriptLimitReachedError(limit=max_saved_scripts, count=count)
    return repos.scripts.create_script(user_id, data), True


@app.post("/api/scripts", status_code=201)
async def create_saved_script_endpoint(
    payload: SaveScriptPayload,
    response: Response,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
) -> Any:
    """Save a script after Stage 4 moderation."""
    clean_title = sanitize_text(payload.title).strip() or "Untitled Script"
    clean_body = sanitize_text(payload.body).strip()
    body_error = _validate_script(clean_body)
    if body_error is not None:
        return body_error
    # Only Layer 1 runs here; this is the explicit saved-script moderation contract.
    get_script_pipeline().moderator.assert_safe(
        f"{clean_title}\n{clean_body}",
        user_id=str(user.id),
        use_layer2=False,
    )
    data = NewScript(
        title=clean_title,
        body=clean_body,
        content_hash=build_content_hash(clean_body),
    )
    try:
        row, created = await run_in_threadpool(_save_script_row, repos, user.id, data)
    except ScriptDuplicateBodyError as err:
        return _script_duplicate("script_duplicate_body", err.twin)
    except ScriptDuplicateTitleError as err:
        return _script_duplicate("script_duplicate_title", err.twin)
    except StorageError:
        logger.exception("Could not save script")
        return _script_storage_unavailable()
    return _script_payload(row)


@app.get("/api/scripts")
async def list_saved_scripts_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    limit: Annotated[int, Query(ge=1, le=max_saved_scripts)] = max_saved_scripts,
    cursor: str | None = None,
) -> Any:
    """Return a newest-first page of saved script summaries, including total and page limit."""
    try:
        page, next_cursor = await _fetch_page(repos.scripts.list_scripts, user.id, limit, cursor)
        total = await run_in_threadpool(repos.scripts.count_scripts, user.id)
    except StorageError:
        logger.exception("Could not list scripts")
        return _script_storage_unavailable()
    except ValueError:
        return _script_error(400, "invalid_cursor", "The page cursor is not valid.")
    return {
        "items": [row.model_dump(mode="json") for row in page],
        "next_cursor": next_cursor,
        "total": total,
        "limit": max_saved_scripts,
    }


@app.get("/api/scripts/{script_id}")
async def get_saved_script_endpoint(
    script_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
) -> Any:
    """One saved script with its body; another user's script answers 404 like a missing one."""
    try:
        row = await run_in_threadpool(repos.scripts.get_script, user.id, script_id)
    except StorageError:
        logger.exception("Could not load script")
        return _script_storage_unavailable()
    if row is None:
        return _script_not_found()
    return _script_payload(row)


class EditScriptPayload(BaseModel):
    """Request body for `PATCH /api/scripts/{id}`: a new title, a new body, or both."""

    title: str | None = Field(default=None, max_length=script_title_max_chars)
    body: str | None = None


@app.patch("/api/scripts/{script_id}")
async def edit_saved_script_endpoint(
    script_id: UUID,
    payload: EditScriptPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
) -> Any:
    """Edit a saved script's title and/or body; new text passes the same checks as a new script."""
    patch = ScriptPatch()
    checked: list[str] = []
    if payload.title is not None:
        patch.title = sanitize_text(payload.title).strip()
        if not patch.title:
            return _script_error(422, "script_title_empty", "The script name cannot be empty.")
        checked.append(patch.title)
    if payload.body is not None:
        clean_body = sanitize_text(payload.body).strip()
        body_error = _validate_script(clean_body)
        if body_error is not None:
            return body_error
        patch.body = clean_body
        patch.content_hash = build_content_hash(clean_body)
        checked.append(clean_body)
    try:
        # A missing script (or another user's) answers 404 before any moderation call.
        if await run_in_threadpool(repos.scripts.get_script, user.id, script_id) is None:
            return _script_not_found()
        if patch.content_hash is not None:
            twin = await run_in_threadpool(
                repos.scripts.find_script_by_hash, user.id, patch.content_hash
            )
            if twin is not None and twin.id != script_id:
                return _script_duplicate("script_duplicate_body", twin)
        if patch.title is not None:
            twin = await run_in_threadpool(
                repos.scripts.find_script_by_title, user.id, patch.title
            )
            if twin is not None and twin.id != script_id:
                return _script_duplicate("script_duplicate_title", twin)
    except StorageError:
        logger.exception("Could not check script before edit")
        return _script_storage_unavailable()
    if checked:
        get_script_pipeline().moderator.assert_safe("\n".join(checked), user_id=str(user.id))
    try:
        row = await run_in_threadpool(repos.scripts.update_script, user.id, script_id, patch)
    except ScriptDuplicateBodyError as err:
        return _script_duplicate("script_duplicate_body", err.twin)
    except ScriptDuplicateTitleError as err:
        return _script_duplicate("script_duplicate_title", err.twin)
    except StorageError:
        logger.exception("Could not edit script")
        return _script_storage_unavailable()
    if row is None:
        return _script_not_found()
    return _script_payload(row)


@app.delete("/api/scripts/{script_id}")
async def delete_saved_script_endpoint(
    script_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
) -> Any:
    """Delete a saved script; sessions keep their `script_snapshot` (script_id becomes null)."""
    try:
        deleted = await run_in_threadpool(repos.scripts.delete_script, user.id, script_id)
    except StorageError:
        logger.exception("Could not delete script")
        return _script_storage_unavailable()
    if not deleted:
        return _script_not_found()
    return {"deleted": True, "id": str(script_id)}
