"""Refresh token in an HttpOnly cookie, the Origin check and the security headers.

The client uses https://testserver because the cookie is Secure (httpx, like a browser, never
sends a Secure cookie over plain http). Uses the in-memory provider and repositories.
"""

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.deps import get_current_user

EMAIL = "cookie@example.com"
PASSWORD = "password-1"
ORIGIN = "https://testserver"


@pytest.fixture
def client():
    main.app.dependency_overrides.pop(get_current_user, None)  # real token check
    return TestClient(main.app, base_url=ORIGIN)


def _login(client):
    client.post("/api/auth/signup", json={
        "email": EMAIL, "password": PASSWORD, "target_accent": "American",
        "consent_recording": True,
    })
    client.post("/api/auth/verify-otp", json={"email": EMAIL, "token": TEST_OTP})
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return response


def _cookie_header(response) -> str:
    return response.headers["set-cookie"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_login_sets_an_httponly_strict_cookie_and_no_refresh_token_in_the_body(client):
    response = _login(client)
    assert "refresh_token" not in response.json()
    header = _cookie_header(response)
    assert header.startswith("psa_refresh=")
    for part in ("HttpOnly", "Secure", "SameSite=strict", "Path=/api/auth", "Max-Age=2592000"):
        assert part.lower() in header.lower(), part


def test_refresh_uses_the_cookie_and_sets_a_new_one(client):
    old_cookie = _login(client).cookies["psa_refresh"]
    response = client.post("/api/auth/refresh", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "expires_in", "user_id"}
    assert client.get("/api/profile", headers=_bearer(body["access_token"])).status_code == 200
    new_cookie = response.cookies["psa_refresh"]
    assert new_cookie and new_cookie != old_cookie


def test_used_refresh_cookie_is_refused_and_cleared(client):
    old_cookie = _login(client).cookies["psa_refresh"]
    assert client.post("/api/auth/refresh").status_code == 200
    client.cookies.clear()
    stale = TestClient(main.app, base_url=ORIGIN, cookies={"psa_refresh": old_cookie})
    response = stale.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_refresh_token"
    assert "max-age=0" in _cookie_header(response).lower()


def test_refresh_without_a_cookie_is_401(client):
    response = client.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_refresh_token"


def test_refresh_ignores_a_token_in_the_body(client):
    _login(client)
    client.cookies.clear()
    response = client.post("/api/auth/refresh", json={"refresh_token": "anything"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/api/auth/refresh", "/api/auth/logout"])
def test_another_origin_is_refused(client, path):
    _login(client)
    response = client.post(path, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["error_code"] == "origin_mismatch"


def test_logout_clears_the_cookie_and_revokes_the_session(client):
    token = _login(client).json()["access_token"]
    response = client.post("/api/auth/logout", headers={**_bearer(token), "Origin": ORIGIN})
    assert response.status_code == 200 and response.json() == {"logged_out": True}
    assert "max-age=0" in _cookie_header(response).lower()
    assert client.get("/api/profile", headers=_bearer(token)).status_code == 401
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_without_a_token_still_clears_the_cookie(client):
    _login(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert "max-age=0" in _cookie_header(response).lower()


def test_delete_account_clears_the_cookie(client):
    token = _login(client).json()["access_token"]
    response = client.request(
        "DELETE", "/api/auth/account", json={"password": PASSWORD}, headers=_bearer(token)
    )
    assert response.status_code == 200
    assert "max-age=0" in _cookie_header(response).lower()


def test_cookie_secure_flag_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(main.settings, "auth_cookie_secure", False)
    assert "secure" not in _cookie_header(_login(client)).lower().split("; ")


# ---------- security headers ----------


def test_page_has_csp_and_security_headers(client):
    response = client.get("/")
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "https://*.supabase.co" in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"


def test_json_responses_get_nosniff_but_no_csp(client):
    response = client.get("/api/config")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in response.headers
