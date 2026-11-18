"""Transient word and sentence retry endpoint."""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from src.app.config import (
    allowed_formats,
    decode_timeout_s,
    duration_cap_margin_s,
    max_upload_bytes,
    settings,
)
from src.app.constants import CONSTANTS
from src.app.deps import CurrentUser, get_current_user
from src.app.rate_limit import SlidingWindowLimiter
from src.app.uploads import safe_upload_path, save_upload_limited
from src.audio_processing.alignment import align
from src.audio_processing.contracts import InsufficientAudio
from src.audio_processing.decode import decode_to_master
from src.audio_processing.probe import probe
from src.audio_processing.stt import transcribe
from src.audio_processing.text_norm import is_filler

router = APIRouter(prefix="/api/practice")
_retry = CONSTANTS["retry"]
limiter = SlidingWindowLimiter(_retry["attempts_per_window"], _retry["window_s"])


def _process(path, workdir, max_seconds, target_text):
    probe(
        path,
        max_seconds=max_seconds,
        max_bytes=max_upload_bytes,
        allowed_formats=frozenset(allowed_formats),
    )
    master = decode_to_master(
        path,
        workdir=workdir,
        max_seconds=max_seconds,
        cap_margin_s=duration_cap_margin_s,
        timeout_s=decode_timeout_s,
    )
    try:
        stt = transcribe(master, settings=settings)
    except InsufficientAudio:
        return "", [], "not_heard"
    if not stt.transcript.strip() or not any(not is_filler(w.word) for w in stt.words):
        return stt.transcript, [], "not_heard"
    items = [item for item in align(target_text, stt.words).items if item.ref_index is not None]
    if not items:
        return stt.transcript, [], None
    statuses = {item.status for item in items}
    verdict = (
        "not_yet" if statuses & {"sub", "del"}
        else "close" if "near_miss" in statuses
        else "correct"
    )
    return stt.transcript, items, verdict


@router.post("/retry")
async def retry(
    audio: Annotated[UploadFile, File()],
    target_text: Annotated[str, Form()],
    kind: Annotated[str, Form()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    if kind not in {"word", "sentence"}:
        return JSONResponse(status_code=422, content={"error_code": "invalid_kind"})
    target_text = target_text.strip()
    if len(target_text) > _retry["max_target_chars"] or not any(c.isalnum() for c in target_text):
        return JSONResponse(status_code=422, content={"error_code": "target_invalid"})
    if not limiter.hit(str(user.id)):
        return JSONResponse(
            status_code=429,
            content={"error_code": "rate_limited", "message": "Please try again later."},
        )
    max_seconds = _retry[f"{kind}_max_seconds"] + _retry["server_grace_s"]
    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        path = safe_upload_path(workdir, audio.filename)
        await run_in_threadpool(save_upload_limited, audio, path, max_bytes=max_upload_bytes)
        heard, items, verdict = await run_in_threadpool(
            _process, path, workdir, max_seconds, target_text
        )
        if verdict is None:
            return JSONResponse(status_code=422, content={"error_code": "target_invalid"})
        return {
            "kind": kind,
            "target_text": target_text,
            "heard_text": heard,
            "verdict": verdict,
            "words": [
                {
                    "ref_word": x.ref_word,
                    "hyp_word": x.hyp_word,
                    "status": x.status,
                    "homophone": x.homophone,
                }
                for x in items
            ],
        }
