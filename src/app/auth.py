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
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel
from supabase_auth import SyncGoTrueClient
from supabase_auth.errors import AuthApiError, AuthError, AuthRetryableError

from src.app.config import settings

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


class MemoryAuthProvider:
    def __init__(self, token_ttl_s: int = MEMORY_TOKEN_TTL_S) -> None:
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
            access_token=access, refresh_token=refresh,
            expires_in=self._token_ttl_s, user_id=user_id,
        )

    def create_user(self, email: str, password: str) -> UUID:
        with self._lock:
            if email in self._accounts:
                raise EmailTakenError(email)
            salt = secrets.token_bytes(16)
            account = _MemoryAccount(uuid4(), email, salt, self._hash(password, salt))
            self._accounts[email] = account
            return account.id

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


class SupabaseAuthProvider:
    """Supabase Auth through its REST API, with the service key (server side only).

    Sign in / refresh use a new client each time: a GoTrue client stores the session it
    receives, and a shared one would mix sessions of different users.
    """

    def __init__(self, url: str, service_key: str) -> None:
        self._url = f"{url.rstrip('/')}/auth/v1"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._admin_client = self._new_client()  # admin calls and token checks, no session

    def _new_client(self) -> SyncGoTrueClient:
        return SyncGoTrueClient(
            url=self._url, headers=dict(self._headers),
            auto_refresh_token=False, persist_session=False,
        )

    @staticmethod
    def _to_session(resp) -> AuthSession:
        session = getattr(resp, "session", None)
        if session is None or resp.user is None:
            raise AuthUnavailableError("Auth answer has no session")
        return AuthSession(
            access_token=session.access_token, refresh_token=session.refresh_token,
            expires_in=session.expires_in, user_id=UUID(resp.user.id),
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

    def delete_user(self, user_id: UUID) -> None:
        try:
            self._admin_client.admin.delete_user(str(user_id))
        except Exception as err:
            raise AuthUnavailableError("Could not delete the account") from err

    def sign_in(self, email: str, password: str) -> AuthSession:
        try:
            resp = self._new_client().sign_in_with_password({"email": email, "password": password})
        except Exception as err:
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
        return MemoryAuthProvider()
    raise AuthUnavailableError("Auth is not configured")
