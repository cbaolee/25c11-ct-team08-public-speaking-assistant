"""Sign up, log in, refresh, log out and password change through the API.

Uses the in-memory account provider and repositories from tests/conftest.py; the
`get_current_user` override is removed so the real token check runs.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient

import src.app.main as main
from src.app import auth as auth_module
from src.app.auth import (
    AuthUnavailableError,
    EmailTakenError,
    InvalidCredentialsError,
    SupabaseAuthProvider,
    WeakPasswordError,
    get_auth,
)
from src.app.db.factory import get_repos
from src.app.db.models import StorageError
from src.app.deps import get_current_user

SIGNUP = {
    "email": "Ana@Example.com",
    "password": "correct-horse",
    "target_accent": "American",
    "age": 21,
    "gender": "Female",
    "consent_recording": True,
}


@pytest.fixture
def client():
    main.app.dependency_overrides.pop(get_current_user, None)  # real token check
    return TestClient(main.app)


def _repos():
    return main.app.dependency_overrides[get_repos]()


def _auth():
    return main.app.dependency_overrides[get_auth]()


# OTP: accounts must verify before login (ADR-010)
def _signup_and_verify(client):
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.post(
        "/api/auth/verify-otp", json={"email": SIGNUP["email"], "token": TEST_OTP}
    )
    assert response.status_code == 200


def _login(client, email="ana@example.com", password="correct-horse"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_signup_creates_account_and_profile(client):
    r = client.post("/api/auth/signup", json=SIGNUP)
    assert r.status_code == 201
    user_id = UUID(r.json()["user_id"])
    profile = _repos().profiles.get_profile(user_id)
    assert profile.target_accent == "American"
    assert profile.display_name == "ana"  # email is lower-cased, name from its first part
    assert profile.consent_recording is True


def test_signup_same_email_returns_409(client):
    _signup_and_verify(client)
    r = client.post("/api/auth/signup", json={**SIGNUP, "email": "ana@example.com"})
    assert r.status_code == 409
    assert r.json()["error_code"] == "email_taken"


@pytest.mark.parametrize(
    ("change", "code"),
    [({"email": "not-an-email"}, "invalid_email"), ({"password": "short"}, "weak_password")],
)
def test_signup_invalid_input_returns_422(client, change, code):
    r = client.post("/api/auth/signup", json={**SIGNUP, **change})
    assert r.status_code == 422
    assert r.json()["error_code"] == code


def test_signup_profile_failure_removes_account(client, monkeypatch):
    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(_repos().profiles, "upsert_profile", broken)
    r = client.post("/api/auth/signup", json=SIGNUP)
    assert r.status_code == 503
    assert r.json()["error_code"] == "profile_not_saved"
    assert _login(client).status_code == 401  # the half-made account is gone
    monkeypatch.undo()
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 201  # email free again


def test_login_returns_tokens_that_open_the_api(client):
    _signup_and_verify(client)
    r = _login(client, email=" ANA@example.com ")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"access_token", "refresh_token", "expires_in", "user_id"}
    profile = client.get("/api/profile", headers=_bearer(body["access_token"]))
    assert profile.status_code == 200
    assert profile.json()["email"] == "ana@example.com"


def test_login_wrong_password_returns_401(client):
    _signup_and_verify(client)
    r = _login(client, password="wrong-password")
    assert r.status_code == 401
    assert r.json()["error_code"] == "invalid_credentials"


def test_api_without_token_returns_401(client):
    for path in ("/api/profile", "/api/sessions", "/api/baseline", "/api/scripts"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json() == {"detail": "not_authenticated"}


def test_refresh_gives_new_session_and_old_refresh_token_stops_working(client):
    _signup_and_verify(client)
    first = _login(client).json()
    r = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    assert client.get("/api/profile", headers=_bearer(r.json()["access_token"])).status_code == 200
    again = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert again.status_code == 401
    assert again.json()["error_code"] == "invalid_refresh_token"


def test_logout_revokes_the_access_token(client):
    _signup_and_verify(client)
    token = _login(client).json()["access_token"]
    assert client.post("/api/auth/logout", headers=_bearer(token)).json() == {"logged_out": True}
    assert client.get("/api/profile", headers=_bearer(token)).status_code == 401


def test_change_password_then_login_with_new_one(client):
    _signup_and_verify(client)
    token = _login(client).json()["access_token"]
    short = client.put(
        "/api/auth/password",
        json={"current_password": "correct-horse", "new_password": "short"},
        headers=_bearer(token),
    )
    assert short.status_code == 422
    r = client.put(
        "/api/auth/password",
        json={"current_password": "correct-horse", "new_password": "new-password-9"},
        headers=_bearer(token),
    )
    assert r.json() == {"updated": True}
    assert client.get("/api/profile", headers=_bearer(token)).status_code == 200  # session kept
    assert _login(client).status_code == 401
    assert _login(client, password="new-password-9").status_code == 200


def test_auth_service_down_returns_503(client, monkeypatch):
    def down(*args, **kwargs):
        raise AuthUnavailableError("down")

    monkeypatch.setattr(_auth(), "sign_in", down)
    r = _login(client)
    assert r.status_code == 503
    assert r.json()["error_code"] == "auth_unavailable"


def test_get_auth_uses_memory_in_dev_without_supabase(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "supabase_url", "")
    monkeypatch.setattr(auth_module.settings, "app_env", "dev")
    get_auth.cache_clear()
    try:
        assert isinstance(get_auth(), auth_module.MemoryAuthProvider)
        monkeypatch.setattr(auth_module.settings, "app_env", "prod")
        get_auth.cache_clear()
        with pytest.raises(AuthUnavailableError):
            get_auth()
    finally:
        get_auth.cache_clear()


# ---------- SupabaseAuthProvider: error mapping, with a fake GoTrue client ----------


def _provider(fake_admin) -> SupabaseAuthProvider:
    provider = SupabaseAuthProvider("https://example.supabase.co", "service-key")
    provider._admin_client = fake_admin
    return provider


def _api_error(code: str, status: int = 422, message: str = "error"):
    from supabase_auth.errors import AuthApiError

    return AuthApiError(message, status, code)


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        (_api_error("email_exists"), EmailTakenError),
        (_api_error("weak_password"), WeakPasswordError),
        (_api_error("unexpected_failure", status=500), AuthUnavailableError),
    ],
)
def test_supabase_create_user_maps_errors(err, expected):
    def create_user(attributes):
        raise err

    provider = _provider(SimpleNamespace(admin=SimpleNamespace(create_user=create_user)))
    with pytest.raises(expected):
        provider.create_user("a@example.com", "password-1")


def test_supabase_sign_in_wrong_password_is_invalid_credentials(monkeypatch):
    def sign_in(credentials):
        raise _api_error("invalid_credentials", status=400)

    provider = _provider(SimpleNamespace())
    monkeypatch.setattr(
        provider, "_new_client", lambda: SimpleNamespace(sign_in_with_password=sign_in)
    )
    with pytest.raises(InvalidCredentialsError):
        provider.sign_in("a@example.com", "bad")


@pytest.mark.parametrize(
    ("claims", "is_user"),
    [
        ({"sub": "6f1c8a4e-3f0b-4c69-9d27-2a8f1b2c3d4e", "role": "authenticated"}, True),
        ({"sub": "6f1c8a4e-3f0b-4c69-9d27-2a8f1b2c3d4e", "role": "service_role"}, False),
        ({"role": "anon"}, False),
    ],
)
def test_supabase_verify_token_accepts_only_user_tokens(claims, is_user):
    provider = _provider(SimpleNamespace(get_claims=lambda jwt: {"claims": claims}))
    assert (provider.verify_token("jwt") is not None) is is_user


def test_supabase_verify_token_bad_jwt_returns_none_and_outage_raises():
    from supabase_auth.errors import AuthInvalidJwtError, AuthRetryableError

    def bad(jwt):
        raise AuthInvalidJwtError("JWT has expired")

    def down(jwt):
        raise AuthRetryableError("timeout", 0)

    assert _provider(SimpleNamespace(get_claims=bad)).verify_token("jwt") is None
    with pytest.raises(AuthUnavailableError):
        _provider(SimpleNamespace(get_claims=down)).verify_token("jwt")
