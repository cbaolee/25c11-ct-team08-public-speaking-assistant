"""Signing up again before the email is confirmed: the latest form wins once the code is accepted.

GoTrue keeps the first password of an unconfirmed account and only sends a new code. The client
sends the latest sign-up form with the code; POST /api/auth/verify-otp saves it after the code is
accepted (ADR-010 D3, amended 21/11/2026). Uses the in-memory provider and repositories.
"""

from uuid import UUID

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient

from src.app.auth import AuthUnavailableError, get_auth
from src.app.db.factory import get_repos
from src.app.db.models import StorageError
from src.app.main import app

EMAIL = "again@example.com"
FIRST = {"email": EMAIL, "password": "password-1", "target_accent": "American"}
SECOND = {
    "email": EMAIL,
    "password": "password-2",
    "target_accent": "British",
    "display_name": "Bee",
    "consent_recording": True,
}
PROFILE_KEYS = ("target_accent", "display_name", "consent_recording")
SECOND_PROFILE = {key: SECOND[key] for key in PROFILE_KEYS}


@pytest.fixture
def client():
    return TestClient(app)


def _auth():
    return app.dependency_overrides[get_auth]()


def _repos():
    return app.dependency_overrides[get_repos]()


def _verify(client, **extra):
    return client.post("/api/auth/verify-otp", json={"email": EMAIL, "token": TEST_OTP, **extra})


def _login(client, password):
    return client.post("/api/auth/login", json={"email": EMAIL, "password": password})


def _sign_up_twice(client) -> UUID:
    first = client.post("/api/auth/signup", json=FIRST)
    assert first.status_code == 201
    again = client.post("/api/auth/signup", json=SECOND)
    assert again.status_code == 200 and again.json()["verification_required"] is True
    return UUID(first.json()["user_id"])


def test_latest_form_is_saved_after_the_code_is_accepted(client):
    user_id = _sign_up_twice(client)
    # Before the code: the repeat sign-up changed nothing
    assert _repos().profiles.get_profile(user_id).target_accent == "American"

    response = _verify(client, password=SECOND["password"], profile=SECOND_PROFILE)
    assert response.status_code == 200
    assert response.json() == {"verified": True, "password_updated": True, "profile_updated": True}

    assert _login(client, FIRST["password"]).status_code == 401
    assert _login(client, SECOND["password"]).status_code == 200
    profile = _repos().profiles.get_profile(user_id)
    assert profile.target_accent == "British"
    assert profile.display_name == "Bee"
    assert profile.consent_recording is True


def test_short_password_is_refused_before_the_code_is_used(client):
    _sign_up_twice(client)
    response = _verify(client, password="short")
    assert response.status_code == 422 and response.json()["error_code"] == "weak_password"
    # The code was not consumed and the account is still unconfirmed
    assert _login(client, FIRST["password"]).json()["error_code"] == "email_not_confirmed"
    assert _verify(client).status_code == 200
    assert _login(client, FIRST["password"]).status_code == 200


def test_code_without_form_keeps_the_first_password(client):
    _sign_up_twice(client)
    response = _verify(client)  # what the Log in path sends
    assert response.json() == {"verified": True, "password_updated": None, "profile_updated": None}
    assert _login(client, FIRST["password"]).status_code == 200
    assert _login(client, SECOND["password"]).status_code == 401


def test_password_save_failure_still_verifies_and_keeps_the_old_password(client, monkeypatch):
    _sign_up_twice(client)

    def fail(*_args, **_kwargs):
        raise AuthUnavailableError("down")

    monkeypatch.setattr(_auth(), "update_password", fail)
    response = _verify(client, password=SECOND["password"])
    assert response.status_code == 200
    assert response.json()["verified"] is True and response.json()["password_updated"] is False
    assert _login(client, FIRST["password"]).status_code == 200


def test_profile_save_failure_still_verifies(client, monkeypatch):
    user_id = _sign_up_twice(client)

    def fail(*_args, **_kwargs):
        raise StorageError("down")

    monkeypatch.setattr(_repos().profiles, "upsert_profile", fail)
    response = _verify(client, password=SECOND["password"], profile=SECOND_PROFILE)
    assert response.status_code == 200
    assert response.json() == {"verified": True, "password_updated": True, "profile_updated": False}
    assert _repos().profiles.get_profile(user_id).target_accent == "American"


def test_confirmed_account_cannot_be_changed_through_verify(client):
    assert client.post("/api/auth/signup", json=FIRST).status_code == 201
    assert _verify(client).status_code == 200
    response = _verify(client, password="password-evil", profile=SECOND_PROFILE)
    assert response.status_code == 422 and response.json()["error_code"] == "otp_invalid"
    assert _login(client, FIRST["password"]).status_code == 200
    assert _login(client, "password-evil").status_code == 401
