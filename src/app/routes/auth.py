"""Account endpoints: sign up (with the profiles row), log in, refresh, log out, password.

Errors use `{error_code, message}` like the baseline and script endpoints.
"""

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.app.auth import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AuthProvider,
    AuthProviderError,
    AuthUnavailableError,
    EmailTakenError,
    InvalidCredentialsError,
    WeakPasswordError,
    get_auth,
)
from src.app.db.factory import Repos, get_repos
from src.app.db.models import ProfileUpsert, StorageError
from src.app.deps import CurrentUser, get_bearer_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

# Light check only (one "@", a dot in the domain, no spaces); Supabase Auth checks again.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 254


class SignupPayload(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    target_accent: str = Field(min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=50)
    topics: list[str] = Field(default_factory=list, max_length=20)
    consent_recording: bool = False


class LoginPayload(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class RefreshPayload(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class PasswordPayload(BaseModel):
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error_code": error_code, "message": message}
    )


def _auth_unavailable() -> JSONResponse:
    return _error(503, "auth_unavailable",
                  "The account service is not available right now. Please try again.")


def _weak_password() -> JSONResponse:
    return _error(422, "weak_password",
                  f"Use a password with at least {MIN_PASSWORD_LENGTH} characters.")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _rollback_account(auth: AuthProvider, repos: Repos, user_id) -> None:
    """Undo a half-finished sign up so the email can be used again."""
    try:
        repos.profiles.delete_profile(user_id)  # Supabase also cascades from auth.users
    except StorageError:
        logger.warning("Could not delete the profile of a failed sign up")
    try:
        auth.delete_user(user_id)
    except AuthProviderError:
        logger.exception("Could not delete the account of a failed sign up")


@router.post("/signup", status_code=201)
async def sign_up(
    payload: SignupPayload,
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Create the account, then its `profiles` row (every saved row needs it).

    If the profile cannot be saved, the account is deleted again and 503 is returned,
    so the person can simply try again with the same email.
    """
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        return _error(422, "invalid_email", "Enter a valid email address.")
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        return _weak_password()
    try:
        user_id = await run_in_threadpool(auth.create_user, email, payload.password)
    except EmailTakenError:
        return _error(409, "email_taken", "An account with this email already exists.")
    except WeakPasswordError:
        return _weak_password()
    except AuthUnavailableError:
        logger.exception("Sign up failed at the account service")
        return _auth_unavailable()

    profile = ProfileUpsert(
        target_accent=payload.target_accent.strip(),
        display_name=(payload.display_name or "").strip() or email.split("@")[0][:50],
        age=payload.age,
        gender=payload.gender,
        topics=payload.topics,
    )
    try:
        await run_in_threadpool(repos.profiles.upsert_profile, user_id, profile)
        if payload.consent_recording:
            await run_in_threadpool(repos.profiles.set_consent, user_id, True)
    except StorageError:
        logger.exception("Could not save the profile of a new account")
        await run_in_threadpool(_rollback_account, auth, repos, user_id)
        return _error(503, "profile_not_saved",
                      "The account could not be created. Please try again.")
    return {"user_id": str(user_id)}


@router.post("/login")
async def log_in(payload: LoginPayload, auth: Annotated[AuthProvider, Depends(get_auth)]):
    """Return `{access_token, refresh_token, expires_in, user_id}`; 401 for a wrong login."""
    try:
        session = await run_in_threadpool(
            auth.sign_in, _normalize_email(payload.email), payload.password
        )
    except InvalidCredentialsError:
        return _error(401, "invalid_credentials", "Wrong email or password.")
    except AuthUnavailableError:
        logger.exception("Log in failed at the account service")
        return _auth_unavailable()
    return session.model_dump(mode="json")


@router.post("/refresh")
async def refresh(payload: RefreshPayload, auth: Annotated[AuthProvider, Depends(get_auth)]):
    """Swap a refresh token for a new session (a refresh token works once)."""
    try:
        session = await run_in_threadpool(auth.refresh, payload.refresh_token)
    except InvalidCredentialsError:
        return _error(401, "invalid_refresh_token", "Your session has ended. Please log in.")
    except AuthUnavailableError:
        logger.exception("Refresh failed at the account service")
        return _auth_unavailable()
    return session.model_dump(mode="json")


@router.post("/logout")
async def log_out(
    _: Annotated[CurrentUser, Depends(get_current_user)],
    token: Annotated[str, Depends(get_bearer_token)],
    auth: Annotated[AuthProvider, Depends(get_auth)],
):
    """Revoke the current session (best effort); the browser drops its tokens anyway."""
    await run_in_threadpool(auth.sign_out, token)
    return {"logged_out": True}


@router.put("/password")
async def change_password(
    payload: PasswordPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    auth: Annotated[AuthProvider, Depends(get_auth)],
):
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        return _weak_password()
    try:
        await run_in_threadpool(auth.update_password, user.id, payload.password)
    except WeakPasswordError:
        return _weak_password()
    except AuthProviderError:
        logger.exception("Could not change the password")
        return _auth_unavailable()
    return {"updated": True}
