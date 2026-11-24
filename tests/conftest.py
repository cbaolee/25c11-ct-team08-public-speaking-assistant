"""Shared test setup.

Every test that is not marked `integration` runs as one logged-in test user, with fresh
in-memory repositories and accounts, and with the Supabase settings from `.env` blanked,
so unit tests never call Supabase and give the same result on every machine (T2).
A test can still set its own `app.dependency_overrides` (they replace
these), and tests of the real login remove the `get_current_user` override themselves.
Recording routes also skip the consent check; tests of that check remove the
`require_recording_consent` override.
"""

from typing import Annotated
from uuid import UUID

import pytest
from fastapi import Depends

from src.app.auth import MemoryAuthProvider, get_auth
from src.app.config import settings
from src.app.db.factory import (
    build_memory_repos,
    get_repos,
    get_shard_client,
    get_supabase_client,
)
from src.app.deps import CurrentUser, get_current_user, require_recording_consent
from src.app.main import app

TEST_OTP = "123456"
TEST_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


def reset_auth_limiters() -> None:
    """Empty the attempt counters of the in-memory repositories (resend cooldown etc.)."""
    app.dependency_overrides[get_repos]().rate_limits.reset()


def _skip_consent_check(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Whoever the test logs in (it may override `get_current_user`), without the consent check."""
    return user


@pytest.fixture(autouse=True)
def isolated_app(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        yield
        return
    # Code that calls get_repos()/get_auth() directly (not through FastAPI) must not see .env
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    monkeypatch.setattr(settings, "supabase_shards", {})
    for cached in (get_repos, get_auth, get_supabase_client, get_shard_client):
        cached.cache_clear()
    repos, auth = build_memory_repos(), MemoryAuthProvider(code_factory=lambda: TEST_OTP)
    app.dependency_overrides[get_repos] = lambda: repos
    app.dependency_overrides[get_auth] = lambda: auth
    test_user = CurrentUser(id=TEST_USER_ID, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[require_recording_consent] = _skip_consent_check
    yield
    app.dependency_overrides.clear()
    for cached in (get_repos, get_auth, get_supabase_client, get_shard_client):
        cached.cache_clear()
