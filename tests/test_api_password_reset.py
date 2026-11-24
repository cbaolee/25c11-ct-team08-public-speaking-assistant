"""Forgot password: a recovery code by email, a new password, then every session ends.

Uses the in-memory provider and repositories from tests/conftest.py (the code is TEST_OTP);
the `get_current_user` override is removed so old tokens are really checked.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

import src.app.auth as auth_module
import src.app.main as main
from src.app.auth import SupabaseAuthProvider, get_auth
from src.app.deps import get_current_user

EMAIL = "reset@example.com"
OLD_PASSWORD = "old-password"
NEW_PASSWORD = "new-password"


@pytest.fixture
def client():
    main.app.dependency_overrides.pop(get_current_user, None)
    return TestClient(main.app)


def _auth():
    return main.app.dependency_overrides[get_auth]()


def _account(client) -> dict:
    client.post("/api/auth/signup", json={
        "email": EMAIL, "password": OLD_PASSWORD, "target_accent": "American",
        "consent_recording": True,
    })
    client.post("/api/auth/verify-otp", json={"email": EMAIL, "token": TEST_OTP})
    login = client.post("/api/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD})
    assert login.status_code == 200
    return login.json()


def _reset(client, token=TEST_OTP, password=NEW_PASSWORD, email=EMAIL):
    return client.post(
        "/api/auth/reset-password", json={"email": email, "token": token, "new_password": password}
    )


@pytest.mark.parametrize("email", [EMAIL, "nobody@example.com"])
def test_forgot_password_always_answers_sent(client, email):
    _account(client)
    response = client.post("/api/auth/forgot-password", json={"email": email})
    assert response.status_code == 200 and response.json() == {"sent": True}


def test_unknown_email_gets_no_code(client):
    client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert _reset(client, email="nobody@example.com").json()["error_code"] == "otp_invalid"


def test_code_sets_new_password_and_ends_every_session(client):
    tokens = _account(client)
    client.post("/api/auth/forgot-password", json={"email": EMAIL})
    response = _reset(client)
    assert response.status_code == 200 and response.json() == {"reset": True}

    old = client.post("/api/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD})
    assert old.status_code == 401
    new = client.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
    assert new.status_code == 200
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/api/profile", headers=headers).status_code == 401
    refresh = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401


def test_code_works_once(client):
    _account(client)
    client.post("/api/auth/forgot-password", json={"email": EMAIL})
    assert _reset(client).status_code == 200
    assert _reset(client, password="another-password").json()["error_code"] == "otp_invalid"


def test_wrong_code_is_invalid_and_password_stays(client):
    _account(client)
    client.post("/api/auth/forgot-password", json={"email": EMAIL})
    response = _reset(client, token="000000")
    assert response.status_code == 422 and response.json()["error_code"] == "otp_invalid"
    login = client.post("/api/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD})
    assert login.status_code == 200


def test_expired_code(client):
    _account(client)
    now = [0.0]
    _auth()._clock = lambda: now[0]
    client.post("/api/auth/forgot-password", json={"email": EMAIL})
    now[0] += 10_000
    assert _reset(client).json()["error_code"] == "otp_expired"


def test_weak_password_is_checked_before_the_code_is_tried(client):
    _account(client)
    client.post("/api/auth/forgot-password", json={"email": EMAIL})
    for _ in range(10):
        response = _reset(client, token="000000", password="short")
        assert response.status_code == 422 and response.json()["error_code"] == "weak_password"
    assert _reset(client).status_code == 200  # no try was used up


def test_too_many_tries_are_rate_limited(client):
    _account(client)
    client.post("/api/auth/forgot-password", json={"email": EMAIL})
    codes = [_reset(client, token="000000").status_code for _ in range(6)]
    assert codes[-1] == 429


def test_second_code_within_the_cooldown_is_rate_limited(client):
    assert client.post("/api/auth/forgot-password", json={"email": EMAIL}).status_code == 200
    second = client.post("/api/auth/forgot-password", json={"email": EMAIL})
    assert second.status_code == 429 and second.json()["error_code"] == "rate_limited"


def test_invalid_email_is_rejected(client):
    response = client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
    assert response.status_code == 422 and response.json()["error_code"] == "invalid_email"


# ---------- SupabaseAuthProvider: recovery code, with a fake GoTrue client ----------


def _supabase(admin, verify_otp):
    provider = SupabaseAuthProvider("https://example.supabase.co", "service-key")
    provider._admin_client = SimpleNamespace(admin=admin)
    provider._new_client = lambda: SimpleNamespace(verify_otp=verify_otp)
    return provider


def test_supabase_reset_sets_password_then_signs_out_everywhere():
    user_id, calls = uuid4(), []
    admin = SimpleNamespace(
        update_user_by_id=lambda uid, attrs: calls.append(("password", uid, attrs["password"])),
        sign_out=lambda token, scope: calls.append(("sign_out", token, scope)),
    )

    def verify_otp(params):
        assert params["type"] == "recovery"
        return SimpleNamespace(
            user=SimpleNamespace(id=str(user_id)), session=SimpleNamespace(access_token="acc")
        )

    assert _supabase(admin, verify_otp).reset_password_with_otp(EMAIL, "123456", NEW_PASSWORD) \
        == user_id
    assert calls == [("password", str(user_id), NEW_PASSWORD), ("sign_out", "acc", "global")]


@pytest.mark.parametrize(("code", "status", "expected"), [
    ("otp_expired", 403, "OtpExpiredError"),
    ("invalid_otp", 400, "OtpInvalidError"),
    ("unexpected_failure", 500, "AuthUnavailableError"),
])
def test_supabase_reset_maps_code_errors(code, status, expected):
    def verify_otp(params):
        raise AuthApiError("error", status, code)

    with pytest.raises(getattr(auth_module, expected)):
        _supabase(SimpleNamespace(), verify_otp).reset_password_with_otp(
            EMAIL, "123456", NEW_PASSWORD
        )
