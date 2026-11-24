"""Attempt counters of the account endpoints (public.auth_rate_limits, migration 0011).

Offline tests cover the in-memory repository, the Supabase repository with a fake client and
the routes' fail-open rule. Tests marked `integration` call hit_rate_limit() on the real psc-main
project (skipped by default; run with `uv run pytest -m integration` after running 0011).
"""

import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.app.config import settings
from src.app.db import factory
from src.app.db.memory import MemoryRateLimitRepo, MemoryState
from src.app.db.models import StorageError
from src.app.db.supabase_repo import SupabaseRateLimitRepo
from src.app.main import app

KEY = hashlib.sha256(b"ana@example.com").hexdigest()


# ---------- in-memory repository ----------


def _memory(now: list[float]) -> MemoryRateLimitRepo:
    return MemoryRateLimitRepo(MemoryState(), clock=lambda: now[0])


def test_memory_allows_max_hits_per_window_then_blocks():
    now = [0.0]
    repo = _memory(now)
    assert [repo.hit("signup_verify", KEY, 3, 600) for _ in range(4)] == [True, True, True, False]
    now[0] = 599
    assert repo.hit("signup_verify", KEY, 3, 600) is False


def test_memory_opens_again_when_the_window_ends():
    now = [0.0]
    repo = _memory(now)
    for _ in range(4):
        repo.hit("signup_verify", KEY, 3, 600)
    now[0] = 600
    assert repo.hit("signup_verify", KEY, 3, 600) is True  # a new window starts


def test_memory_buckets_and_keys_are_counted_apart():
    repo = _memory([0.0])
    assert repo.hit("reset_send", KEY, 1, 60) is True
    assert repo.hit("reset_send", KEY, 1, 60) is False
    assert repo.hit("signup_resend", KEY, 1, 60) is True
    assert repo.hit("reset_send", "0" * 64, 1, 60) is True


def test_memory_reset_empties_every_counter():
    repo = _memory([0.0])
    repo.hit("reset_send", KEY, 1, 60)
    repo.reset()
    assert repo.hit("reset_send", KEY, 1, 60) is True


# ---------- Supabase repository, fake client ----------


@pytest.mark.parametrize("data", [True, [True], [{"hit_rate_limit": True}]])
def test_supabase_hit_reads_the_rpc_answer(data):
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = data
    assert SupabaseRateLimitRepo(client).hit("reauth", KEY, 5, 600) is True
    client.rpc.assert_called_once_with(
        "hit_rate_limit", {"p_bucket": "reauth", "p_key": KEY, "p_max": 5, "p_window_s": 600}
    )


@pytest.mark.parametrize("data", [None, [], "yes"])
def test_supabase_hit_without_an_answer_raises(data):
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = data
    with pytest.raises(StorageError):
        SupabaseRateLimitRepo(client).hit("reauth", KEY, 5, 600)


# ---------- routes: the counter is down ----------


def test_routes_let_attempts_through_when_the_counter_is_down(monkeypatch, caplog):
    repos = app.dependency_overrides[factory.get_repos]()

    def down(*_args):
        raise StorageError("down")

    monkeypatch.setattr(repos.rate_limits, "hit", down)
    client = TestClient(app)
    for _ in range(3):  # normally the second one is 429 (resend cooldown)
        response = client.post("/api/auth/forgot-password", json={"email": "ana@example.com"})
        assert response.status_code == 200
    assert "Rate limit counter unavailable" in caplog.text


# ---------- real psc-main ----------


@pytest.fixture
def live_repo():
    if not (settings.supabase_url and settings.supabase_service_key):
        pytest.skip("SUPABASE_URL and SUPABASE_SERVICE_KEY are missing")
    factory.get_supabase_client.cache_clear()
    client = factory.get_supabase_client()
    key = secrets.token_hex(32)  # a fresh key: never collides with a real user's counter
    yield SupabaseRateLimitRepo(client), key
    client.table("auth_rate_limits").delete().eq("key", key).execute()


@pytest.mark.integration
def test_live_hit_rate_limit_counts_up_to_max(live_repo):
    repo, key = live_repo
    assert [repo.hit("test_bucket", key, 2, 600) for _ in range(3)] == [True, True, False]


@pytest.mark.integration
def test_live_parallel_hits_never_exceed_max(live_repo):
    repo, key = live_repo
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(lambda _: repo.hit("test_bucket", key, 3, 600), range(12)))
    assert answers.count(True) == 3
