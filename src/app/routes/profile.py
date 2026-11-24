"""Profile endpoints: read and edit the caller's `profiles` row (Profile page, modals)."""

import logging
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from src.app.auth import AuthProvider, get_auth
from src.app.config import avatar_max_bytes, avatar_max_side_px, avatar_size_px, settings
from src.app.db.factory import Repos, get_repos
from src.app.db.models import (
    ProfilePatch,
    ProfileRow,
    StorageError,
    UserPreferences,
    build_avatar_path,
)
from src.app.deps import CurrentUser, get_current_user
from src.app.routes.auth import sync_display_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ProfileUpdatePayload(BaseModel):
    """Only the fields that are sent are changed."""

    target_accent: str | None = Field(default=None, min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=50)
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


class InvalidAvatarError(Exception):
    """The upload is not a PNG/JPEG/WebP picture we can use."""


def _make_avatar(content: bytes) -> bytes:
    """Check the upload by its content (not its file name) and return a square WebP.

    Sync on purpose: Pillow work is CPU heavy, callers run it via run_in_threadpool.
    """
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:  # verify() leaves the image unusable
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise InvalidAvatarError
            # Checked from the header, before any pixel is decoded (a tiny PNG can be huge).
            if max(image.size) > avatar_max_side_px:
                raise InvalidAvatarError
            upright = ImageOps.exif_transpose(image)  # phone photos store rotation in EXIF
            square = ImageOps.fit(
                upright.convert("RGB"),
                (avatar_size_px, avatar_size_px),
                method=Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            square.save(output, format="WEBP", quality=88)
            return output.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as err:
        raise InvalidAvatarError from err


def _avatar_url(row: ProfileRow, user: CurrentUser, repos: Repos) -> str | None:
    """Signed URL of the avatar, or None (no avatar, or Storage failed). Sync: network call."""
    if row.avatar_path is None:
        return None
    try:
        return repos.files.create_signed_url(
            user.id, settings.avatars_bucket, row.avatar_path, settings.signed_url_ttl_s
        )
    except (StorageError, ValueError):
        logger.warning("Could not sign avatar URL; showing initials instead")
        return None


async def _to_payload(row: ProfileRow, user: CurrentUser, repos: Repos) -> dict:
    avatar_url = await run_in_threadpool(_avatar_url, row, user, repos)
    return {**row.model_dump(mode="json"), "email": user.email, "avatar_url": avatar_url}


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
    return await _to_payload(row, user, repos)


@router.put("/profile/avatar")
async def upload_avatar(
    file: Annotated[UploadFile, File()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Store the caller's picture as `{user_id}/avatar.webp` (one file per user, upsert)."""
    content = await file.read(avatar_max_bytes + 1)
    if len(content) > avatar_max_bytes:
        mb = avatar_max_bytes / (1024 * 1024)
        return _error(413, "avatar_too_large", f"The profile picture must be at most {mb:g} MB.")
    try:
        webp = await run_in_threadpool(_make_avatar, content)
    except InvalidAvatarError:
        return _error(
            422,
            "avatar_invalid",
            "Use a PNG, JPEG or WebP picture of at most "
            f"{avatar_max_side_px} x {avatar_max_side_px} pixels.",
        )

    try:
        row = await run_in_threadpool(repos.profiles.get_profile, user.id)
    except StorageError:
        logger.exception("Could not load profile for avatar upload")
        return _unavailable()
    if row is None:
        return _not_found()  # checked before upload, so no file is left without a profile

    path = build_avatar_path(user.id)
    try:
        await run_in_threadpool(
            repos.files.upload_file,
            user.id,
            settings.avatars_bucket,
            path,
            webp,
            "image/webp",
            True,
        )
    except StorageError:
        logger.exception("Could not upload avatar")
        return _unavailable()
    try:
        row = await run_in_threadpool(repos.profiles.set_avatar_path, user.id, path)
    except StorageError:
        logger.exception("Could not save avatar path")
        row = None
    if row is None:
        # Do not leave a file that no profile points to.
        try:
            await run_in_threadpool(
                repos.files.delete_files, user.id, settings.avatars_bucket, [path]
            )
        except StorageError:
            logger.warning("Could not remove avatar file after a failed profile update")
        return _unavailable()
    # The picture is saved at this point. If signing fails, avatar_url is null and the next
    # GET /api/profile signs it again; a 503 here would wrongly tell the user it was not saved.
    avatar_url = await run_in_threadpool(_avatar_url, row, user, repos)
    return {"avatar_url": avatar_url}


@router.delete("/profile/avatar")
async def delete_avatar(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Remove the caller's picture. The fixed path is deleted even if avatar_path is null."""
    try:
        await run_in_threadpool(
            repos.files.delete_files,
            user.id,
            settings.avatars_bucket,
            [build_avatar_path(user.id)],  # missing files are ignored
        )
        row = await run_in_threadpool(repos.profiles.set_avatar_path, user.id, None)
    except StorageError:
        logger.exception("Could not delete avatar")
        return _unavailable()
    if row is None:
        return _not_found()
    return {"avatar_url": None}


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdatePayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
    auth: Annotated[AuthProvider, Depends(get_auth)],
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
    if sent.get("display_name") and row.display_name:
        await run_in_threadpool(sync_display_name, auth, user.id, row.display_name)
    return await _to_payload(row, user, repos)
