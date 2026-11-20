"""Profile endpoints: read and edit the caller's `profiles` row (Profile page, modals)."""

import logging
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from src.app.config import avatar_max_bytes, avatar_size_px, settings
from src.app.db.factory import Repos, get_repos
from src.app.db.models import (
    ProfilePatch,
    ProfileRow,
    StorageError,
    UserPreferences,
    build_avatar_path,
)
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
    preferences: UserPreferences | None = None


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error_code": error_code, "message": message}
    )


def _unavailable() -> JSONResponse:
    return _error(503, "profile_unavailable", "Could not reach the profile right now.")


def _not_found() -> JSONResponse:
    return _error(404, "profile_not_found", "This account has no profile.")


def _to_payload(row: ProfileRow, user: CurrentUser, repos: Repos | None = None) -> dict:
    payload = {**row.model_dump(mode="json"), "email": user.email}
    payload["avatar_url"] = None
    if row.avatar_path is not None and repos is not None:
        try:
            payload["avatar_url"] = repos.files.create_signed_url(
                user.id,
                settings.avatars_bucket,
                row.avatar_path,
                settings.signed_url_ttl_s,
            )
        except (StorageError, ValueError):
            payload["avatar_url"] = None
    return payload


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
    return _to_payload(row, user, repos)


@router.put("/profile/avatar")
async def upload_avatar(
    file: Annotated[UploadFile, File()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    content = await file.read(avatar_max_bytes + 1)
    if len(content) > avatar_max_bytes:
        return _error(413, "avatar_too_large", "The profile picture is too large.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                return _error(422, "avatar_invalid", "The profile picture format is not supported.")
            resized = ImageOps.fit(
                image.convert("RGB"),
                (avatar_size_px, avatar_size_px),
                method=Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            resized.save(output, format="WEBP", quality=88)
    except (UnidentifiedImageError, OSError, ValueError):
        return _error(422, "avatar_invalid", "The uploaded file is not a valid image.")

    path = build_avatar_path(user.id)
    try:
        await run_in_threadpool(
            repos.files.upload_file,
            user.id,
            settings.avatars_bucket,
            path,
            output.getvalue(),
            "image/webp",
            True,
        )
        row = await run_in_threadpool(repos.profiles.set_avatar_path, user.id, path)
    except StorageError:
        logger.exception("Could not upload avatar")
        return _unavailable()
    if row is None:
        return _not_found()
    try:
        avatar_url = await run_in_threadpool(
            repos.files.create_signed_url,
            user.id,
            settings.avatars_bucket,
            path,
            settings.signed_url_ttl_s,
        )
    except (StorageError, ValueError):
        logger.exception("Could not sign uploaded avatar")
        return _unavailable()
    return {"avatar_url": avatar_url}


@router.delete("/profile/avatar")
async def delete_avatar(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    try:
        row = await run_in_threadpool(repos.profiles.get_profile, user.id)
    except StorageError:
        logger.exception("Could not load profile for avatar deletion")
        return _unavailable()
    if row is None:
        return _not_found()
    if row.avatar_path is not None:
        try:
            await run_in_threadpool(
                repos.files.delete_files,
                user.id,
                settings.avatars_bucket,
                [row.avatar_path],
            )
        except (StorageError, ValueError):
            logger.exception("Could not delete avatar file")
            return _unavailable()
    try:
        row = await run_in_threadpool(repos.profiles.set_avatar_path, user.id, None)
    except StorageError:
        logger.exception("Could not clear avatar path")
        return _unavailable()
    if row is None:
        return _not_found()
    return {"avatar_url": None}


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
    sent.pop("preferences", None)
    # Only the keys the client sent; the model already checked them (UserPreferences).
    prefs = payload.preferences.model_dump(exclude_unset=True) if payload.preferences else None
    try:
        row = await run_in_threadpool(repos.profiles.update_profile, user.id, ProfilePatch(**sent))
        if row is not None and consent is not None and consent != row.consent_recording:
            row = await run_in_threadpool(repos.profiles.set_consent, user.id, consent)
        if row is not None and prefs:
            row = await run_in_threadpool(repos.profiles.merge_preferences, user.id, prefs)
    except StorageError:
        logger.exception("Could not update profile")
        return _unavailable()
    if row is None:
        return _not_found()
    return _to_payload(row, user, repos)
