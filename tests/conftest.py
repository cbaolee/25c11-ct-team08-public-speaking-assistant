"""Shared test setup.

Every test that is not marked `integration` runs as one logged-in test user, with fresh
in-memory repositories and accounts, and with the Supabase settings from `.env` blanked,
so unit tests never call Supabase and give the same result on every machine (T2).
A test can still set its own `app.dependency_overrides` (they replace
these), and tests of the real login remove the `get_current_user` override themselves.
"""

from uuid import UUID

import pytest

from src.app.auth import MemoryAuthProvider, get_auth
from src.app.config import settings
from src.app.db.factory import build_memory_repos, get_repos, get_supabase_client
from src.app.deps import CurrentUser, get_current_user
from src.app.main import app
from src.app.routes.auth import reset_auth_limiters

TEST_OTP = "123456"
TEST_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture(autouse=True)
def isolated_app(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        yield
        return
    # Code that calls get_repos()/get_auth() directly (not through FastAPI) must not see .env
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")
    for cached in (get_repos, get_auth, get_supabase_client):
        cached.cache_clear()
    reset_auth_limiters()
    repos, auth = build_memory_repos(), MemoryAuthProvider(code_factory=lambda: TEST_OTP)
    app.dependency_overrides[get_repos] = lambda: repos
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=TEST_USER_ID, email="test@example.com"
    )
    yield
    app.dependency_overrides.clear()
    for cached in (get_repos, get_auth, get_supabase_client):
        cached.cache_clear()
