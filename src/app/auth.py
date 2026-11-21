"""Accounts: sign up, log in, refresh and check access tokens.

Supabase Auth keeps the accounts (`auth.users`); `profiles.id` is the same UUID.
The browser never talks to Supabase directly: it sends email + password to our API,
gets an access token back, then sends `Authorization: Bearer <token>` on every request.
Without SUPABASE_URL (APP_ENV=dev only) an in-memory provider keeps accounts in RAM,
like the in-memory repositories: everything is lost when the server stops.

All functions are sync; async endpoints call them via run_in_threadpool.
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel
from supabase_auth import SyncGoTrueClient
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError, AuthWeakPasswordError

from src.app.config import settings
from src.app.constants import CONSTANTS

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # Supabase stores bcrypt hashes, bcrypt only reads 72 bytes
MEMORY_TOKEN_TTL_S = 3600  # same default lifetime as a Supabase access token
_PBKDF2_ROUNDS = 100_000


class AuthProviderError(Exception):
    """Base class: an account operation failed."""


class InvalidCredentialsError(AuthProviderError):
    """Wrong email/password, or an unknown/expired refresh token."""


class EmailTakenError(AuthProviderError):
    """An account with this email already exists."""


class WeakPasswordError(AuthProviderError):
    """The account service refused the password."""


class AuthUnavailableError(AuthProviderError):
    """The account service could not be reached or answered with an unexpected error."""


class EmailNotConfirmedError(AuthProviderError):
    """The account has not confirmed its email."""


class OtpInvalidError(AuthProviderError):
    """The verification code is invalid."""


class OtpExpiredError(AuthProviderError):
    """The verification code has expired."""


class AuthRateLimitedError(AuthProviderError):
    """The account service rate limit was reached."""


@dataclass(frozen=True)
class SignUpResult:
    user_id: str
    needs_verification: bool
    created: bool


class AuthSession(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # seconds until access_token expires
    user_id: UUID


@dataclass(frozen=True)
class TokenUser:
    id: UUID
    email: str | None


class AuthProvider(Protocol):
    def sign_up(self, email: str, password: str) -> SignUpResult: ...

    def verify_signup_otp(self, email: str, token: str) -> None: ...

    def resend_signup_otp(self, email: str) -> None: ...

    def create_user(self, email: str, password: str) -> UUID: ...

    def delete_user(self, user_id: UUID) -> None: ...

    def sign_in(self, email: str, password: str) -> AuthSession: ...

    def refresh(self, refresh_token: str) -> AuthSession: ...

    def verify_token(self, access_token: str) -> TokenUser | None: ...  # None: invalid or expired

    def sign_out(self, access_token: str) -> None: ...

    def update_password(self, user_id: UUID, password: str) -> None: ...


# ---------- in-memory provider (dev without Supabase, tests) ----------


@dataclass
class _MemoryAccount:
    id: UUID
    email: str
    salt: bytes
    password_hash: bytes
    confirmed: bool = True
    otp_hash: str | None = None
    otp_expires_at: float = 0
    otp_attempts: int = 0


def _mask_email(email: str) -> str:
    """Hide the local part of an email address."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


class MemoryAuthProvider:
    def __init__(
        self,
        token_ttl_s: int = MEMORY_TOKEN_TTL_S,
        *,
        require_email_otp: bool | None = None,
        otp_length: int | None = None,
        otp_ttl_s: int | None = None,
        max_attempts: int | None = None,
        code_factory: Callable[[], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        log_codes: bool = False,
    ) -> None:
        config = CONSTANTS["auth"]
        self._require_email_otp = (
            config["require_email_otp"] if require_email_otp is None else require_email_otp
        )
        self._otp_length = config["otp_length"] if otp_length is None else otp_length
        self._otp_ttl_s = config["otp_ttl_s"] if otp_ttl_s is None else otp_ttl_s
        self._max_attempts = (
            config["verify_attempts_per_window"] if max_attempts is None else max_attempts
        )
        self._code_factory = code_factory or (
            lambda: "".join(str(secrets.randbelow(10)) for _ in range(self._otp_length))
        )
        self._clock = clock
        self._log_codes = log_codes
        self._token_ttl_s = token_ttl_s
        self._lock = threading.Lock()
        self._accounts: dict[str, _MemoryAccount] = {}  # key: email
        self._access: dict[str, tuple[UUID, float]] = {}  # token -> (user id, expiry time)
        self._refresh: dict[str, UUID] = {}

    @staticmethod
    def _hash(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)

    def _account_by_id(self, user_id: UUID) -> _MemoryAccount | None:
        return next((a for a in self._accounts.values() if a.id == user_id), None)

    def _new_session(self, user_id: UUID) -> AuthSession:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._access[access] = (user_id, time.monotonic() + self._token_ttl_s)
        self._refresh[refresh] = user_id
        return AuthSession(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._token_ttl_s,
            user_id=user_id,
        )

    def create_user(self, email: str, password: str) -> UUID:
        with self._lock:
            if email in self._accounts:
                raise EmailTakenError(email)
            salt = secrets.token_bytes(16)
            account = _MemoryAccount(uuid4(), email, salt, self._hash(password, salt))
            self._accounts[email] = account
            return account.id

    def _issue_otp(self, account: _MemoryAccount) -> None:
        code = self._code_factory()
        account.otp_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        account.otp_expires_at = self._clock() + self._otp_ttl_s
        account.otp_attempts = 0
        if self._log_codes:
            logger.info("dev OTP for %s : %s", _mask_email(account.email), code)

    def sign_up(self, email: str, password: str) -> SignUpResult:
        email = email.strip().lower()
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError()
        with self._lock:
            account = self._accounts.get(email)
            if account is not None:
                if account.confirmed:
                    raise EmailTakenError()
                self._issue_otp(account)
                return SignUpResult(str(account.id), True, False)
            salt = secrets.token_bytes(16)
            account = _MemoryAccount(
                uuid4(), email, salt, self._hash(password, salt), not self._require_email_otp
            )
            self._accounts[email] = account
            if not account.confirmed:
                self._issue_otp(account)
            return SignUpResult(str(account.id), not account.confirmed, True)

    def verify_signup_otp(self, email: str, token: str) -> None:
        """Confirm an account; confirmed accounts also return invalid to hide their status."""
        with self._lock:
            account = self._accounts.get(email.strip().lower())
            if account is None or account.confirmed or account.otp_hash is None:
                raise OtpInvalidError()
            if self._clock() >= account.otp_expires_at:
                account.otp_hash = None
                raise OtpExpiredError()
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(account.otp_hash, digest):
                account.otp_attempts += 1
                if account.otp_attempts >= self._max_attempts:
                    account.otp_hash = None
                raise OtpInvalidError()
            account.confirmed = True
            account.otp_hash = None

    def resend_signup_otp(self, email: str) -> None:
        with self._lock:
            account = self._accounts.get(email.strip().lower())
            if account is not None and not account.confirmed:
                self._issue_otp(account)

    def delete_user(self, user_id: UUID) -> None:
        with self._lock:
            account = self._account_by_id(user_id)
            if account is not None:
                del self._accounts[account.email]
            self._access = {t: v for t, v in self._access.items() if v[0] != user_id}
            self._refresh = {t: u for t, u in self._refresh.items() if u != user_id}

    def sign_in(self, email: str, password: str) -> AuthSession:
        with self._lock:
            account = self._accounts.get(email)
            if account is None or not hmac.compare_digest(
                account.password_hash, self._hash(password, account.salt)
            ):
                raise InvalidCredentialsError()
            if not account.confirmed:
                raise EmailNotConfirmedError()
            return self._new_session(account.id)

    def refresh(self, refresh_token: str) -> AuthSession:
        with self._lock:
            user_id = self._refresh.pop(refresh_token, None)  # one use only, like Supabase
            if user_id is None or self._account_by_id(user_id) is None:
                raise InvalidCredentialsError()
            return self._new_session(user_id)

    def verify_token(self, access_token: str) -> TokenUser | None:
        with self._lock:
            entry = self._access.get(access_token)
            if entry is None:
                return None
            user_id, expires_at = entry
            account = self._account_by_id(user_id)
            if account is None or time.monotonic() >= expires_at:
                self._access.pop(access_token, None)
                return None
            return TokenUser(id=user_id, email=account.email)

    def sign_out(self, access_token: str) -> None:
        with self._lock:
            entry = self._access.pop(access_token, None)
            if entry is not None:
                self._refresh = {t: u for t, u in self._refresh.items() if u != entry[0]}

    def update_password(self, user_id: UUID, password: str) -> None:
        with self._lock:
            account = self._account_by_id(user_id)
            if account is None:
                raise InvalidCredentialsError()
            account.salt = secrets.token_bytes(16)
            account.password_hash = self._hash(password, account.salt)


# ---------- Supabase Auth provider ----------


def _is_unavailable(err: Exception) -> bool:
    """Network problems and 5xx answers are outages, not a wrong password."""
    if isinstance(err, AuthRetryableError | httpx.HTTPError):
        return True
    status = getattr(err, "status", None)
    return isinstance(status, int) and status >= 500


def _created_by_this_call(user) -> bool:
    """Infer creation only from sufficiently close server timestamps."""
    ref = user.confirmation_sent_at or user.email_confirmed_at
    if ref is None or user.created_at is None:
        return False
    try:
        return 0 <= (ref - user.created_at).total_seconds() < 5
    except (TypeError, ValueError):
        return False


def _is_rate_limited(err: Exception) -> bool:
    return getattr(err, "status", None) == 429 or getattr(err, "code", None) in {
        "over_email_send_rate_limit", "over_request_rate_limit"
    }


class SupabaseAuthProvider:
    """Supabase Auth through its REST API, with the service key (server side only).

    Sign in / refresh use a new client each time: a GoTrue client stores the session it
    receives, and a shared one would mix sessions of different users.
    """

    def __init__(
        self, url: str, service_key: str, *, require_email_otp: bool | None = None
    ) -> None:
        self._require_email_otp = (
            CONSTANTS["auth"]["require_email_otp"]
            if require_email_otp is None else require_email_otp
        )
        self._url = f"{url.rstrip('/')}/auth/v1"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._admin_client = self._new_client()  # admin calls and token checks, no session

    def _new_client(self) -> SyncGoTrueClient:
        return SyncGoTrueClient(
            url=self._url,
            headers=dict(self._headers),
            auto_refresh_token=False,
            persist_session=False,
        )

    @staticmethod
    def _to_session(resp) -> AuthSession:
        session = getattr(resp, "session", None)
        if session is None or resp.user is None:
            raise AuthUnavailableError("Auth answer has no session")
        return AuthSession(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=session.expires_in,
            user_id=UUID(resp.user.id),
        )

    def create_user(self, email: str, password: str) -> UUID:
        try:
            # email_confirm: the account works at once, no confirmation email to click
            resp = self._admin_client.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
        except AuthApiError as err:
            code = (err.code or "").lower()
            if code in {"email_exists", "user_already_exists"} or "already" in err.message.lower():
                raise EmailTakenError(email) from err
            if code == "weak_password":
                raise WeakPasswordError() from err
            raise AuthUnavailableError("Could not create the account") from err
        except Exception as err:
            raise AuthUnavailableError("Could not create the account") from err
        return UUID(resp.user.id)

    def _revoke_response_session(self, resp) -> None:
        session = getattr(resp, "session", None)
        if session is not None:
            try:
                self._admin_client.admin.sign_out(session.access_token, scope="local")
            except Exception:
                pass  # Best effort; never expose the session.

    def sign_up(self, email: str, password: str) -> SignUpResult:
        if not self._require_email_otp:
            return SignUpResult(str(self.create_user(email, password)), False, True)
        try:
            resp = self._new_client().sign_up({"email": email, "password": password})
        except AuthWeakPasswordError as err:
            raise WeakPasswordError() from err
        except Exception as err:
            if _is_rate_limited(err):
                raise AuthRateLimitedError() from err
            if isinstance(err, AuthApiError) and err.code in {
                "email_exists", "user_already_exists"
            }:
                raise EmailTakenError() from err
            raise AuthUnavailableError("Could not create the account") from err
        user = resp.user
        if user is None:
            self._revoke_response_session(resp)
            raise AuthUnavailableError("Could not create the account")
        self._revoke_response_session(resp)
        if user.identities == []:
            raise EmailTakenError()
        return SignUpResult(
            user.id, resp.session is None or user.email_confirmed_at is None,
            _created_by_this_call(user),
        )

    def verify_signup_otp(self, email: str, token: str) -> None:
        try:
            resp = self._new_client().verify_otp({"email": email, "token": token, "type": "signup"})
        except Exception as err:
            if _is_rate_limited(err):
                raise AuthRateLimitedError() from err
            if isinstance(err, AuthApiError) and 400 <= err.status < 500:
                raise OtpInvalidError() from err
            raise AuthUnavailableError("Could not verify the account") from err
        self._revoke_response_session(resp)

    def resend_signup_otp(self, email: str) -> None:
        try:
            self._new_client().resend({"type": "signup", "email": email})
        except Exception as err:
            if _is_rate_limited(err):
                raise AuthRateLimitedError() from err
            if isinstance(err, AuthApiError) and 400 <= err.status < 500:
                return
            raise AuthUnavailableError("Could not resend the code") from err

    def delete_user(self, user_id: UUID) -> None:
        try:
            self._admin_client.admin.delete_user(str(user_id))
        except Exception as err:
            raise AuthUnavailableError("Could not delete the account") from err

    def sign_in(self, email: str, password: str) -> AuthSession:
        try:
            resp = self._new_client().sign_in_with_password({"email": email, "password": password})
        except Exception as err:
            if isinstance(err, AuthApiError) and err.code == "email_not_confirmed":
                raise EmailNotConfirmedError() from err
            if isinstance(err, AuthError) and not _is_unavailable(err):
                raise InvalidCredentialsError() from err
            raise AuthUnavailableError("Could not sign in") from err
        return self._to_session(resp)

    def refresh(self, refresh_token: str) -> AuthSession:
        try:
            resp = self._new_client().refresh_session(refresh_token)
        except Exception as err:
            if isinstance(err, AuthError) and not _is_unavailable(err):
                raise InvalidCredentialsError() from err
            raise AuthUnavailableError("Could not refresh the session") from err
        return self._to_session(resp)

    def verify_token(self, access_token: str) -> TokenUser | None:
        try:
            # Checks signature and expiry (asymmetric keys: locally with the cached JWKS;
            # older HS256 projects: asks Supabase Auth).
            resp = self._admin_client.get_claims(jwt=access_token)
        except Exception as err:
            if _is_unavailable(err):
                raise AuthUnavailableError("Could not check the access token") from err
            return None
        claims = resp.get("claims", {}) if resp else {}
        if claims.get("role") != "authenticated" or not claims.get("sub"):
            return None  # e.g. the anon or service key sent as a user token
        try:
            return TokenUser(id=UUID(claims["sub"]), email=claims.get("email"))
        except ValueError:
            return None

    def sign_out(self, access_token: str) -> None:
        try:
            self._admin_client.admin.sign_out(access_token, scope="local")
        except Exception:
            # Best effort: the browser drops its tokens anyway; the access token expires by itself.
            logger.warning("Could not revoke the session on Supabase Auth")

    def update_password(self, user_id: UUID, password: str) -> None:
        try:
            self._admin_client.admin.update_user_by_id(str(user_id), {"password": password})
        except AuthApiError as err:
            if (err.code or "").lower() == "weak_password":
                raise WeakPasswordError() from err
            raise AuthUnavailableError("Could not change the password") from err
        except Exception as err:
            raise AuthUnavailableError("Could not change the password") from err


@lru_cache(maxsize=1)
def get_auth() -> AuthProvider:
    """FastAPI dependency: Supabase Auth when SUPABASE_URL is set, RAM accounts in dev."""
    if settings.supabase_url:
        return SupabaseAuthProvider(settings.supabase_url, settings.supabase_service_key)
    if settings.app_env == "dev":
        return MemoryAuthProvider(log_codes=True)
    raise AuthUnavailableError("Auth is not configured")
