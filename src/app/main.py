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
    chat_turn_jobs_max_capacity,
    composer_max_words,
    eta_buffer_s,
    max_audio_seconds,
    max_list_page_size,
    max_pdf_pages,
    max_pdf_size_bytes,
    max_request_bytes,
    max_saved_scripts,
    max_script_chars,
    max_script_words,
    max_text_file_bytes,
    max_text_file_words,
    max_turn_text_chars,
    max_upload_bytes,
    missing_required_settings,
    moderation_max_chunks,
    script_title_max_chars,
    settings,
    suggest_query_max_chunks,
    upload_read_chunk_bytes,
    validate_list_limits,
)
from src.app.constants import CONSTANTS
from src.app.db.factory import Repos, get_repos
from src.app.db.models import (
    NewScript,
    NewSession,
    ScriptDuplicateBodyError,
    ScriptDuplicateTitleError,
    ScriptLimitReachedError,
    ScriptPatch,
    ScriptRow,
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
from src.app.deps import (
    CurrentUser,
    RecordingConsentRequiredError,
    get_current_user,
    require_recording_consent,
)
from src.app.routes import auth as auth_routes
from src.app.routes import baselines, coach, practice
from src.app.routes import profile as profile_routes
from src.app.script_guards import (
    guard_category_generate,
    guard_category_message_file,
    guard_category_suggest,
    reject_gibberish,
    remember_category_decision,
)
from src.app.script_limits import (
    check_generate_limits,
    job_running_block,
    rate_limited_response,
    validate_generate_input,
)
from src.app.uploads import BodySizeLimitMiddleware, safe_upload_path, save_upload_limited
from src.audio_processing.contracts import AudioRejected, SttUnavailable, VadParams
from src.audio_processing.evaluate_jobs import EvaluateJobStore, RateLimited, run_evaluate_job
from src.audio_processing.pipeline import evaluate_session
from src.text_processing.category_guard import warm_category_prototypes
from src.text_processing.chat_session import (
    CHAT_TURN_STEP_DURATIONS,
    ChatSessionState,
    TurnStepTracker,
    analyze_slot_coverage,
    append_to_context_window,
    build_turn1_decision,
    chat_session_store,
    evaluate_and_build_followup,
    ingest_upload_file,
)
from src.text_processing.contracts import (
    CATEGORY_SLUG_MAP,
    DocumentChunk,
    ScriptGenerationError,
    ScriptGenerationRequest,
    script_stage_durations,
)
from src.text_processing.generator import ScriptGenerator
from src.text_processing.groq_pool import make_groq_client
from src.text_processing.moderation import DEFAULT_LLAMA_GUARD_MODEL, ContentModerator
from src.text_processing.parser import (
    DocumentParserError,
    max_bytes_for_extension,
    validate_turn_text_length,
)
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
            warm_category_prototypes(retriever, pipeline.template_store)
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

# Only the app's own scripts run. Styles allow 'unsafe-inline' for the style="" attributes in
# index.html. Audio and pictures come from signed Supabase Storage URLs (core and shards).
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://*.supabase.co",
    "media-src 'self' blob: https://*.supabase.co",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """No MIME sniffing and no full URL in Referer on every response; CSP on HTML pages."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return response


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
        "max_audio_seconds": max_audio_seconds,
        "script_title_max_chars": script_title_max_chars,
        "max_turn_text_chars": max_turn_text_chars,
        "max_pdf_size_bytes": max_pdf_size_bytes,
        "max_pdf_pages": max_pdf_pages,
        "max_text_file_bytes": max_text_file_bytes,
        "max_text_file_words": max_text_file_words,
        "file_size_limits_bytes": {
            ".pdf": max_pdf_size_bytes,
            ".md": max_text_file_bytes,
            ".txt": max_text_file_bytes,
        },
        "eta_buffer_s": eta_buffer_s,
        "script_telemetry": {
            "eta_buffer_s": eta_buffer_s,
            "chat_turn_step_durations_s": dict(CHAT_TURN_STEP_DURATIONS),
            "generate_stage_durations_s": script_stage_durations(5),
        },
        "auth": {key: CONSTANTS["auth"][key] for key in (
            "otp_length", "resend_cooldown_s", "unconfirmed_ttl_min"
        )},
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


@app.exception_handler(RecordingConsentRequiredError)
async def recording_consent_handler(request: Request, exc: RecordingConsentRequiredError):
    """403 while the user has recording turned off (Settings > Permissions)."""
    return JSONResponse(
        status_code=403,
        content={
            "error_code": "consent_required",
            "message": "Turn on recording in Settings to use this feature.",
        },
    )


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
    user: Annotated[CurrentUser, Depends(require_recording_consent)],
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


@app.post("/api/generate-script", status_code=202, response_model=None)
async def generate_script_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    repos: Annotated[Repos, Depends(get_repos)],
    topic: Annotated[str, Form()] = "",
    category: Annotated[str, Form()] = "",
    duration_min: Annotated[int, Form()] = 5,
    greeting: Annotated[str, Form()] = "",
    raw_text: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
    session_id: Annotated[str, Form()] = "",
    user_feedback: Annotated[str, Form()] = "",
) -> dict[str, Any] | JSONResponse:
    """Queue a background script generation job and return `202 {job_id, status}` (Brief §5.5).

    Invalid input answers 422; a running job or a full limit answers 429 (ADR-015).
    """
    pipeline = get_script_pipeline()
    user_id = str(user.id)

    # Validate user text inputs (2,000-word & 18,000-char caps) before writing temp files or jobs
    _validate_turn_text(user_feedback)
    _validate_turn_text(raw_text)

    pdf_path: str | None = None
    clean_topic = topic.strip()
    clean_session_id = session_id.strip() or None
    clean_feedback = user_feedback.strip() or None

    store = getattr(pipeline, "session_store", chat_session_store)
    sess = None
    if clean_session_id:
        sess = store.get(clean_session_id, user_id=user_id)
        if sess:
            if not clean_topic:
                clean_topic = getattr(sess, "topic", None) or sess.initial_prompt or ""
            if not category and sess.category:
                category = sess.category
            if duration_min == 5 and sess.duration_min:
                duration_min = sess.duration_min

    # Order matters (ADR-015): bad input and a busy user are refused before anything is counted,
    # and the limits are counted before an upload is written to disk.
    validate_generate_input(clean_topic, duration_min, clean_feedback)
    has_pdf = (
        pdf is not None and (pdf.filename or "").lower().endswith(".pdf") and pdf.size != 0
    )
    reject_gibberish(user_feedback, raw_text, has_file=has_pdf)
    await run_in_threadpool(
        guard_category_generate,
        pipeline,
        session=sess,
        category=category,
        topic=clean_topic,
        raw_text=raw_text,
    )
    if pipeline.has_active_job(user_id):
        return rate_limited_response(job_running_block())
    block = await run_in_threadpool(
        check_generate_limits,
        repos.rate_limits,
        user_id,
        is_regenerate=clean_feedback is not None,
        duration_min=duration_min,
    )
    if block is not None:
        return rate_limited_response(block)

    if pdf is not None and pdf.filename:
        # Fixed ".pdf" suffix; enforce the 25 MB PDF ceiling (not the 100 MB audio ceiling).
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf_path = tmp_file.name
        try:
            await run_in_threadpool(
                save_upload_limited,
                pdf,
                Path(pdf_path),
                max_bytes=max_pdf_size_bytes,
                audio=False,
            )
        except AudioRejected as exc:
            Path(pdf_path).unlink(missing_ok=True)
            raise ScriptGenerationError(
                error_code="file_too_large" if exc.code == "too_large" else exc.code,
                message=exc.message,
                status_code=422,
            ) from exc
        except Exception:
            Path(pdf_path).unlink(missing_ok=True)
            raise

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
    # Checked again: another request of this user may have created a job during the awaits above.
    # Nothing is awaited between this check and create_job, so two requests cannot both pass.
    if pipeline.has_active_job(user_id):
        if pdf_path:
            Path(pdf_path).unlink(missing_ok=True)
        return rate_limited_response(job_running_block())
    job = pipeline.create_job(user_id=user_id, duration_min=duration_min)
    background_tasks.add_task(pipeline.run_job, job.job_id, req, True)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "steps": [dict(s) for s in job.steps],
        "eta_buffer_s": job.eta_buffer_s,
        "estimated_total_s": job.estimated_total_s,
        "estimated_remaining_s": job.estimated_remaining_s,
    }


class SelectTopicPayload(BaseModel):
    session_id: str
    template_id: str | None = None


def _resolve_groq_client(pipeline: ScriptGenerationPipeline) -> Any | None:
    """Resolve Groq client without silently passing None when GROQ_API_KEYS is configured."""
    client = getattr(pipeline.template_engine, "client", None)
    if client is not None:
        return client
    llm_gen = getattr(pipeline, "llm_generator", None)
    if isinstance(llm_gen, ScriptGenerator) and llm_gen.client is not None:
        return llm_gen.client
    return make_groq_client()


def _validate_turn_text(text: str) -> None:
    """Enforce per-turn text limits before moderation, embeddings, or LLM calls."""
    if not text:
        return
    try:
        validate_turn_text_length(
            text, max_chars=max_turn_text_chars, max_words=composer_max_words
        )
    except DocumentParserError as exc:
        raise ScriptGenerationError(
            error_code=exc.error_code,
            message=exc.message,
            status_code=422,
        ) from exc


async def _read_document_upload_limited(
    upload: UploadFile, *, chunk_size: int = upload_read_chunk_bytes
) -> bytes:
    """Stream-read an uploaded .pdf/.md/.txt file up to its per-type byte ceiling."""
    filename = upload.filename or ""
    try:
        max_bytes = max_bytes_for_extension(filename)
    except DocumentParserError as exc:
        raise ScriptGenerationError(
            error_code=exc.error_code,
            message=exc.message,
            status_code=422,
        ) from exc

    declared_size = getattr(upload, "size", None)
    suffix = Path(filename).suffix.lower()
    if isinstance(declared_size, int) and declared_size > max_bytes:
        raise ScriptGenerationError(
            error_code="file_too_large",
            message=f"Uploaded '{suffix}' file exceeds {max_bytes} bytes limit.",
            status_code=422,
        )

    buf = bytearray()
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise ScriptGenerationError(
                error_code="file_too_large",
                message=f"Uploaded '{suffix}' file exceeds {max_bytes} bytes limit.",
                status_code=422,
            )

    if not buf:
        raise ScriptGenerationError(
            error_code="empty_file",
            message="The uploaded file is empty.",
            status_code=422,
        )
    return bytes(buf)


_chat_turn_jobs: dict[str, dict[str, Any]] = {}
_chat_turn_jobs_lock = threading.Lock()
_CHAT_TURN_JOBS_CAP = chat_turn_jobs_max_capacity


def _create_chat_turn_job(user_id: str, tracker: TurnStepTracker) -> str:
    job_id = str(uuid4())
    snap = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "queued",
        **tracker.to_telemetry(),
        "result": None,
        "error_code": None,
        "message": None,
    }
    with _chat_turn_jobs_lock:
        if len(_chat_turn_jobs) >= _CHAT_TURN_JOBS_CAP:
            oldest = next(iter(_chat_turn_jobs))
            del _chat_turn_jobs[oldest]
        _chat_turn_jobs[job_id] = snap
    return job_id


def _sync_chat_turn_job(
    job_id: str | None,
    tracker: TurnStepTracker,
    *,
    status: str = "running",
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    message: str | None = None,
    extra: dict[str, str] | None = None,
) -> None:
    if not job_id:
        return
    with _chat_turn_jobs_lock:
        job = _chat_turn_jobs.get(job_id)
        if job is None:
            return
        job["status"] = status
        job.update(tracker.to_telemetry())
        job["result"] = result
        job["error_code"] = error_code
        job["message"] = message
        job.update(extra or {})


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
    tracker = TurnStepTracker(["validating_input", "moderating", "matching_templates"])
    tracker.start("validating_input")

    # 1. Enforce per-turn text and upload byte limits BEFORE moderation, embeddings, or LLM
    _validate_turn_text(prompt)

    file_chunks: list[DocumentChunk] = []
    filename: str = ""
    if file is not None and file.filename:
        filename = file.filename
        file_bytes = await _read_document_upload_limited(file)
        try:
            raw_chunks = await run_in_threadpool(ingest_upload_file, file_bytes, filename)
            file_chunks = sanitize_chunks(raw_chunks)
        except DocumentParserError as exc:
            raise ScriptGenerationError(
                error_code=exc.error_code,
                message=exc.message,
                status_code=422,
            ) from exc

    reject_gibberish(prompt, has_file=bool(file_chunks))

    def _run_suggest_sync() -> dict[str, Any]:
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

        clean_prompt = sanitize_text(prompt).strip() if prompt else ""

        tracker.start("moderating")
        if clean_prompt:
            pipeline.moderator.assert_safe(clean_prompt, user_id=user_id)
        if file_chunks:
            file_text = "\n".join(c.content for c in file_chunks[:moderation_max_chunks])
            if file_text:
                pipeline.moderator.assert_safe(file_text, user_id=user_id)

        tracker.start("matching_templates")
        # Ranked and checked before the session is created or changed.
        target_category = category or (session.category if session else "")
        chunks = [*(session.chunks if session else []), *file_chunks]

        query = clean_prompt
        if not query and chunks:
            query = " ".join(c.content for c in chunks[:suggest_query_max_chunks])

        suggestion_res = pipeline.template_store.suggest_topics(
            category_slug=target_category,
            duration_min=duration_min or (session.duration_min if session else duration_min),
            query=query,
            retriever=getattr(pipeline.template_engine, "retriever", None),
        )
        may_remember = guard_category_suggest(
            pipeline,
            session=session,
            category=target_category,
            prompt=clean_prompt,
            file_chunks=file_chunks,
            has_template_match=bool(query.strip()) and not suggestion_res.recommend_free_topic,
            client=_resolve_groq_client(pipeline),
            limiter=getattr(pipeline.template_engine, "limiter", None),
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
            id_offset = len(session.chunks)
            for idx, chunk in enumerate(file_chunks, start=1):
                chunk.chunk_id = id_offset + idx
            session.chunks.extend(file_chunks)
            retriever = getattr(pipeline.template_engine, "retriever", None)
            if retriever is not None:
                session.chunk_embeddings = retriever.encode_chunks(session.chunks)

        store.put(session)
        if may_remember:
            remember_category_decision(session)
        tracker.finish()
        res = suggestion_res.to_dict()
        res["session_id"] = session.session_id
        res["topics"] = list(res["suggestions"])
        res["files_loaded"] = list(session.files_loaded)
        res.update(tracker.to_telemetry())
        return res

    return await run_in_threadpool(_run_suggest_sync)


@app.post("/api/script-chat/select-topic")
async def script_chat_select_topic_endpoint(
    payload: SelectTopicPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Turn 1: lock the topic/mode, reply, and allow Generate if the context is sufficient.

    `topic_clear` is false only for a Write Freely prompt that names no topic yet.
    """
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    store = getattr(pipeline, "session_store", chat_session_store)
    tracker = TurnStepTracker(["validating_input", "analyzing_slots", "analyzing_with_llm"])
    tracker.start("validating_input")

    def _run_select_sync() -> dict[str, Any]:
        session = store.get(payload.session_id, user_id=user_id)
        if session is None:
            raise ScriptGenerationError(
                error_code="session_not_found",
                message=f"Session '{payload.session_id}' not found.",
                status_code=404,
            )

        lock_fn = getattr(store, "turn_lock", None)
        lock = lock_fn(session.session_id) if callable(lock_fn) else threading.RLock()
        with lock:
            tracker.start("analyzing_slots")
            template_doc = None
            is_free_topic = not bool(payload.template_id)
            if payload.template_id:
                template_doc = pipeline.template_store.get(payload.template_id)
                if template_doc is None:
                    raise ScriptGenerationError(
                        error_code="template_not_found",
                        message=f"Template '{payload.template_id}' not found.",
                        status_code=404,
                    )

            was_template = session.selected_template_id is not None
            session.selected_template_id = payload.template_id
            session.gather_turns = 0
            session.assistant_turn = 1
            session.ready_to_generate = False
            retriever = getattr(pipeline.template_engine, "retriever", None)

            if template_doc is not None:
                session.topic = template_doc.metadata.topic
                cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
                    template_document=template_doc,
                    chunks=session.chunks,
                    chunk_embeddings=session.chunk_embeddings,
                    retriever=retriever,
                    prompt=session.initial_prompt,
                    user_notes=session.get_context_texts(include_summary=True),
                )
                session.coverage_ratio = cov_ratio
                session.missing_entities = missing_entities
                session.missing_groups = missing_groups
            else:
                session.selected_template_id = None
                if was_template or not session.topic:
                    session.topic = session.initial_prompt or session.category or "Custom Speech"
                session.missing_entities = []
                session.missing_groups = []
                session.coverage_ratio = 0.0

            tracker.start("analyzing_with_llm")
            client = _resolve_groq_client(pipeline)
            limiter = getattr(pipeline.template_engine, "limiter", None)
            model_chain = getattr(pipeline.template_engine, "model_chain", None)
            decision = build_turn1_decision(
                topic=session.topic or session.category or "your speech",
                category=session.category,
                duration_min=session.duration_min,
                is_free_topic=is_free_topic,
                initial_prompt=session.initial_prompt,
                files_loaded=session.files_loaded,
                chunks=session.chunks,
                coverage_ratio=session.coverage_ratio,
                missing_entities=session.missing_entities,
                missing_groups=session.missing_groups,
                client=client,
                model_chain=model_chain,
                limiter=limiter,
            )
            session.last_question = decision.reply_message
            session.missing_items = list(decision.missing_items)
            session.ready_to_generate = decision.can_generate

            tracker.finish()
            store.put(session)
            return {
                "session_id": session.session_id,
                "template_id": session.selected_template_id,
                "selected_template_id": session.selected_template_id,
                "ready_to_generate": decision.can_generate,
                "can_generate": decision.can_generate,
                "topic_clear": decision.topic_clear,
                "assistant_turn": 1,
                "coverage_ratio": session.coverage_ratio,
                "missing_entities": session.missing_entities,
                "missing_groups": session.missing_groups,
                "missing_items": list(decision.missing_items),
                "context_compacted": False,
                "reply_message": decision.reply_message,
                **tracker.to_telemetry(),
            }

    return await run_in_threadpool(_run_select_sync)


def _execute_chat_message(
    *,
    pipeline: ScriptGenerationPipeline,
    session: ChatSessionState,
    user_id: str,
    clean_msg: str,
    file_chunks: list[DocumentChunk],
    filename: str,
    tracker: TurnStepTracker,
    job_id: str | None = None,
) -> dict[str, Any]:
    store = getattr(pipeline, "session_store", chat_session_store)
    lock_fn = getattr(store, "turn_lock", None)
    lock = lock_fn(session.session_id) if callable(lock_fn) else threading.RLock()
    with lock:
        return _execute_chat_message_locked(
            store=store,
            pipeline=pipeline,
            session=session,
            user_id=user_id,
            clean_msg=clean_msg,
            file_chunks=file_chunks,
            filename=filename,
            tracker=tracker,
            job_id=job_id,
        )


def _execute_chat_message_locked(
    *,
    store: Any,
    pipeline: ScriptGenerationPipeline,
    session: ChatSessionState,
    user_id: str,
    clean_msg: str,
    file_chunks: list[DocumentChunk],
    filename: str,
    tracker: TurnStepTracker,
    job_id: str | None = None,
) -> dict[str, Any]:
    tracker.start("moderating")
    _sync_chat_turn_job(job_id, tracker)
    if clean_msg:
        pipeline.moderator.assert_safe(clean_msg, user_id=user_id)
    if file_chunks:
        file_text = "\n".join(c.content for c in file_chunks[:moderation_max_chunks])
        if file_text:
            pipeline.moderator.assert_safe(file_text, user_id=user_id)
    may_remember = False
    if file_chunks:
        may_remember = guard_category_message_file(
            pipeline,
            session,
            clean_msg,
            file_chunks,
            client=_resolve_groq_client(pipeline),
            limiter=getattr(pipeline.template_engine, "limiter", None),
        )

    tracker.start("updating_context")
    _sync_chat_turn_job(job_id, tracker)
    session.gather_turns += 1
    session.assistant_turn = max(2, session.gather_turns + 1)

    retriever = getattr(pipeline.template_engine, "retriever", None)
    client = _resolve_groq_client(pipeline)
    limiter = getattr(pipeline.template_engine, "limiter", None)
    model_chain = getattr(pipeline.template_engine, "model_chain", None)

    if file_chunks:
        session.files_loaded.append(filename)
        id_offset = len(session.chunks)
        for idx, chunk in enumerate(file_chunks, start=1):
            chunk.chunk_id = id_offset + idx
        session.chunks.extend(file_chunks)
        if retriever is not None:
            session.chunk_embeddings = retriever.encode_chunks(session.chunks)

    def _on_compact_start() -> None:
        tracker.start("compacting_context")
        _sync_chat_turn_job(job_id, tracker)

    context_compacted = False
    if clean_msg:
        _, context_compacted = append_to_context_window(
            session,
            clean_msg,
            turn=session.gather_turns,
            source="chat",
            client=client,
            limiter=limiter,
            on_compact_start=_on_compact_start,
        )
    elif file_chunks and filename:
        _, context_compacted = append_to_context_window(
            session,
            f"Uploaded reference file: {filename}",
            turn=session.gather_turns,
            source="file_summary",
            client=client,
            limiter=limiter,
            on_compact_start=_on_compact_start,
        )

    if context_compacted:
        tracker.done("compacting_context")
        _sync_chat_turn_job(job_id, tracker)
    else:
        tracker.done("updating_context")
        tracker.skip("compacting_context")
        _sync_chat_turn_job(job_id, tracker)

    tracker.start("analyzing_with_llm")
    _sync_chat_turn_job(job_id, tracker)

    if session.selected_template_id:
        template_doc = pipeline.template_store.get(session.selected_template_id)
        if template_doc:
            session.topic = template_doc.metadata.topic
            cov_ratio, missing_entities, missing_groups = analyze_slot_coverage(
                template_document=template_doc,
                chunks=session.chunks,
                chunk_embeddings=session.chunk_embeddings,
                retriever=retriever,
                prompt=session.initial_prompt,
                user_notes=session.get_context_texts(include_summary=True),
            )
            session.coverage_ratio = cov_ratio
            session.missing_entities = missing_entities
            session.missing_groups = missing_groups

    topic = getattr(session, "topic", None) or session.initial_prompt or "your speech"
    decision = evaluate_and_build_followup(
        topic=topic,
        category=session.category,
        duration_min=session.duration_min,
        is_free_topic=(session.selected_template_id is None),
        compacted_summary=session.compacted_summary,
        context_entries=session.context_window,
        latest_user_answer=clean_msg,
        last_question=session.last_question,
        missing_entities=session.missing_entities,
        missing_groups=session.missing_groups,
        coverage_ratio=session.coverage_ratio,
        files_loaded=session.files_loaded,
        initial_prompt=session.initial_prompt,
        client=client,
        model_chain=model_chain,
        limiter=limiter,
    )
    session.ready_to_generate = decision.sufficient
    session.missing_items = list(decision.missing_items)
    session.last_question = decision.reply_message

    tracker.finish()
    store.put(session)
    if may_remember:
        remember_category_decision(session)
    result = {
        "session_id": session.session_id,
        "reply_message": decision.reply_message,
        "ready_to_generate": session.ready_to_generate,
        "can_generate": True,
        "assistant_turn": session.assistant_turn,
        "coverage_ratio": session.coverage_ratio,
        "missing_entities": session.missing_entities,
        "missing_groups": session.missing_groups,
        "missing_items": list(decision.missing_items),
        "context_compacted": context_compacted,
        "compaction_count": session.compaction_count,
        "gather_turns": session.gather_turns,
        "files_loaded": list(session.files_loaded),
        **tracker.to_telemetry(),
    }
    _sync_chat_turn_job(job_id, tracker, status="completed", result=result)
    return result


async def _prepare_chat_message_inputs(
    *,
    pipeline: ScriptGenerationPipeline,
    user_id: str,
    session_id: str,
    message: str,
    file: UploadFile | None,
) -> tuple[ChatSessionState, str, list[DocumentChunk], str]:
    store = getattr(pipeline, "session_store", chat_session_store)
    session = store.get(session_id, user_id=user_id)
    if session is None:
        raise ScriptGenerationError(
            error_code="session_not_found",
            message=f"Session '{session_id}' not found.",
            status_code=404,
        )

    # Enforce per-turn text and upload byte limits BEFORE moderation, embeddings, or LLM
    _validate_turn_text(message)

    file_chunks: list[DocumentChunk] = []
    filename = ""
    if file is not None and file.filename:
        filename = file.filename
        file_bytes = await _read_document_upload_limited(file)
        try:
            raw_chunks = await run_in_threadpool(ingest_upload_file, file_bytes, filename)
            file_chunks = sanitize_chunks(raw_chunks)
        except DocumentParserError as exc:
            raise ScriptGenerationError(
                error_code=exc.error_code,
                message=exc.message,
                status_code=422,
            ) from exc

    reject_gibberish(message, has_file=bool(file_chunks))
    clean_msg = sanitize_text(message).strip() if message else ""
    if not clean_msg and not file_chunks:
        raise ScriptGenerationError(
            error_code="empty_input",
            message="Please provide a message or a document.",
            status_code=422,
        )
    return session, clean_msg, file_chunks, filename


@app.post("/api/script-chat/message")
async def script_chat_message_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session_id: Annotated[str, Form(...)],
    message: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    """Turn 2+: Bound context, optionally compact, evaluate with Groq, and keep loop open."""
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    tracker = TurnStepTracker(
        [
            "validating_input",
            "moderating",
            "updating_context",
            "compacting_context",
            "analyzing_with_llm",
        ]
    )
    tracker.start("validating_input")
    session, clean_msg, file_chunks, filename = await _prepare_chat_message_inputs(
        pipeline=pipeline,
        user_id=user_id,
        session_id=session_id,
        message=message,
        file=file,
    )
    return await run_in_threadpool(
        lambda: _execute_chat_message(
            pipeline=pipeline,
            session=session,
            user_id=user_id,
            clean_msg=clean_msg,
            file_chunks=file_chunks,
            filename=filename,
            tracker=tracker,
        )
    )


def _run_chat_message_job(
    job_id: str,
    pipeline: ScriptGenerationPipeline,
    session: ChatSessionState,
    user_id: str,
    clean_msg: str,
    file_chunks: list[DocumentChunk],
    filename: str,
    tracker: TurnStepTracker,
) -> None:
    try:
        _execute_chat_message(
            pipeline=pipeline,
            session=session,
            user_id=user_id,
            clean_msg=clean_msg,
            file_chunks=file_chunks,
            filename=filename,
            tracker=tracker,
            job_id=job_id,
        )
    except ScriptGenerationError as exc:
        tracker.fail()
        _sync_chat_turn_job(
            job_id,
            tracker,
            status="failed",
            error_code=exc.error_code,
            message=exc.message,
            extra=getattr(exc, "extra", None),
        )
    except Exception as exc:
        tracker.fail()
        _sync_chat_turn_job(
            job_id,
            tracker,
            status="failed",
            error_code="generation_unavailable",
            message=str(exc),
        )


@app.post("/api/script-chat/message/jobs", status_code=202)
async def create_script_chat_message_job_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    session_id: Annotated[str, Form(...)],
    message: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    """Queue a Turn 2+ message turn and return 202 with live step/ETA polling job_id."""
    pipeline = get_script_pipeline()
    user_id = str(user.id)
    tracker = TurnStepTracker(
        [
            "validating_input",
            "moderating",
            "updating_context",
            "compacting_context",
            "analyzing_with_llm",
        ]
    )
    tracker.start("validating_input")
    session, clean_msg, file_chunks, filename = await _prepare_chat_message_inputs(
        pipeline=pipeline,
        user_id=user_id,
        session_id=session_id,
        message=message,
        file=file,
    )
    tracker.done("validating_input")
    job_id = _create_chat_turn_job(user_id, tracker)
    background_tasks.add_task(
        _run_chat_message_job,
        job_id,
        pipeline,
        session,
        user_id,
        clean_msg,
        file_chunks,
        filename,
        tracker,
    )
    with _chat_turn_jobs_lock:
        snap = dict(_chat_turn_jobs[job_id])
    snap.pop("user_id", None)
    return snap


@app.get("/api/script-chat/jobs/{job_id}")
async def get_script_chat_job_endpoint(
    job_id: str, user: Annotated[CurrentUser, Depends(get_current_user)]
) -> JSONResponse:
    """Poll step progress, +10s buffered ETA, and result of an async chat turn job."""
    with _chat_turn_jobs_lock:
        job = _chat_turn_jobs.get(job_id)
        snap = dict(job) if job and job.get("user_id") == str(user.id) else None
    if snap is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "job_not_found", "message": f"Job '{job_id}' not found."},
        )
    snap.pop("user_id", None)
    return JSONResponse(status_code=200, content=snap)


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
