import json
import logging
import shutil
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from src.app.config import settings
from src.app.db.factory import Repos, get_repos
from src.app.db.models import NewSession, StorageError, build_object_path
from src.app.db.session_helpers import encode_opus, split_series
from src.app.deps import CurrentUser, get_current_user
from src.app.routes import baselines
from src.audio_processing.contracts import (
    AudioRejected, 
    VadParams 
)
from src.audio_processing.pipeline import evaluate_session

WEB_DIR = Path(__file__).resolve().parents[1] / "web" 

app = FastAPI()
logger = logging.getLogger(__name__)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")
app.include_router(baselines.router)


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
        return str(session_id)
    except Exception:
        for bucket, path in uploaded_paths:
            try:
                repos.files.delete_files(user_id, bucket, [path])
            except Exception:
                logger.exception("Failed to clean up uploaded session object in %s bucket", bucket)
        raise


@app.post("/api/evaluate")
async def evaluate_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    audio: UploadFile = File(...),
    script: str = Form(...),
    baseline_profile: str = Form(""),
):
    """
    Endpoint xử lý chấm điểm phiên luyện tập thuyết trình.

    Baseline lấy từ DB theo user; `baseline_profile` của client được nhận nhưng bỏ qua
    (UI cũ vẫn gửi). Khi settings.baseline_required bật, chưa có baseline thì trả 409.
    """
    # Khởi tạo trực tiếp cấu hình VAD mặc định
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
        audio_path = Path(temp_dir) / (audio.filename or "uploaded.wav")
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        result = evaluate_session(
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
