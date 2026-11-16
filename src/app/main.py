import json
import logging
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src.app.config import (
    max_request_bytes,
    max_script_chars,
    max_script_words,
    max_upload_bytes,
    settings,
)
from src.app.db.factory import Repos, get_repos
from src.app.db.models import (
    NewSession,
    SessionRow,
    StorageError,
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
from src.app.routes import baselines
from src.app.uploads import BodySizeLimitMiddleware, safe_upload_path, save_upload_limited
from src.audio_processing.contracts import AudioRejected, SttUnavailable, VadParams
from src.audio_processing.pipeline import evaluate_session
from src.text_processing.contracts import (
    CATEGORY_SLUG_MAP,
    ScriptGenerationError,
    ScriptGenerationRequest,
)
from src.text_processing.pipeline import ScriptGenerationPipeline

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI()
app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_request_bytes)
logger = logging.getLogger(__name__)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app.include_router(baselines.router)

_script_pipeline: ScriptGenerationPipeline | None = None


def get_script_pipeline() -> ScriptGenerationPipeline:
    """Return the process-wide `ScriptGenerationPipeline` singleton."""
    global _script_pipeline
    if _script_pipeline is None:
        _script_pipeline = ScriptGenerationPipeline()
    return _script_pipeline


class SaveScriptPayload(BaseModel):
    """Request body for `POST /api/scripts`."""

    title: str = "Untitled Script"
    script: str
    duration_min: int | None = None
    source: str = "user"



@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "demo_ui.html")


@app.exception_handler(AudioRejected)
async def audio_rejected_handler(request: Request, exc: AudioRejected):
    """
    Xử lý lỗi HTTP 422 khi probe hoặc decode từ chối file audio[cite: 1].
    """
    return JSONResponse(
        status_code=422,
        content={"error_code": exc.code, "message": exc.message}
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
    """Compact older full sessions to keep only the newest full set."""
    try:
        rows = repos.sessions.list_full_beyond(
            user_id, keep=settings.retention_full_sessions
        )
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


def _save_result_to_history(
    *,
    repos: Repos,
    user_id: UUID,
    script: str,
    result,
    source_audio_path: Path | None,
    baseline_id: UUID | None = None,
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
                result.audio.get("duration_s")
                if isinstance(result.audio, dict)
                else None
            ),
            stt_provider=(stt.get("provider") if isinstance(stt, dict) else None),
            stt_model=(stt.get("model") if isinstance(stt, dict) else None),
            topic=None,
            accent=None,
            baseline_id=baseline_id,
            script_id=None,
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


@app.get("/api/sessions")
async def list_sessions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    cursor: str | None = None,
):
    """Return a page of the user's session summaries plus a next cursor when more exist."""
    query_limit = min(limit + 1, 20)
    try:
        rows = await run_in_threadpool(
            repos.sessions.list_sessions, user.id, query_limit, cursor
        )
    except StorageError:
        logger.exception("Could not list sessions for user %s", user.id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "invalid_cursor"})
    has_more = len(rows) > limit
    page = rows[:limit]
    if limit == 20 and len(rows) == limit:
        probe_cursor = encode_cursor(page[-1].created_at, page[-1].id)
        try:
            has_more = bool(await run_in_threadpool(
                repos.sessions.list_sessions, user.id, 1, probe_cursor
            ))
        except StorageError:
            logger.exception("Could not check session page for user %s", user.id)
            return JSONResponse(
                status_code=503,
                content={"error": "session_storage_unavailable"},
            )
    payload = {
        "items": [row.model_dump(mode="json") for row in page],
        "next_cursor": (
            encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
        ),
    }
    return payload


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Return the full session payload or a compact summary for older sessions."""
    try:
        row = await run_in_threadpool(
            repos.sessions.get_session, user.id, session_id
        )
    except StorageError:
        logger.exception("Could not load session %s", session_id)
        return JSONResponse(
            status_code=503,
            content={"error": "session_storage_unavailable"},
        )
    if row is None:
        return JSONResponse(status_code=404, content={"error": "session_not_found"})

    data = row.model_dump(
        mode="json", exclude={"user_id", "audio_path", "series_path"}
    )

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
        row = await run_in_threadpool(
            repos.sessions.get_session, user.id, session_id
        )
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
        deleted = await run_in_threadpool(
            repos.sessions.delete_session, user.id, session_id
        )
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
            content={"error_code": "script_empty",
                     "message": "The practice text is empty. Choose or write a text first."},
        )
    if len(script) > max_script_chars or len(script.split()) > max_script_words:
        return JSONResponse(
            status_code=422,
            content={"error_code": "script_too_long",
                     "message": f"The practice text is too long (maximum {max_script_words} "
                                "words). Please use a shorter text."},
        )
    return None


@app.post("/api/evaluate")
async def evaluate_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    audio: Annotated[UploadFile, File()],
    script: Annotated[str, Form()],
    baseline_profile: Annotated[str, Form()] = "",
):
    """
    Score one practice session and save it to the user's history.

    The baseline is loaded from the DB for the current user; the client's `baseline_profile`
    is accepted but ignored (the old UI still sends it). When settings.baseline_required is
    on and the user has no baseline, return 409.
    """
    script_error = _validate_script(script)
    if script_error is not None:
        return script_error

    # Default VAD settings
    vad_params = VadParams()

    try:
        baseline_row = await run_in_threadpool(repos.baselines.get_current_baseline, user.id)
    except StorageError:
        logger.exception("Could not load baseline")
        return JSONResponse(
            status_code=503,
            content={"error_code": "baseline_unavailable",
                     "message": "Could not load the current baseline"},
        )
    if baseline_row is None and settings.baseline_required:
        return JSONResponse(
            status_code=409,
            content={"error_code": "baseline_required",
                     "message": "Record a baseline before practising"},
        )
    baseline = baselines.to_baseline_profile(baseline_row) if baseline_row else None

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = safe_upload_path(Path(temp_dir), audio.filename)
        save_upload_limited(audio, audio_path, max_bytes=max_upload_bytes)

        # FFmpeg + VAD + STT + scoring take seconds: run them in a worker thread so the
        # event loop keeps serving other requests (polling, other users) meanwhile.
        result = await run_in_threadpool(
            evaluate_session,
            audio_path=audio_path,
            script=script,
            baseline=baseline,
            vad_params=vad_params,
        )

        session_id = None
        saved = False
        save_started = perf_counter()
        try:
            session_id = await run_in_threadpool(
                _save_result_to_history,
                repos=repos,
                user_id=user.id,
                script=script,
                result=result,
                source_audio_path=audio_path,
                baseline_id=baseline_row.id if baseline_row else None,
            )
            saved = session_id is not None
        except Exception:
            logger.exception("Failed to save evaluation result to session history")
            saved = False
            session_id = None
        finally:
            logger.info(
                "Evaluation session save attempt took %.3f seconds",
                perf_counter() - save_started,
            )

        return result.model_copy(
            update={"session_id": session_id, "saved": saved}
        ).model_dump(mode="json")


@app.exception_handler(ScriptGenerationError)
async def script_generation_error_handler(_: Request, exc: ScriptGenerationError) -> JSONResponse:
    """Return structured JSON `{error_code, message}` for Script Generation errors (Brief §5.7)."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


def _resolve_user_id(request: Request, explicit_user_id: str | None = None) -> str:
    if explicit_user_id and explicit_user_id.strip():
        return explicit_user_id.strip()
    header_uid = request.headers.get("X-User-Id", "").strip()
    return header_uid or "anonymous"


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
    request: Request,
    background_tasks: BackgroundTasks,
    topic: Annotated[str, Form(...)],
    category: Annotated[str, Form()] = "",
    duration_min: Annotated[int, Form()] = 5,
    greeting: Annotated[str, Form()] = "",
    raw_text: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    """Queue a background script generation job and return `202 {job_id, status}` (Brief §5.5)."""
    pipeline = get_script_pipeline()
    user_id = _resolve_user_id(request)
    pdf_path: str | None = None
    if pdf is not None and pdf.filename:
        # Fixed ".pdf" suffix; the parser checks the %PDF- signature and the 25 MB limit.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf_path = tmp_file.name
        save_upload_limited(pdf, Path(pdf_path), max_bytes=max_upload_bytes)

    req = ScriptGenerationRequest(
        topic=topic,
        category=category or None,
        duration_min=duration_min,
        pdf_path=pdf_path,
        raw_text=raw_text or None,
        greeting=greeting or None,
        user_id=user_id,
    )
    job = pipeline.create_job(user_id=user_id)
    background_tasks.add_task(pipeline.run_job, job.job_id, req, True)
    return {"job_id": job.job_id, "status": job.status}


@app.get("/api/generate-script/{job_id}")
async def get_generate_script_job_endpoint(job_id: str) -> JSONResponse:
    """Poll status, progress, and result of a script generation job (Brief §5.5)."""
    job = get_script_pipeline().get_job(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "job_not_found", "message": f"Job '{job_id}' not found."},
        )
    return JSONResponse(status_code=200, content=job.to_dict())


@app.post("/api/scripts", status_code=201)
async def create_saved_script_endpoint(
    request: Request, payload: SaveScriptPayload
) -> dict[str, Any]:
    """Save a generated or user-written script after Stage 4 moderation (Brief §5.7, §5.8)."""
    user_id = _resolve_user_id(request)
    return get_script_pipeline().save_script(
        user_id=user_id,
        title=payload.title,
        script=payload.script,
        duration_min=payload.duration_min,
        source=payload.source,
    )


@app.get("/api/scripts")
async def list_saved_scripts_endpoint(request: Request) -> dict[str, Any]:
    """List saved scripts for the current user."""
    user_id = _resolve_user_id(request)
    return {"scripts": get_script_pipeline().list_scripts(user_id=user_id)}


@app.get("/api/scripts/{script_id}")
async def get_saved_script_endpoint(script_id: str, request: Request) -> JSONResponse:
    """Get a single saved script owned by the current user."""
    user_id = _resolve_user_id(request)
    item = get_script_pipeline().get_script(script_id=script_id, user_id=user_id)
    if item is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "script_not_found", "message": "Script not found."},
        )
    return JSONResponse(status_code=200, content=item)


@app.delete("/api/scripts/{script_id}")
async def delete_saved_script_endpoint(script_id: str, request: Request) -> JSONResponse:
    """Delete a saved script owned by the current user."""
    user_id = _resolve_user_id(request)
    deleted = get_script_pipeline().delete_script(script_id=script_id, user_id=user_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"error_code": "script_not_found", "message": "Script not found."},
        )
    return JSONResponse(status_code=200, content={"deleted": True, "id": script_id})
