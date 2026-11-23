"""DELETE /api/auth/account (ADR-011): password first, files in all 4 buckets, then the account."""

from uuid import UUID, uuid4

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.auth import AuthUnavailableError, get_auth
from src.app.config import settings
from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.models import (
    NewSession,
    ProfileUpsert,
    StorageError,
    build_avatar_path,
    build_object_path,
)
from src.app.deps import get_current_user

EMAIL, PASSWORD = "ana@example.com", "correct-horse"
BUCKETS = ["audio", "series", "baselines", "avatars"]


@pytest.fixture
def client():
    main.app.dependency_overrides.pop(get_current_user, None)  # real token check
    return TestClient(main.app)


def _repos():
    return main.app.dependency_overrides[get_repos]()


def _auth():
    return main.app.dependency_overrides[get_auth]()


def _account(client) -> tuple[UUID, dict]:
    r = client.post(
        "/api/auth/signup",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "target_accent": "American",
        },
    )
    user_id = UUID(r.json()["user_id"])
    client.post("/api/auth/verify-otp", json={"email": EMAIL, "token": TEST_OTP})
    token = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return user_id, {"Authorization": f"Bearer {token.json()['access_token']}"}


def _seed(user_id: UUID) -> None:
    repos = _repos()
    repos.profiles.upsert_profile(user_id, ProfileUpsert(target_accent="American"))
    session_id = uuid4()
    audio = build_object_path(user_id, session_id, ".webm")
    repos.sessions.create_session(
        user_id,
        NewSession(
            id=session_id,
            script_snapshot="hello",
            status="insufficient_audio",
            result={},
            result_schema_version="2.0",
        ),
    )
    repos.files.upload_file(user_id, "audio", audio, b"a", "audio/webm")
    repos.files.upload_file(
        user_id,
        "series",
        build_object_path(user_id, session_id, ".series.json"),
        b"{}",
        "application/json",
    )
    repos.files.upload_file(
        user_id, "baselines", build_object_path(user_id, uuid4(), ".webm"), b"b", "audio/webm"
    )
    repos.files.upload_file(user_id, "avatars", build_avatar_path(user_id), b"p", "image/webp")


def _delete(client, headers, password=PASSWORD):
    return client.request(
        "DELETE", "/api/auth/account", json={"password": password}, headers=headers
    )


def test_buckets_are_the_four_user_buckets():
    assert [
        settings.audio_bucket,
        settings.series_bucket,
        settings.baselines_bucket,
        settings.avatars_bucket,
    ] == BUCKETS


def test_delete_account_removes_files_rows_and_login(client):
    user_id, headers = _account(client)
    _seed(user_id)
    r = _delete(client, headers)
    assert r.status_code == 200 and r.json() == {"deleted": True}
    repos = _repos()
    assert all(repos.files.list_user_files(user_id, b) == [] for b in BUCKETS)
    assert repos.profiles.get_profile(user_id) is None
    assert repos.sessions.list_sessions(user_id, 10, None) == []
    assert (
        client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code
        == 401
    )
    assert client.get("/api/profile", headers=headers).status_code == 401  # tokens are gone


def _record_calls(monkeypatch, *, fail_bucket=None, fail_auth=False, fail_sessions=False):
    calls = []
    repos, auth = _repos(), _auth()
    real_folder, real_delete = repos.files.delete_user_folder, auth.delete_user
    real_sessions = repos.sessions.delete_user_sessions

    def delete_user_sessions(user_id):
        calls.append(("sessions", None))
        if fail_sessions:
            raise StorageError("down")
        return real_sessions(user_id)

    def delete_user_folder(user_id, bucket):
        calls.append(("storage", bucket))
        if bucket == fail_bucket:
            raise StorageError("down")
        real_folder(user_id, bucket)

    def delete_user(user_id):
        calls.append(("auth", None))
        if fail_auth:
            raise AuthUnavailableError("down")
        real_delete(user_id)

    monkeypatch.setattr(repos.files, "delete_user_folder", delete_user_folder)
    monkeypatch.setattr(auth, "delete_user", delete_user)
    monkeypatch.setattr(repos.sessions, "delete_user_sessions", delete_user_sessions)
    return calls


def test_wrong_password_deletes_nothing(client, monkeypatch):
    user_id, headers = _account(client)
    _seed(user_id)
    calls = _record_calls(monkeypatch)
    r = _delete(client, headers, "not-my-password")
    assert r.status_code == 403 and r.json()["error_code"] == "wrong_password"
    assert calls == []
    assert _repos().profiles.get_profile(user_id) is not None
    assert len(_repos().files.list_user_files(user_id, "audio")) == 1


def test_storage_is_emptied_in_all_buckets_before_the_account(client, monkeypatch):
    _, headers = _account(client)
    calls = _record_calls(monkeypatch)
    assert _delete(client, headers).status_code == 200
    assert calls == [("storage", b) for b in BUCKETS] + [("sessions", None), ("auth", None)]


def test_storage_error_keeps_account_and_rows(client, monkeypatch):
    user_id, headers = _account(client)
    _seed(user_id)
    calls = _record_calls(monkeypatch, fail_bucket="baselines")
    r = _delete(client, headers)
    assert r.status_code == 503 and r.json()["error_code"] == "storage_unavailable"
    assert ("auth", None) not in calls
    assert _repos().profiles.get_profile(user_id) is not None
    assert client.get("/api/profile", headers=headers).status_code == 200


def test_auth_error_after_files_is_503_and_retry_works(client, monkeypatch):
    user_id, headers = _account(client)
    _seed(user_id)
    _record_calls(monkeypatch, fail_auth=True)
    r = _delete(client, headers)
    assert r.status_code == 503 and r.json()["error_code"] == "auth_unavailable"
    assert _repos().files.list_user_files(user_id, "audio") == []
    assert _repos().profiles.get_profile(user_id) is not None
    monkeypatch.undo()
    assert _delete(client, headers).json() == {"deleted": True}  # retry is safe


def test_delete_account_requires_login(client):
    r = client.request("DELETE", "/api/auth/account", json={"password": PASSWORD})
    assert r.status_code == 401


def test_session_error_keeps_the_account(client, monkeypatch):
    user_id, headers = _account(client)
    _seed(user_id)
    calls = _record_calls(monkeypatch, fail_sessions=True)
    r = _delete(client, headers)
    assert r.status_code == 503 and r.json()["error_code"] == "storage_unavailable"
    assert ("auth", None) not in calls
    assert _repos().profiles.get_profile(user_id) is not None
    monkeypatch.undo()
    assert _delete(client, headers).json() == {"deleted": True}  # retry is safe
    assert _repos().sessions.list_sessions(user_id, 10, None) == []


def test_delete_account_cleans_the_users_shard(client):
    """ADR-012: a user whose sessions live in a shard project leaves nothing there."""
    repos = build_memory_repos(extra_shards=1)
    main.app.dependency_overrides[get_repos] = lambda: repos
    user_id, headers = _account(client)
    _seed(user_id)
    assert repos.accounts.get_shard(user_id) == "shard1"
    shard_sessions, shard_files = repos.sessions._shards["shard1"], repos.files._shards["shard1"]
    assert any(r.user_id == user_id for r in shard_sessions._state.sessions.values())
    assert shard_files.list_user_files(user_id, "audio") != []

    assert _delete(client, headers).json() == {"deleted": True}
    assert shard_sessions.delete_user_sessions(user_id) == 0  # nothing left to delete
    assert all(shard_files.list_user_files(user_id, b) == [] for b in ("audio", "series"))
    assert repos.files.list_user_files(user_id, "avatars") == []
    assert repos.accounts.get_shard(user_id) is None
