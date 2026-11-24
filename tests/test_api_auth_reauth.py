"""Change password with the current one (ADR-011): 403 wrong_password, 422 same_password, 429."""

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.auth import AuthUnavailableError, get_auth
from src.app.constants import CONSTANTS
from src.app.deps import get_current_user

EMAIL, PASSWORD = "ana@example.com", "correct-horse"


@pytest.fixture
def client():
    main.app.dependency_overrides.pop(get_current_user, None)  # real token check
    return TestClient(main.app)


def _auth():
    return main.app.dependency_overrides[get_auth]()


def _token(client) -> dict:
    client.post("/api/auth/signup", json={
        "email": EMAIL, "password": PASSWORD, "target_accent": "American",
        "consent_recording": True,
    })
    assert client.post(
        "/api/auth/verify-otp", json={"email": EMAIL, "token": TEST_OTP}
    ).status_code == 200
    token = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def _change(client, headers, current, new):
    return client.put(
        "/api/auth/password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


def test_wrong_current_password_is_403_and_keeps_the_old_password(client):
    headers = _token(client)
    r = _change(client, headers, "not-my-password", "new-password-9")
    assert r.status_code == 403  # not 401: the browser would end the session on a 401
    assert r.json()["error_code"] == "wrong_password"
    assert _auth().verify_password(EMAIL, PASSWORD)


def test_same_password_is_422_before_any_check(client, monkeypatch):
    headers = _token(client)
    calls = []
    monkeypatch.setattr(_auth(), "verify_password", lambda *a: calls.append(a) or True)
    r = _change(client, headers, PASSWORD, PASSWORD)
    assert r.status_code == 422 and r.json()["error_code"] == "same_password"
    assert calls == []


def test_old_payload_shape_is_rejected(client):
    headers = _token(client)
    r = client.put("/api/auth/password", json={"password": "new-password-9"}, headers=headers)
    assert r.status_code == 422


def test_reauth_attempts_are_rate_limited(client):
    headers = _token(client)
    limit = CONSTANTS["auth"]["verify_attempts_per_window"]
    for _ in range(limit):
        assert _change(client, headers, "wrong-password", "new-password-9").status_code == 403
    r = _change(client, headers, PASSWORD, "new-password-9")
    assert r.status_code == 429 and r.json()["error_code"] == "rate_limited"


def test_reauth_service_down_is_503(client, monkeypatch):
    headers = _token(client)

    def down(*args):
        raise AuthUnavailableError("down")

    monkeypatch.setattr(_auth(), "verify_password", down)
    r = _change(client, headers, PASSWORD, "new-password-9")
    assert r.status_code == 503 and r.json()["error_code"] == "auth_unavailable"
