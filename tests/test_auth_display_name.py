"""The account keeps a copy of the display name, so the emails can greet the user with it.

The profile is the source of truth; the copy (Supabase user_metadata.display_name) is set at
sign up, after the sign-up code, and when Profile changes the name. Uses the in-memory provider.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from conftest import TEST_OTP, TEST_USER_ID
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.auth import AuthUnavailableError, SupabaseAuthProvider, get_auth
from src.app.db.factory import get_repos
from src.app.db.models import ProfileUpsert

EMAIL = "bee@example.com"
SIGNUP = {
    "email": EMAIL, "password": "password-1", "target_accent": "American",
    "display_name": " Bee ", "consent_recording": True,
}


@pytest.fixture
def client():
    return TestClient(main.app)


def _auth():
    return main.app.dependency_overrides[get_auth]()


def _account():
    return _auth()._accounts[EMAIL]


def test_sign_up_copies_the_display_name(client):
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 201
    assert _account().display_name == "Bee"


def test_sign_up_without_a_name_uses_the_email(client):
    client.post("/api/auth/signup", json={**SIGNUP, "display_name": None})
    assert _account().display_name == "bee"


def test_the_latest_form_name_is_copied_after_the_code(client):
    client.post("/api/auth/signup", json=SIGNUP)
    profile = {"target_accent": "British", "display_name": "Beatrice", "consent_recording": True}
    response = client.post(
        "/api/auth/verify-otp", json={"email": EMAIL, "token": TEST_OTP, "profile": profile}
    )
    assert response.status_code == 200
    assert _account().display_name == "Beatrice"


def test_profile_change_copies_the_new_name(client, monkeypatch):
    repos = main.app.dependency_overrides[get_repos]()
    repos.profiles.upsert_profile(TEST_USER_ID, ProfileUpsert(target_accent="American"))
    copied = []
    monkeypatch.setattr(_auth(), "set_display_name", lambda uid, name: copied.append((uid, name)))
    assert client.patch("/api/profile", json={"display_name": "Cee"}).status_code == 200
    assert copied == [(TEST_USER_ID, "Cee")]
    assert client.patch("/api/profile", json={"age": 30}).status_code == 200
    assert len(copied) == 1  # no name sent: nothing to copy


def test_copy_failure_does_not_fail_the_profile_change(client, monkeypatch):
    repos = main.app.dependency_overrides[get_repos]()
    repos.profiles.upsert_profile(TEST_USER_ID, ProfileUpsert(target_accent="American"))

    def down(_uid, _name):
        raise AuthUnavailableError()

    monkeypatch.setattr(_auth(), "set_display_name", down)
    response = client.patch("/api/profile", json={"display_name": "Cee"})
    assert response.status_code == 200 and response.json()["display_name"] == "Cee"


# ---------- SupabaseAuthProvider, with a fake GoTrue client ----------


def test_supabase_sign_up_sends_the_name_as_metadata():
    sent = {}

    def sign_up(credentials):
        sent.update(credentials)
        user = SimpleNamespace(
            id=str(uuid4()), identities=[{}], email_confirmed_at=None,
            confirmation_sent_at=None, created_at=None,
        )
        return SimpleNamespace(user=user, session=None)

    provider = SupabaseAuthProvider("https://example.supabase.co", "service-key")
    provider._new_client = lambda: SimpleNamespace(sign_up=sign_up)
    provider.sign_up(EMAIL, "password-1", "Bee")
    assert sent["options"] == {"data": {"display_name": "Bee"}}


def test_supabase_set_display_name_updates_user_metadata():
    calls = []
    provider = SupabaseAuthProvider("https://example.supabase.co", "service-key")
    provider._admin_client = SimpleNamespace(admin=SimpleNamespace(
        update_user_by_id=lambda uid, attrs: calls.append((uid, attrs))
    ))
    user_id = UUID("00000000-0000-4000-8000-000000000009")
    provider.set_display_name(user_id, "Bee")
    assert calls == [(str(user_id), {"user_metadata": {"display_name": "Bee"}})]
