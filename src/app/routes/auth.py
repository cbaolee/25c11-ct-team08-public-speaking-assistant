"""Account endpoints: sign up (with the profiles row), log in, refresh, log out, password.

Errors use `{error_code, message}` like the baseline and script endpoints.
"""

import hashlib
import logging
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.app.auth import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AuthProvider,
    AuthProviderError,
    AuthRateLimitedError,
    AuthUnavailableError,
    EmailNotConfirmedError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidEmailError,
    OtpExpiredError,
    OtpInvalidError,
    WeakPasswordError,
    get_auth,
)
from src.app.config import settings
from src.app.constants import CONSTANTS
from src.app.db.factory import Repos, get_repos
from src.app.db.models import ProfileUpsert, StorageError
from src.app.deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")

# Light check only (one "@", a dot in the domain, no spaces); Supabase Auth checks again.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 254
_auth_config = CONSTANTS["auth"]
# Attempt limits per email (or per user for re-auth), counted in public.auth_rate_limits
# (migration 0011) so they survive restarts and are shared by every worker.
# bucket -> (max hits, fixed window in seconds)
_RATE_LIMITS = {
    "signup_resend": (1, _auth_config["resend_cooldown_s"]),
    "signup_verify": (_auth_config["verify_attempts_per_window"], _auth_config["verify_window_s"]),
    # Re-auth (change password, delete account): own budget, same size as the code check (ADR-011)
    "reauth": (_auth_config["verify_attempts_per_window"], _auth_config["verify_window_s"]),
    "reset_send": (1, _auth_config["resend_cooldown_s"]),
    "reset_verify": (_auth_config["verify_attempts_per_window"], _auth_config["verify_window_s"]),
}


def _hit_rate_limit(repos: Repos, bucket: str, key: str) -> bool:
    """Count one attempt; False when the bucket is full for this key.

    Fails open: when the counter cannot be reached the attempt is allowed and a warning is
    logged. Supabase Auth keeps its own limits on emails and code checks, so a short database
    outage must not lock everyone out of logging in or resetting a password.
    """
    max_hits, window_s = _RATE_LIMITS[bucket]
    try:
        return repos.rate_limits.hit(bucket, key, max_hits, window_s)
    except StorageError:
        logger.warning("Rate limit counter unavailable for %s; allowing the attempt", bucket)
        return True


async def _allowed(repos: Repos, bucket: str, key: str) -> bool:
    return await run_in_threadpool(_hit_rate_limit, repos, bucket, key)


def _email_key(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()


class SignupPayload(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    target_accent: str = Field(min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=50)
    consent_recording: bool = False


class LoginPayload(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class OtpEmailPayload(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)


class SignupDetails(BaseModel):
    """The profile part of the sign-up form, sent again with the code (see verify_otp)."""

    target_accent: str = Field(min_length=1, max_length=50)
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, max_length=50)
    consent_recording: bool = False


class VerifyOtpPayload(OtpEmailPayload):
    token: str = Field(max_length=32)
    # Latest sign-up form (ADR-010 D3, amended 21/11): applied only after the code is accepted.
    password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)
    profile: SignupDetails | None = None


class ResetPasswordPayload(OtpEmailPayload):
    token: str = Field(max_length=32)
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class PasswordChangePayload(BaseModel):
    current_password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class DeleteAccountPayload(BaseModel):
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


# Refresh token: only in an HttpOnly cookie that JavaScript cannot read, sent only to
# /api/auth/* and never by another site (SameSite=Strict). The access token is returned in the
# body and lives only in the page's memory.
REFRESH_COOKIE = "psa_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
MAX_REFRESH_TOKEN_LENGTH = 4096


def _set_refresh_cookie(response: JSONResponse, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=_auth_config["refresh_cookie_days"] * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: JSONResponse) -> JSONResponse:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response


def _session_response(session) -> JSONResponse:
    """Body `{access_token, expires_in, user_id}`; the refresh token goes in the cookie only."""
    response = JSONResponse({
        "access_token": session.access_token,
        "expires_in": session.expires_in,
        "user_id": str(session.user_id),
    })
    _set_refresh_cookie(response, session.refresh_token)
    return response


def _is_foreign_origin(request: Request) -> bool:
    """True when the browser says the request comes from another site.

    SameSite=Strict already keeps the cookie off cross-site requests; this second check
    covers old browsers. A request without `Origin` (not a browser, or a same-origin GET)
    passes: it cannot carry the cookie from another site anyway.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return False
    host = request.headers.get("host", "")
    return origin.split("://", 1)[-1].rstrip("/") != host


def _foreign_origin() -> JSONResponse:
    return _error(403, "origin_mismatch", "This request must come from the app itself.")


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error_code": error_code, "message": message}
    )


def _auth_unavailable() -> JSONResponse:
    return _error(
        503, "auth_unavailable", "The account service is not available right now. Please try again."
    )


def _weak_password() -> JSONResponse:
    return _error(
        422, "weak_password", f"Use a password with at least {MIN_PASSWORD_LENGTH} characters."
    )


def _consent_required() -> JSONResponse:
    return _error(422, "consent_required", "Recording consent is required to create an account.")


def _display_name(sent: str | None, email: str) -> str:
    """The name the app and the emails use: the one sent, or the part of the email before @."""
    return (sent or "").strip() or email.split("@")[0][:50]


def sync_display_name(auth: AuthProvider, user_id: UUID, display_name: str) -> None:
    """Best effort: copy the name to the account so the emails greet the user with it.

    The profile is the source of truth; a failure only means an older name (or "Hi,") in mail.
    """
    try:
        auth.set_display_name(user_id, display_name)
    except AuthProviderError:
        logger.warning("Could not copy the display name to the account")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _rollback_account(
    auth: AuthProvider, repos: Repos, user_id, *, delete_profile: bool, delete_user: bool
) -> None:
    """Delete only request-owned data: deleting an auth user cascades to all their data."""
    if delete_profile:
        try:
            repos.profiles.delete_profile(user_id)
        except StorageError:
            logger.warning("Could not delete the profile of a failed sign up")
    if delete_user:
        try:
            auth.delete_user(user_id)
        except AuthProviderError:
            logger.warning("Could not delete the account of a failed sign up")


@router.post("/signup", status_code=201)
async def sign_up(
    payload: SignupPayload,
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Create or resume signup without overwriting existing data."""
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        return _error(422, "invalid_email", "Enter a valid email address.")
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        return _weak_password()
    if payload.consent_recording is not True:
        return _consent_required()
    display_name = _display_name(payload.display_name, email)
    try:
        result = await run_in_threadpool(auth.sign_up, email, payload.password, display_name)
    except EmailTakenError:
        return _error(409, "email_taken", "An account with this email already exists.")
    except WeakPasswordError:
        return _weak_password()
    except InvalidEmailError:
        return _error(422, "invalid_email", "Enter a valid email address.")
    except AuthRateLimitedError:
        return _rate_limited()
    except AuthUnavailableError:
        logger.warning("Sign up failed at the account service")
        return _auth_unavailable()

    user_id = UUID(str(result.user_id))
    try:
        existing = await run_in_threadpool(repos.profiles.get_profile, user_id)
    except StorageError:
        logger.warning("Could not read the profile of a sign up")
        return _profile_not_saved()
    if existing is None:
        profile = ProfileUpsert(
            target_accent=payload.target_accent.strip(),
            display_name=display_name,
            age=payload.age,
            gender=payload.gender,
        )
        profile_created_here = False
        try:
            await run_in_threadpool(repos.profiles.upsert_profile, user_id, profile)
            profile_created_here = True
            await run_in_threadpool(repos.profiles.set_consent, user_id, True)
        except StorageError:
            if result.created and result.needs_verification:
                await run_in_threadpool(
                    _rollback_account, auth, repos, user_id, delete_profile=True, delete_user=True
                )
            else:
                if profile_created_here:
                    await run_in_threadpool(
                        _rollback_account, auth, repos, user_id,
                        delete_profile=True, delete_user=False,
                    )
                logger.warning("Profile save failed; preserving existing account and data")
            return _profile_not_saved()
    if result.needs_verification or not result.created:
        await _allowed(repos, "signup_resend", _email_key(email))  # starts the resend cooldown
    return JSONResponse(status_code=201 if result.created else 200, content={
        "user_id": str(user_id),
        "verification_required": result.needs_verification if result.created else True,
    })


def _profile_not_saved() -> JSONResponse:
    return _error(503, "profile_not_saved", "The account could not be created. Please try again.")


def _rate_limited() -> JSONResponse:
    return _error(429, "rate_limited", "Too many attempts. Please try again later.")


def _apply_password(auth: AuthProvider, user_id: UUID, password: str) -> bool:
    try:
        auth.update_password(user_id, password)
    except (AuthProviderError, ValueError):
        logger.warning("Verified account: the new password could not be saved")
        return False
    return True


def _apply_profile(
    auth: AuthProvider, repos: Repos, user_id: UUID, details: SignupDetails, email: str
) -> bool:
    profile = ProfileUpsert(
        target_accent=details.target_accent.strip(),
        display_name=_display_name(details.display_name, email),
        age=details.age,
        gender=details.gender,
    )
    try:
        repos.profiles.upsert_profile(user_id, profile)
        repos.profiles.set_consent(user_id, True)
    except StorageError:
        logger.warning("Verified account: the latest sign-up profile could not be saved")
        return False
    sync_display_name(auth, user_id, profile.display_name)
    return True


@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOtpPayload,
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Confirm the email, then apply the latest sign-up form (password, profile) if it came with it.

    Signing up again with an email that is still unconfirmed keeps the first password and profile
    (GoTrue only sends a new code). Whoever enters the code owns the inbox, so the form they sent
    last is saved here, after the code is accepted. A confirmed account cannot reach this point:
    verifying it again is `otp_invalid`.
    """
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        return _error(422, "invalid_email", "Enter a valid email address.")
    token = payload.token.strip()
    if not re.fullmatch(rf"[0-9]{{{_auth_config['otp_length']}}}", token):
        return _error(422, "otp_invalid", "Enter a valid verification code.")
    if payload.password is not None and len(payload.password) < MIN_PASSWORD_LENGTH:
        return _weak_password()  # checked first, so a bad password never uses up the code
    if payload.profile is not None and payload.profile.consent_recording is not True:
        return _consent_required()
    if not await _allowed(repos, "signup_verify", _email_key(email)):
        return _rate_limited()
    try:
        user_id = await run_in_threadpool(auth.verify_signup_otp, email, token)
    except OtpInvalidError:
        return _error(422, "otp_invalid", "The verification code is invalid.")
    except OtpExpiredError:
        return _error(422, "otp_expired", "The verification code has expired.")
    except AuthRateLimitedError:
        return _rate_limited()
    except AuthUnavailableError:
        return _auth_unavailable()
    password_updated = profile_updated = None
    if payload.password is not None:
        password_updated = user_id is not None and await run_in_threadpool(
            _apply_password, auth, user_id, payload.password
        )
    if payload.profile is not None:
        profile_updated = user_id is not None and await run_in_threadpool(
            _apply_profile, auth, repos, user_id, payload.profile, email
        )
    return {
        "verified": True,
        "password_updated": password_updated,
        "profile_updated": profile_updated,
    }


@router.post("/resend-otp")
async def resend_otp(
    payload: OtpEmailPayload,
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        return _error(422, "invalid_email", "Enter a valid email address.")
    if not await _allowed(repos, "signup_resend", _email_key(email)):
        return _rate_limited()
    try:
        await run_in_threadpool(auth.resend_signup_otp, email)
    except AuthRateLimitedError:
        return _rate_limited()
    except AuthUnavailableError:
        return _auth_unavailable()
    return {"sent": True}


@router.post("/forgot-password")
async def forgot_password(
    payload: OtpEmailPayload,
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Email a recovery code. Always `{"sent": true}`, so nobody learns which emails have accounts.

    Used from Log in (Forgot password?) and from Settings > Change password, where the browser
    sends the logged-in account's email.
    """
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        return _error(422, "invalid_email", "Enter a valid email address.")
    if not await _allowed(repos, "reset_send", _email_key(email)):
        return _rate_limited()
    try:
        await run_in_threadpool(auth.send_password_reset, email)
    except AuthRateLimitedError:
        return _rate_limited()
    except AuthUnavailableError:
        return _auth_unavailable()
    return {"sent": True}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordPayload,
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Set a new password with the recovery code; every session of the account ends.

    The password length is checked first, so a weak password never uses up a try.
    """
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        return _error(422, "invalid_email", "Enter a valid email address.")
    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        return _weak_password()
    token = payload.token.strip()
    if not re.fullmatch(rf"[0-9]{{{_auth_config['otp_length']}}}", token):
        return _error(422, "otp_invalid", "Enter a valid verification code.")
    if not await _allowed(repos, "reset_verify", _email_key(email)):
        return _rate_limited()
    try:
        await run_in_threadpool(auth.reset_password_with_otp, email, token, payload.new_password)
    except OtpInvalidError:
        return _error(422, "otp_invalid", "The verification code is invalid.")
    except OtpExpiredError:
        return _error(422, "otp_expired", "The verification code has expired.")
    except WeakPasswordError:
        return _weak_password()
    except AuthRateLimitedError:
        return _rate_limited()
    except AuthUnavailableError:
        return _auth_unavailable()
    # Every session ended, this browser's too: drop its refresh cookie
    return _clear_refresh_cookie(JSONResponse({"reset": True}))


@router.post("/login")
async def log_in(payload: LoginPayload, auth: Annotated[AuthProvider, Depends(get_auth)]):
    """Return `{access_token, expires_in, user_id}` and set the refresh cookie; 401: wrong login."""
    try:
        session = await run_in_threadpool(
            auth.sign_in, _normalize_email(payload.email), payload.password
        )
    except EmailNotConfirmedError:
        return _error(
            403, "email_not_confirmed",
            "Confirm your email with the code we sent before logging in.",
        )
    except InvalidCredentialsError:
        return _error(401, "invalid_credentials", "Wrong email or password.")
    except AuthUnavailableError:
        logger.exception("Log in failed at the account service")
        return _auth_unavailable()
    return _session_response(session)


@router.post("/refresh")
async def refresh(request: Request, auth: Annotated[AuthProvider, Depends(get_auth)]):
    """Swap the refresh cookie for a new session and a new cookie (a refresh token works once).

    The page calls this on load (F5) and when the access token expires. No body.
    """
    if _is_foreign_origin(request):
        return _foreign_origin()
    refresh_token = request.cookies.get(REFRESH_COOKIE, "")
    ended = _error(401, "invalid_refresh_token", "Your session has ended. Please log in.")
    if not refresh_token or len(refresh_token) > MAX_REFRESH_TOKEN_LENGTH:
        return _clear_refresh_cookie(ended) if refresh_token else ended
    try:
        session = await run_in_threadpool(auth.refresh, refresh_token)
    except InvalidCredentialsError:
        return _clear_refresh_cookie(ended)
    except AuthUnavailableError:
        logger.exception("Refresh failed at the account service")
        return _auth_unavailable()  # the cookie stays: the session may still be valid
    return _session_response(session)


@router.post("/logout")
async def log_out(request: Request, auth: Annotated[AuthProvider, Depends(get_auth)]):
    """Revoke the session (best effort) and always delete the refresh cookie.

    Works without a valid access token, so an expired page can still log out cleanly.
    """
    if _is_foreign_origin(request):
        return _foreign_origin()
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            await run_in_threadpool(auth.sign_out, token)
        except AuthProviderError:
            logger.warning("Log out: could not revoke the session")
    return _clear_refresh_cookie(JSONResponse({"logged_out": True}))


def _user_key(user_id: UUID) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()


async def _check_current_password(
    auth: AuthProvider, repos: Repos, user: CurrentUser, password: str
) -> JSONResponse | None:
    """Re-auth before a sensitive action. None when the password is right, else the error.

    A wrong password is 403, not 401: the browser treats every 401 as "session ended"
    (api.js refreshes the token and logs out), but the session is still valid here.
    """
    if not await _allowed(repos, "reauth", _user_key(user.id)):
        return _rate_limited()
    if not user.email:
        return _auth_unavailable()  # the token carries no email: cannot re-check the password
    try:
        ok = await run_in_threadpool(auth.verify_password, user.email, password)
    except AuthRateLimitedError:
        return _rate_limited()
    except AuthUnavailableError:
        logger.warning("Re-auth failed at the account service")
        return _auth_unavailable()
    if not ok:
        return _error(403, "wrong_password", "The current password is not correct.")
    return None


@router.put("/password")
async def change_password(
    payload: PasswordChangePayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Change the password after re-checking the current one; the session stays logged in."""
    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        return _weak_password()
    if payload.new_password == payload.current_password:
        return _error(422, "same_password", "Choose a password different from the current one.")
    denied = await _check_current_password(auth, repos, user, payload.current_password)
    if denied is not None:
        return denied
    try:
        await run_in_threadpool(auth.update_password, user.id, payload.new_password)
    except WeakPasswordError:
        return _weak_password()
    except AuthProviderError:
        logger.exception("Could not change the password")
        return _auth_unavailable()
    return {"updated": True}


def _user_buckets() -> tuple[str, ...]:
    return (
        settings.audio_bucket,
        settings.series_bucket,
        settings.baselines_bucket,
        settings.avatars_bucket,
    )


@router.delete("/account")
async def delete_account(
    payload: DeleteAccountPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    auth: Annotated[AuthProvider, Depends(get_auth)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    """Delete the account and all its data (ADR-011, ADR-012). Order matters:

    1. re-check the current password (nothing is deleted on 403/429/503);
    2. empty the user's folder in every bucket; Storage objects are not removed by the
       database cascade, so they go first. `repos.files` sends audio and series to the
       user's shard project. If Storage fails, stop: rows still point to files and a retry
       deletes what is left (every step is idempotent);
    3. delete the user's session rows; they may live in a shard project, where the cascade
       from the core project does not reach. If this fails, stop: the account still exists
       and a retry deletes what is left;
    4. delete the auth user, always last; `on delete cascade` removes accounts, profiles,
       baselines, scripts (and sessions in the core project). If this fails after the data
       is gone, the account still works without history and the user can try again.
    5. after the auth deletion, remove schedule events in memory repositories. Supabase uses
       the auth-user cascade; cleanup is best-effort and must not undo a successful deletion.
    Running evaluate jobs are not cancelled: the job store has no per-user cancel (see ADR-011).
    """
    denied = await _check_current_password(auth, repos, user, payload.password)
    if denied is not None:
        return denied
    try:
        for bucket in _user_buckets():
            await run_in_threadpool(repos.files.delete_user_folder, user.id, bucket)
    except (StorageError, RuntimeError):  # RuntimeError: the user's shard is not configured
        logger.warning("Delete account: Storage cleanup failed, nothing else was deleted")
        return _error(
            503, "storage_unavailable",
            "Your files could not be deleted right now. Please try again.",
        )
    try:
        await run_in_threadpool(repos.sessions.delete_user_sessions, user.id)
    except (StorageError, RuntimeError):
        logger.warning("Delete account: files deleted but the session rows could not be deleted")
        return _error(
            503, "storage_unavailable",
            "Your history could not be deleted right now. Please try again.",
        )
    try:
        await run_in_threadpool(auth.delete_user, user.id)
    except AuthProviderError:
        logger.warning("Delete account: files deleted but the account could not be deleted")
        return _auth_unavailable()
    try:
        # Supabase: auth.users deletion cascades through schedule_events. Memory repos need
        # explicit cleanup because auth and repository storage are separate in dev/tests.
        await run_in_threadpool(repos.schedule.delete_user_schedule, user.id)
    except StorageError:
        logger.warning("Delete account: account deleted, schedule cleanup failed")
    try:
        # Supabase: the cascade already removed the rows, so this is a no-op. In-memory
        # accounts and repositories are not linked, so the rows are removed here.
        await run_in_threadpool(repos.profiles.delete_profile, user.id)
    except StorageError:
        logger.warning("Delete account: account deleted, profile cleanup failed")
    return _clear_refresh_cookie(JSONResponse({"deleted": True}))
