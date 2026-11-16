"""Profile endpoints: read and edit the caller's `profiles` row (Profile page, modals)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.app.db.factory import Repos, get_repos
from src.app.db.models import ProfilePatch, ProfileRow, StorageError
from src.app.deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ProfileUpdatePayload(BaseModel):
    """Only the fields that are sent are changed."""

    target_accent: str | None = Field(default=None, min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=50)
    topics: list[str] | None = Field(default=None, max_length=20)
    consent_recording: bool | None = None


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error_code": error_code, "message": message}
    )


def _unavailable() -> JSONResponse:
    return _error(503, "profile_unavailable", "Could not reach the profile right now.")


def _not_found() -> JSONResponse:
    return _error(404, "profile_not_found", "This account has no profile.")


def _to_payload(row: ProfileRow, user: CurrentUser) -> dict:
    return {**row.model_dump(mode="json"), "email": user.email}


@router.get("/profile")
async def get_profile(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    try:
        row = await run_in_threadpool(repos.profiles.get_profile, user.id)
    except StorageError:
        logger.exception("Could not load profile")
        return _unavailable()
    if row is None:
        return _not_found()
    return _to_payload(row, user)


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdatePayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    sent = payload.model_dump(exclude_unset=True)
    if "target_accent" in sent and sent["target_accent"] is None:
        return _error(422, "invalid_profile", "The target accent cannot be empty.")
    consent = sent.pop("consent_recording", None)
    try:
        row = await run_in_threadpool(repos.profiles.update_profile, user.id, ProfilePatch(**sent))
        if row is not None and consent is not None and consent != row.consent_recording:
            row = await run_in_threadpool(repos.profiles.set_consent, user.id, consent)
    except StorageError:
        logger.exception("Could not update profile")
        return _unavailable()
    if row is None:
        return _not_found()
    return _to_payload(row, user)
