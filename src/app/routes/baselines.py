"""Baseline endpoints: analyse a voice sample, keep it as the user's current baseline."""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from src.app.config import settings
from src.app.db.factory import Repos, get_repos
from src.app.db.models import BaselineRow, NewBaseline, StorageError, build_object_path
from src.app.db.session_helpers import AudioEncodingError, encode_opus
from src.app.deps import CurrentUser, get_current_user
from src.audio_processing.contracts import BaselineProfile, InsufficientAudio, VadParams
from src.audio_processing.pipeline import analyze_baseline
from src.audio_processing.result_schema import BaselineResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def to_baseline_profile(row: BaselineRow) -> BaselineProfile:
    """Convert a stored baseline row into the profile the Evaluate Pipeline expects."""
    return BaselineProfile(
        median_pause_s=row.median_pause_s,
        hesitation_threshold_s=row.hesitation_threshold_s,
        median_f0_hz=row.median_f0_hz,
        mean_loudness_db=row.mean_loudness_db,
        flags=list(row.flags),
    )


def _save_baseline(
    repos: Repos, user: CurrentUser, profile: dict, source_path: Path, work_dir: Path
) -> None:
    """Upload the Opus audio, then make the new baseline current and drop the old audio."""
    baseline_id = uuid4()
    object_path = build_object_path(user.id, baseline_id, ".webm")
    opus_path = work_dir / "baseline.webm"
    encode_opus(source_path, opus_path)
    repos.files.upload_file(
        user.id, settings.baselines_bucket, object_path, opus_path.read_bytes(), "audio/webm"
    )
    try:
        _, previous = repos.baselines.replace_current_baseline(
            user.id, NewBaseline(id=baseline_id, audio_path=object_path, **profile)
        )
    except StorageError:
        repos.files.delete_files(user.id, settings.baselines_bucket, [object_path])
        raise
    if previous is not None and previous.audio_path:
        try:
            repos.files.delete_files(user.id, settings.baselines_bucket, [previous.audio_path])
        except StorageError:
            logger.warning("Could not delete old baseline audio for baseline %s", previous.id)


@router.post("/baseline")
async def create_baseline(
    audio: Annotated[UploadFile, File()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Analyse a baseline recording; when the status is ok, store it as the current baseline."""
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        audio_path = work_dir / (audio.filename or "baseline.wav")
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        try:
            # D12: one JSON shape {schema_version, status, reason, profile, flags}
            payload = analyze_baseline(audio_path=audio_path, vad_params=VadParams())
        except InsufficientAudio:
            payload = {
                "schema_version": "2.0", "status": "insufficient_audio",
                "reason": "low_voiced_ratio", "profile": None, "flags": [],
            }
        response = BaselineResponse(**payload)

        if response.status == "ok" and response.profile is not None:
            try:
                await run_in_threadpool(
                    _save_baseline, repos, user, response.profile, audio_path, work_dir
                )
            except (StorageError, AudioEncodingError):
                logger.exception("Could not save baseline")
                return JSONResponse(
                    status_code=503,
                    content={
                        "error_code": "baseline_not_saved",
                        "message": "Baseline was analysed but could not be saved",
                    },
                )
    return response.model_dump(mode="json")


@router.get("/baseline")
async def get_baseline(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Return the caller's current baseline, or null when there is none."""
    row = await run_in_threadpool(repos.baselines.get_current_baseline, user.id)
    if row is None:
        return None
    return row.model_dump(mode="json", exclude={"user_id"})
