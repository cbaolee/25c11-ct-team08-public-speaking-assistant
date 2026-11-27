"""get_current_user: the user comes only from a verified `Authorization: Bearer` token."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.app.auth import AuthUnavailableError, MemoryAuthProvider, TokenUser
from src.app.deps import get_bearer_token, get_current_user


def _signed_in(auth: MemoryAuthProvider) -> tuple[str, str]:
    user_id = auth.create_user("a@example.com", "password-1")
    return str(user_id), auth.sign_in("a@example.com", "password-1").access_token


def test_get_current_user_valid_token_returns_user():
    auth = MemoryAuthProvider()
    user_id, token = _signed_in(auth)

    user = get_current_user(token, auth)
    assert str(user.id) == user_id
    assert user.email == "a@example.com"


def test_get_current_user_unknown_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        get_current_user("not-a-token", MemoryAuthProvider())
    assert exc.value.status_code == 401
    assert exc.value.detail == "not_authenticated"


def test_get_current_user_expired_token_raises_401():
    auth = MemoryAuthProvider(token_ttl_s=0)  # every token is already expired
    _, token = _signed_in(auth)

    with pytest.raises(HTTPException) as exc:
        get_current_user(token, auth)
    assert exc.value.status_code == 401


def test_get_current_user_auth_down_raises_503():
    class DownAuth:
        def verify_token(self, token: str) -> TokenUser | None:
            raise AuthUnavailableError("down")

    with pytest.raises(HTTPException) as exc:
        get_current_user("token", DownAuth())
    assert exc.value.status_code == 503
    assert exc.value.detail == "auth_unavailable"


def test_get_bearer_token_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc:
        get_bearer_token(None)
    assert exc.value.status_code == 401


def test_get_bearer_token_returns_raw_token():
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="abc")
    assert get_bearer_token(creds) == "abc"


def test_get_current_user_logged_out_token_raises_401():
    auth = MemoryAuthProvider()
    _, token = _signed_in(auth)
    auth.sign_out(token)

    with pytest.raises(HTTPException):
        get_current_user(token, auth)


def test_get_current_user_deleted_account_raises_401():
    auth = MemoryAuthProvider()
    user_id, token = _signed_in(auth)
    from uuid import UUID

    auth.delete_user(UUID(user_id))
    with pytest.raises(HTTPException):
        get_current_user(token, auth)
    assert auth.verify_token(str(uuid4())) is None
