"""GET/PATCH /api/profile with the in-memory repositories (tests/conftest.py)."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import src.app.main as main
from src.app.db.factory import get_repos
from src.app.db.models import ProfileUpsert, StorageError
from tests.conftest import TEST_USER_ID


@pytest.fixture
def repos():
    return main.app.dependency_overrides[get_repos]()


@pytest.fixture
def client(repos):
    repos.profiles.upsert_profile(
        TEST_USER_ID, ProfileUpsert(target_accent="American", display_name="ana", topics=["it"])
    )
    return TestClient(main.app)


def test_get_profile_returns_row_and_email(client):
    body = client.get("/api/profile").json()
    assert body["id"] == str(TEST_USER_ID)
    assert body["email"] == "test@example.com"
    assert (body["display_name"], body["target_accent"]) == ("ana", "American")
    assert body["consent_recording"] is False


def test_get_profile_missing_returns_404(repos):
    r = TestClient(main.app).get("/api/profile")
    assert r.status_code == 404
    assert r.json()["error_code"] == "profile_not_found"


def test_patch_profile_changes_only_sent_fields(client):
    r = client.patch("/api/profile", json={"age": 30, "topics": ["sports", "wildlife"]})
    assert r.status_code == 200
    body = r.json()
    assert (body["age"], body["topics"]) == (30, ["sports", "wildlife"])
    assert body["target_accent"] == "American"  # not sent, not changed


def test_patch_profile_consent_sets_timestamp(client):
    body = client.patch("/api/profile", json={"consent_recording": True}).json()
    assert body["consent_recording"] is True
    assert body["consent_updated_at"] is not None


def test_patch_profile_null_accent_returns_422(client):
    r = client.patch("/api/profile", json={"target_accent": None})
    assert r.status_code == 422
    assert r.json()["error_code"] == "invalid_profile"


def test_patch_profile_bad_age_returns_422(client):
    assert client.patch("/api/profile", json={"age": 0}).status_code == 422


def test_profile_storage_error_returns_503(client, repos, monkeypatch):
    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.profiles, "get_profile", broken)
    r = client.get("/api/profile")
    assert r.status_code == 503
    assert r.json()["error_code"] == "profile_unavailable"


def test_patch_profile_merges_preferences(client):
    first = client.patch("/api/profile", json={"preferences": {"follow_wpm": 150, "theme": "dark"}})
    assert first.status_code == 200
    second = client.patch("/api/profile", json={"preferences": {"follow_wpm": 155}})
    assert second.status_code == 200
    assert second.json()["preferences"] == {"follow_wpm": 155, "theme": "dark"}


def test_patch_profile_rejects_follow_wpm_outside_range(client):
    r = client.patch("/api/profile", json={"preferences": {"follow_wpm": 181}})
    assert r.status_code == 422


def test_upload_avatar_resizes_and_delete_clears_it(client):
    source = BytesIO()
    Image.new("RGB", (600, 400), "red").save(source, format="PNG")
    upload = ("avatar.png", source.getvalue(), "image/png")
    r = client.put("/api/profile/avatar", files={"file": upload})
    assert r.status_code == 200
    assert r.json()["avatar_url"].startswith("memory://")

    profile = client.get("/api/profile").json()
    assert profile["avatar_path"].endswith("/avatar.webp")

    r = client.delete("/api/profile/avatar")
    assert r.status_code == 200
    assert r.json()["avatar_url"] is None
    assert client.get("/api/profile").json()["avatar_path"] is None
