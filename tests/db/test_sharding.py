"""Sessions and session files go to the user's shard; the rest stays in the core (ADR-012)."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.app.db import factory
from src.app.db.factory import build_memory_repos
from src.app.db.memory import MemoryAccountRepo, MemoryState
from src.app.db.models import NewSession, build_avatar_path, build_object_path
from src.app.db.sharding import ShardRouter


def _session() -> NewSession:
    return NewSession(
        id=uuid4(), script_snapshot="hi", status="ok", result={}, result_schema_version="2.0"
    )


def _shard_sessions(repos, shard_ref):
    return repos.sessions._shards[shard_ref]


def test_new_users_fill_the_least_used_shard_first():
    repos = build_memory_repos(extra_shards=2)  # core, shard1, shard2
    users = [uuid4() for _ in range(4)]
    for user_id in users:
        repos.sessions.create_session(user_id, _session())
    # The core never gets new users while a shard project exists
    assert [repos.accounts.get_shard(u) for u in users] == ["shard1", "shard2", "shard1", "shard2"]


def test_old_core_users_stay_in_the_core():
    repos = build_memory_repos(extra_shards=1)
    user_id = uuid4()
    repos.accounts.assign_shard(user_id, "core")  # a user from before the shards
    session = repos.sessions.create_session(user_id, _session())
    assert repos.accounts.get_shard(user_id) == "core"
    assert _shard_sessions(repos, "core").get_session(user_id, session.id) is not None


def test_session_and_its_files_live_in_the_users_shard():
    repos = build_memory_repos(extra_shards=1)
    user_id = uuid4()
    session = repos.sessions.create_session(user_id, _session())
    audio = build_object_path(user_id, session.id, ".webm")
    repos.files.upload_file(user_id, "audio", audio, b"a", "audio/webm")
    repos.files.upload_file(user_id, "avatars", build_avatar_path(user_id), b"p", "image/webp")

    assert repos.accounts.get_shard(user_id) == "shard1"
    assert _shard_sessions(repos, "shard1").get_session(user_id, session.id) is not None
    assert _shard_sessions(repos, "core").get_session(user_id, session.id) is None
    assert repos.sessions.get_session(user_id, session.id) is not None
    assert repos.files._shards["shard1"].list_user_files(user_id, "audio") == [audio]
    assert repos.files._shards["core"].list_user_files(user_id, "audio") == []
    assert repos.files._shards["core"].list_user_files(user_id, "avatars") == [
        build_avatar_path(user_id)
    ]
    assert repos.files.download_file(user_id, "audio", audio) == b"a"


def test_reads_do_not_give_a_shard():
    repos = build_memory_repos(extra_shards=1)
    user_id = uuid4()
    assert repos.sessions.list_sessions(user_id, 10, None) == []
    assert repos.files.list_user_files(user_id, "audio") == []
    assert repos.accounts.get_shard(user_id) is None


def test_core_only_setup_puts_everyone_in_the_core():
    repos = build_memory_repos()
    user_id = uuid4()
    repos.sessions.create_session(user_id, _session())
    assert repos.accounts.get_shard(user_id) == "core"


def test_router_caches_the_shard():
    accounts = MagicMock(wraps=MemoryAccountRepo(MemoryState()))
    router = ShardRouter(accounts, ["core", "aaaa"])
    user_id = uuid4()
    first = router.shard_for(user_id, assign=True)
    assert router.shard_for(user_id, assign=False) == first
    assert accounts.get_shard.call_count == 1


def test_router_needs_the_core_shard():
    with pytest.raises(ValueError):
        ShardRouter(MemoryAccountRepo(MemoryState()), ["aaaa", "bbbb"])


def test_stored_shard_that_is_not_configured_fails_loudly():
    repos = build_memory_repos()
    user_id = uuid4()
    repos.accounts.assign_shard(user_id, "gone")  # project removed from SUPABASE_SHARDS
    with pytest.raises(RuntimeError, match="Shard gone"):
        repos.sessions.list_sessions(user_id, 10, None)


def test_supabase_repos_get_one_client_per_shard(monkeypatch):
    from src.app.config import parse_shards

    made = []
    monkeypatch.setattr(factory, "get_supabase_client", lambda: "core-client")
    monkeypatch.setattr(
        factory, "create_client", lambda url, key: made.append((url, key)) or f"client:{url}"
    )
    monkeypatch.setattr(
        factory.settings, "supabase_shards", parse_shards({"https://aaaa.supabase.co": "k"})
    )
    factory.get_shard_client.cache_clear()
    try:
        repos = factory.build_supabase_repos()
    finally:
        factory.get_shard_client.cache_clear()
    assert list(repos.sessions._shards) == ["core", "aaaa"]
    assert repos.sessions._shards["core"]._client == "core-client"
    assert repos.sessions._shards["aaaa"]._client == "client:https://aaaa.supabase.co"
    assert made == [("https://aaaa.supabase.co", "k")]


def test_ties_follow_the_env_order():
    accounts = MemoryAccountRepo(MemoryState())
    router = ShardRouter(accounts, ["core", "zzzz", "aaaa"])
    picks = [router.shard_for(uuid4(), assign=True) for _ in range(3)]
    assert picks == ["zzzz", "aaaa", "zzzz"]
