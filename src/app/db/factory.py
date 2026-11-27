from dataclasses import dataclass
from functools import cache, lru_cache

from supabase import Client, create_client

from src.app.config import settings
from src.app.db.memory import (
    MemoryAccountRepo,
    MemoryAudioStore,
    MemoryBaselineRepo,
    MemoryProfileRepo,
    MemoryRateLimitRepo,
    MemoryScriptRepo,
    MemorySessionRepo,
    MemoryState,
)
from src.app.db.models import StorageError
from src.app.db.repositories import (
    AccountRepo,
    AudioStore,
    BaselineRepo,
    ProfileRepo,
    RateLimitRepo,
    ScriptRepo,
    SessionRepo,
)
from src.app.db.sharding import CORE_SHARD, ShardedAudioStore, ShardedSessionRepo, ShardRouter
from src.app.db.supabase_repo import (
    SupabaseAccountRepo,
    SupabaseAudioStore,
    SupabaseBaselineRepo,
    SupabaseProfileRepo,
    SupabaseRateLimitRepo,
    SupabaseScriptRepo,
    SupabaseSessionRepo,
)


def _session_buckets() -> set[str]:
    return {settings.audio_bucket, settings.series_bucket}


def _sharded(
    accounts: AccountRepo,
    sessions: dict[str, SessionRepo],
    files: dict[str, AudioStore],
) -> tuple[SessionRepo, AudioStore]:
    router = ShardRouter(accounts, list(sessions))
    return (
        ShardedSessionRepo(router, sessions),
        ShardedAudioStore(router, files, _session_buckets),
    )


@dataclass(frozen=True)
class Repos:
    profiles: ProfileRepo
    baselines: BaselineRepo
    scripts: ScriptRepo
    sessions: SessionRepo
    files: AudioStore
    accounts: AccountRepo
    rate_limits: RateLimitRepo


def build_memory_repos(extra_shards: int = 0) -> Repos:
    """In-memory repositories. `extra_shards` adds shards "shard1", "shard2"... (ADR-012 tests)."""
    core = MemoryState()
    shard_states = {CORE_SHARD: core} | {
        f"shard{n}": MemoryState() for n in range(1, 1 + extra_shards)
    }
    accounts = MemoryAccountRepo(core)
    sessions, files = _sharded(
        accounts,
        {n: MemorySessionRepo(s) for n, s in shard_states.items()},
        {n: MemoryAudioStore(s) for n, s in shard_states.items()},
    )
    return Repos(
        profiles=MemoryProfileRepo(core),
        baselines=MemoryBaselineRepo(core),
        scripts=MemoryScriptRepo(core),
        sessions=sessions,
        files=files,
        accounts=accounts,
        rate_limits=MemoryRateLimitRepo(core),
    )


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Create the Supabase client once, on first use (never at import time)."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise StorageError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_service_key)


@cache
def get_shard_client(shard_ref: str) -> Client:
    """Client of one shard project from SUPABASE_SHARDS; "core" is the core client."""
    if shard_ref == CORE_SHARD:
        return get_supabase_client()
    shard = settings.supabase_shards.get(shard_ref)
    if shard is None:
        raise StorageError(f"Shard {shard_ref} is not in SUPABASE_SHARDS")
    return create_client(shard.url, shard.service_key)


def build_supabase_repos() -> Repos:
    client = get_supabase_client()
    accounts = SupabaseAccountRepo(client)
    refs = [CORE_SHARD, *settings.supabase_shards]  # .env order breaks ties
    sessions, files = _sharded(
        accounts,
        {n: SupabaseSessionRepo(get_shard_client(n)) for n in refs},
        {n: SupabaseAudioStore(get_shard_client(n)) for n in refs},
    )
    return Repos(
        profiles=SupabaseProfileRepo(client),
        baselines=SupabaseBaselineRepo(client),
        scripts=SupabaseScriptRepo(client),
        sessions=sessions,
        files=files,
        accounts=accounts,
        rate_limits=SupabaseRateLimitRepo(client),
    )


@lru_cache(maxsize=1)
def get_repos() -> Repos:
    if settings.supabase_url:
        return build_supabase_repos()
    if settings.app_env == "dev":
        return build_memory_repos()
    raise StorageError("Persistent repositories are not configured")
