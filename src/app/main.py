import json
import logging
import tempfile
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
    max_request_bytes,
    max_saved_scripts,
    max_script_chars,
    max_script_words,
    max_upload_bytes,
    missing_required_settings,
    settings,
)
from src.app.constants import CONSTANTS
from src.app.db.factory import Repos, get_repos
from src.app.db.models import (
    NewScript,
    NewSession,
    ScriptDuration,
    ScriptRow,
    ScriptSource,
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
from src.audio_processing.pipeline import evaluate_session
from src.text_processing.contracts import (
    CATEGORY_SLUG_MAP,
    ScriptGenerationError,
    ScriptGenerationRequest,
)
from src.text_processing.pipeline import ScriptGenerationPipeline
from src.text_processing.sanitizer import sanitize_text

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse to start when a required key is missing (fail at startup, not mid-demo)."""
    missing = missing_required_settings(settings)
    if missing:
        logger.critical("Missing required settings in .env: %s", ", ".join(missing))
        raise RuntimeError("Missing required settings in .env: " + ", ".join(missing))
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_request_bytes)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app.include_router(auth_routes.router)
app.include_router(profile_routes.router)
app.include_router(baselines.router)
app.include_router(practice.router)
app.include_router(coach.router)

_script_pipeline: ScriptGenerationPipeline | None = None


def get_script_pipeline() -> ScriptGenerationPipeline:
    """Return the process-wide `ScriptGenerationPipeline` singleton."""
    global _script_pipeline
    if _script_pipeline is None:
        _script_pipeline = ScriptGenerationPipeline()
    return _script_pipeline


class SaveScriptPayload(BaseModel):
    """Request body for `POST /api/scripts`; values match the `scripts` table.

    `source`: `generated_template` / `generated_llm` for Script Pipeline output (its
    `GeneratedScript.source` "template" / "llm"), `written` for text the user typed.
    """

    title: str = Field(default="Untitled Script", max_length=200)
    body: str
    source: ScriptSource
    duration_min: ScriptDuration | None = None
    topic: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    template_id: str | None = Field(default=None, max_length=200)
    models_used: list[str] = Field(default_factory=list, max_length=10)
    citations: list[dict] = Field(default_factory=list, max_length=500)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/config")
async def web_config() -> dict[str, Any]:
    """The [web] section of app_constants.toml for the browser (no secrets in it)."""
    return {**CONSTANTS["web"], "retry": {key: CONSTANTS["retry"][key] for key in (
        "sentence_min_error_ratio", "word_max_seconds", "sentence_max_seconds", "clip_pad_s"
    )}}


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
    """Compact older full sessions to keep only the newest full set."""
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

    Asks for `limit + 1` rows to know if another page exists. The repo caps `limit` at 20,
    so for `limit == 20` one extra 1-row call checks the next page. Raises the repo's
    StorageError, or ValueError for a bad cursor.
    """
    rows = await run_in_threadpool(list_rows, user_id, min(limit + 1, 20), cursor)
    has_more = len(rows) > limit
    page = rows[:limit]
    if limit == 20 and len(rows) == limit:
        probe_cursor = encode_cursor(page[-1].created_at, page[-1].id)
        has_more = bool(await run_in_threadpool(list_rows, user_id, 1, probe_cursor))
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    return page, next_cursor


@app.get("/api/sessions")
async def list_sessions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
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
    session_topic = topic.strip()[:MAX_TOPIC_CHARS] or (script_row.topic if script_row else None)

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

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = safe_upload_path(Path(temp_dir), audio.filename)
        # Copying up to 100 MB is blocking file I/O: keep it off the event loop
        await run_in_threadpool(save_upload_limited, audio, audio_path, max_bytes=max_upload_bytes)

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
            accent = await run_in_threadpool(_load_profile_accent, repos, user.id)
            session_id = await run_in_threadpool(
                _save_result_to_history,
                repos=repos,
                user_id=user.id,
                script=script,
                result=result,
                source_audio_path=audio_path,
                baseline_id=baseline_row.id if baseline_row else None,
                script_id=script_row.id if script_row else None,
                topic=session_topic,
                accent=accent,
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

        return result.model_copy(update={"session_id": session_id, "saved": saved}).model_dump(
            mode="json"
        )


@app.exception_handler(ScriptGenerationError)
async def script_generation_error_handler(_: Request, exc: ScriptGenerationError) -> JSONResponse:
    """Return structured JSON `{error_code, message}` for Script Generation errors (Brief §5.7)."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


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
    topic: Annotated[str, Form(...)],
    category: Annotated[str, Form()] = "",
    duration_min: Annotated[int, Form()] = 5,
    greeting: Annotated[str, Form()] = "",
    raw_text: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
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
    return row.model_dump(mode="json", exclude={"user_id", "content_hash"})


def _save_script_row(repos: Repos, user_id: UUID, data: NewScript) -> tuple[ScriptRow, bool]:
    """Return (row, created). The same text saved again returns the existing row."""
    existing = repos.scripts.find_script_by_hash(user_id, data.content_hash)
    if existing is not None:
        return existing, False
    if repos.scripts.count_scripts(user_id) >= max_saved_scripts:
        raise ScriptGenerationError(
            "rate_limited",
            f"Maximum saved scripts limit ({max_saved_scripts}) reached.",
            status_code=429,
        )
    return repos.scripts.create_script(user_id, data), True


@app.post("/api/scripts", status_code=201)
async def create_saved_script_endpoint(
    payload: SaveScriptPayload,
    response: Response,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
) -> Any:
    """Save a generated or user-written script after Stage 4 moderation (Brief §5.7, §5.8).

    201 with the new script; 200 with the existing one when the same text is already saved.
    """
    clean_title = sanitize_text(payload.title).strip() or "Untitled Script"
    clean_body = sanitize_text(payload.body).strip()
    body_error = _validate_script(clean_body)
    if body_error is not None:
        return body_error
    get_script_pipeline().moderator.assert_safe(
        f"{clean_title}\n{clean_body}", user_id=str(user.id)
    )
    data = NewScript(
        title=clean_title,
        body=clean_body,
        word_count=len(clean_body.split()),
        source=payload.source,
        content_hash=build_content_hash(clean_body),
        topic=payload.topic,
        category=payload.category,
        duration_min=payload.duration_min,
        citations=payload.citations,
        template_id=payload.template_id,
        models_used=payload.models_used,
    )
    try:
        row, created = await run_in_threadpool(_save_script_row, repos, user.id, data)
    except StorageError:
        logger.exception("Could not save script")
        return _script_storage_unavailable()
    if not created:
        response.status_code = 200
    return _script_payload(row)


@app.get("/api/scripts")
async def list_saved_scripts_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
    cursor: str | None = None,
) -> Any:
    """Newest-first page of the user's saved scripts (summaries, no body)."""
    try:
        page, next_cursor = await _fetch_page(repos.scripts.list_scripts, user.id, limit, cursor)
    except StorageError:
        logger.exception("Could not list scripts")
        return _script_storage_unavailable()
    except ValueError:
        return _script_error(400, "invalid_cursor", "The page cursor is not valid.")
    return {"items": [row.model_dump(mode="json") for row in page], "next_cursor": next_cursor}


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
