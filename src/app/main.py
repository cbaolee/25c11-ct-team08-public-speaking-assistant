import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.app.db.factory import Repos, get_repos
from src.app.db.models import StorageError
from src.app.deps import CurrentUser, get_current_user
from src.app.routes import baselines
from src.audio_processing.contracts import AudioRejected, VadParams
from src.audio_processing.pipeline import evaluate_session

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI()
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


@app.post("/api/evaluate")
async def evaluate_endpoint(
    audio: Annotated[UploadFile, File()],
    script: Annotated[str, Form()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    baseline_profile: Annotated[str, Form()] = "",
):
    """Score a practice recording against the caller's stored baseline.

    `baseline_profile` is still accepted so the old UI keeps working, but it is
    ignored: the server reads the baseline from the database (M6).
    TODO: remove the field once the frontend stops sending it.
    """
    vad_params = VadParams()

    try:
        row = await run_in_threadpool(repos.baselines.get_current_baseline, user.id)
    except StorageError:
        logger.exception("Could not load baseline")
        return JSONResponse(
            status_code=503,
            content={"error_code": "baseline_unavailable",
                     "message": "Could not load the current baseline"},
        )
    baseline = baselines.to_baseline_profile(row) if row is not None else None

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / (audio.filename or "uploaded.wav")
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        result = evaluate_session(
            audio_path=audio_path,
            script=script,
            baseline=baseline,
            vad_params=vad_params
        )

        return result.model_dump(mode="json")
