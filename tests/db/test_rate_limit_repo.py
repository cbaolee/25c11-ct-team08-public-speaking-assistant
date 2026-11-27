"""Attempt counters of the account endpoints (public.auth_rate_limits, migration 0011).

Offline tests cover the in-memory repository, the Supabase repository with a fake client and
the routes' fail-open rule. Tests marked `integration` call hit_rate_limit() on the real psc-main
project (skipped by default; run with `uv run pytest -m integration` after running 0011).
"""

import hashlib
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
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


@pytest.mark.parametrize(("at_s", "left_s"), [(0, 600), (75, 525), (599.5, 1), (600, 1)])
def test_memory_retry_after_counts_down_to_the_window_end(at_s, left_s):
    now = [0.0]
    repo = _memory(now)
    repo.hit("reset_send", KEY, 1, 600)
    now[0] = at_s
    assert repo.retry_after_s("reset_send", KEY, 600) == left_s


def test_memory_retry_after_of_an_unknown_key_is_the_window_and_writes_nothing():
    state = MemoryState()
    repo = MemoryRateLimitRepo(state, clock=lambda: 0.0)
    assert repo.retry_after_s("reset_send", KEY, 600) == 600
    assert state.rate_limits == {}


def test_memory_refused_hit_does_not_change_the_wait():
    now = [0.0]
    repo = _memory(now)
    repo.hit("reset_send", KEY, 1, 600)
    now[0] = 75
    assert repo.hit("reset_send", KEY, 1, 600) is False
    assert repo.retry_after_s("reset_send", KEY, 600) == 525
    assert repo.retry_after_s("reset_send", KEY, 600) == 525  # reading counts nothing


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


NOW = datetime(2026, 11, 26, 10, 0, 0, tzinfo=UTC)


def _window_query(client: MagicMock) -> MagicMock:
    """The last step of select(...).eq(...).eq(...).limit(...) on the fake client."""
    select = client.table.return_value.select.return_value
    return select.eq.return_value.eq.return_value.limit.return_value


def _retry_after(rows: list) -> int:
    client = MagicMock()
    _window_query(client).execute.return_value.data = rows
    return SupabaseRateLimitRepo(client, now=lambda: NOW).retry_after_s("reauth", KEY, 600)


@pytest.mark.parametrize(
    "window_start",
    ["2026-11-26T09:58:45Z", "2026-11-26T09:58:45+00:00", "2026-11-26T09:58:45"],
)
def test_supabase_retry_after_adds_one_second_margin(window_start):
    assert _retry_after([{"window_start": window_start}]) == 526  # ceil(600 - 75) + 1


@pytest.mark.parametrize(
    "rows",
    [[], [{}], [{"window_start": None}], [{"window_start": "yesterday"}]],
)
def test_supabase_retry_after_without_a_readable_start_is_the_window(rows):
    assert _retry_after(rows) == 600


@pytest.mark.parametrize(
    ("window_start", "left_s"),
    [
        ("2026-11-26T10:05:00+00:00", 600),  # in the future: capped at the window
        ("2026-11-26T09:50:00+00:00", 1),  # just ended
        ("2026-11-25T10:00:00+00:00", 1),  # long ended: never below 1
    ],
)
def test_supabase_retry_after_stays_inside_the_window(window_start, left_s):
    assert _retry_after([{"window_start": window_start}]) == left_s


def test_supabase_retry_after_reads_only_the_row_of_the_bucket_and_key():
    client = MagicMock()
    _window_query(client).execute.return_value.data = []
    SupabaseRateLimitRepo(client).retry_after_s("reauth", KEY, 600)
    client.table.assert_called_once_with("auth_rate_limits")
    select = client.table.return_value.select
    select.assert_called_once_with("window_start")
    select.return_value.eq.assert_called_once_with("bucket", "reauth")
    select.return_value.eq.return_value.eq.assert_called_once_with("key", KEY)
    select.return_value.eq.return_value.eq.return_value.limit.assert_called_once_with(1)
    client.rpc.assert_not_called()


def test_supabase_retry_after_database_error_raises():
    client = MagicMock()
    _window_query(client).execute.side_effect = RuntimeError("down")
    with pytest.raises(StorageError):
        SupabaseRateLimitRepo(client).retry_after_s("reauth", KEY, 600)


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
