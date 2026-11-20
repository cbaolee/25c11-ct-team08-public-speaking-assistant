"""GET/PATCH /api/profile with the in-memory repositories (tests/conftest.py)."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import src.app.main as main
import src.app.routes.profile as profile_routes
from src.app.config import avatar_size_px, settings
from src.app.db.factory import get_repos
from src.app.db.models import ProfileUpsert, StorageError, build_avatar_path
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


def test_patch_profile_merges_preferences(client, repos):
    # A key written earlier (e.g. by a newer app version) must survive a PATCH of follow_wpm.
    repos.profiles.merge_preferences(TEST_USER_ID, {"theme": "dark"})
    first = client.patch("/api/profile", json={"preferences": {"follow_wpm": 150}})
    assert first.status_code == 200
    second = client.patch("/api/profile", json={"preferences": {"follow_wpm": 155}})
    assert second.status_code == 200
    assert second.json()["preferences"] == {"follow_wpm": 155, "theme": "dark"}


def test_patch_preferences_ignores_bad_stored_value(client, repos):
    # A stored value outside today's range must not block saving a valid one.
    repos.profiles.merge_preferences(TEST_USER_ID, {"follow_wpm": 999})
    r = client.patch("/api/profile", json={"preferences": {"follow_wpm": 150}})
    assert r.status_code == 200
    assert r.json()["preferences"]["follow_wpm"] == 150


@pytest.mark.parametrize(
    "prefs", [{"follow_wpm": 147}, {"follow_wpm": "150"}, {"follow_wpm": True}, {"abc": 1}]
)
def test_patch_preferences_rejects_bad_input(client, prefs):
    assert client.patch("/api/profile", json={"preferences": prefs}).status_code == 422


def test_patch_preferences_storage_error_returns_503(client, repos, monkeypatch):
    def fail(*_args):
        raise StorageError("down")

    monkeypatch.setattr(repos.profiles, "merge_preferences", fail)
    r = client.patch("/api/profile", json={"preferences": {"follow_wpm": 150}})
    assert r.status_code == 503
    assert r.json()["error_code"] == "profile_unavailable"


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


def _image_bytes(size=(600, 400), fmt="PNG", color="red", exif=None) -> bytes:
    out = BytesIO()
    image = Image.new("RGB", size, color)
    if exif is not None:
        image.save(out, format=fmt, exif=exif)
    else:
        image.save(out, format=fmt)
    return out.getvalue()


def _put_avatar(client, content, name="avatar.png"):
    return client.put("/api/profile/avatar", files={"file": (name, content, "image/png")})


def _stored_avatar(repos) -> Image.Image:
    data = repos.files._state.files[(settings.avatars_bucket, build_avatar_path(TEST_USER_ID))]
    return Image.open(BytesIO(data))


@pytest.mark.parametrize(
    "content", [b"hello, not a picture", _image_bytes(fmt="GIF")], ids=["renamed_text", "gif"]
)
def test_upload_avatar_rejects_non_picture(client, content):
    r = _put_avatar(client, content)
    assert r.status_code == 422
    assert r.json()["error_code"] == "avatar_invalid"


def test_upload_avatar_too_large_returns_413(client, monkeypatch):
    monkeypatch.setattr(profile_routes, "avatar_max_bytes", 100)
    r = _put_avatar(client, _image_bytes())
    assert r.status_code == 413
    assert r.json()["error_code"] == "avatar_too_large"


def test_upload_avatar_too_many_pixels_returns_422(client, monkeypatch):
    monkeypatch.setattr(profile_routes, "avatar_max_side_px", 500)
    r = _put_avatar(client, _image_bytes(size=(600, 400)))
    assert r.status_code == 422
    assert r.json()["error_code"] == "avatar_invalid"


def test_uploaded_avatar_is_one_square_webp(client, repos):
    assert _put_avatar(client, _image_bytes()).status_code == 200
    assert _put_avatar(client, _image_bytes(color="blue")).status_code == 200
    keys = [k for k in repos.files._state.files if k[0] == settings.avatars_bucket]
    assert keys == [(settings.avatars_bucket, build_avatar_path(TEST_USER_ID))]
    stored = _stored_avatar(repos)
    assert stored.format == "WEBP"
    assert stored.size == (avatar_size_px, avatar_size_px)


def test_upload_avatar_follows_exif_rotation(client, repos):
    # 400x200: left half red, right half blue; EXIF 6 = shown rotated 90 degrees clockwise,
    # so after rotation red must be on top.
    image = Image.new("RGB", (400, 200), "blue")
    image.paste((255, 0, 0), (0, 0, 200, 200))
    exif = Image.Exif()
    exif[0x0112] = 6
    out = BytesIO()
    image.save(out, format="JPEG", exif=exif)
    assert _put_avatar(client, out.getvalue(), "photo.jpg").status_code == 200
    top = _stored_avatar(repos).convert("RGB").getpixel((avatar_size_px // 2, 5))
    assert top[0] > 200 and top[2] < 60


def test_upload_avatar_removes_file_when_path_save_fails(client, repos, monkeypatch):
    def fail(*_args):
        raise StorageError("down")

    monkeypatch.setattr(repos.profiles, "set_avatar_path", fail)
    r = _put_avatar(client, _image_bytes())
    assert r.status_code == 503
    assert not any(k[0] == settings.avatars_bucket for k in repos.files._state.files)


def test_upload_avatar_without_profile_stores_nothing(repos):
    r = _put_avatar(TestClient(main.app), _image_bytes())
    assert r.status_code == 404
    assert not any(k[0] == settings.avatars_bucket for k in repos.files._state.files)


def test_delete_avatar_removes_file_even_if_path_is_null(client, repos):
    assert _put_avatar(client, _image_bytes()).status_code == 200
    repos.profiles.set_avatar_path(TEST_USER_ID, None)
    r = client.delete("/api/profile/avatar")
    assert r.status_code == 200
    assert not any(k[0] == settings.avatars_bucket for k in repos.files._state.files)


def test_delete_avatar_when_none(client):
    r = client.delete("/api/profile/avatar")
    assert r.status_code == 200
    assert r.json()["avatar_url"] is None


def test_new_profile_has_no_avatar_and_empty_preferences(client):
    body = client.get("/api/profile").json()
    assert body["avatar_url"] is None
    assert body["preferences"] == {}
