"""Shared test setup.

Every test that is not marked `integration` runs as one logged-in test user, with fresh
in-memory repositories and accounts, so unit tests never call Supabase even when `.env`
has SUPABASE_URL. A test can still set its own `app.dependency_overrides` (they replace
these), and tests of the real login remove the `get_current_user` override themselves.
"""

from uuid import UUID

import pytest

from src.app.auth import MemoryAuthProvider, get_auth
from src.app.db.factory import build_memory_repos, get_repos
from src.app.deps import CurrentUser, get_current_user
from src.app.main import app

TEST_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture(autouse=True)
def isolated_app(request):
    if request.node.get_closest_marker("integration"):
        yield
        return
    repos, auth = build_memory_repos(), MemoryAuthProvider()
    app.dependency_overrides[get_repos] = lambda: repos
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=TEST_USER_ID, email="test@example.com"
    )
    yield
    app.dependency_overrides.clear()
