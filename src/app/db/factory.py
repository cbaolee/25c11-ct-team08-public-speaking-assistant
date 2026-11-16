from dataclasses import dataclass
from functools import lru_cache

from supabase import Client, create_client

from src.app.config import settings
from src.app.db.memory import (
    MemoryAudioStore,
    MemoryBaselineRepo,
    MemoryProfileRepo,
    MemoryScriptRepo,
    MemorySessionRepo,
    MemoryState,
)
from src.app.db.models import StorageError
from src.app.db.repositories import (
    AudioStore,
    BaselineRepo,
    ProfileRepo,
    ScriptRepo,
    SessionRepo,
)
from src.app.db.supabase_repo import (
    SupabaseAudioStore,
    SupabaseBaselineRepo,
    SupabaseProfileRepo,
    SupabaseScriptRepo,
    SupabaseSessionRepo,
)


@dataclass(frozen=True)
class Repos:
    profiles: ProfileRepo
    baselines: BaselineRepo
    scripts: ScriptRepo
    sessions: SessionRepo
    files: AudioStore


def build_memory_repos() -> Repos:
    state = MemoryState()
    return Repos(
        profiles=MemoryProfileRepo(state),
        baselines=MemoryBaselineRepo(state),
        scripts=MemoryScriptRepo(state),
        sessions=MemorySessionRepo(state),
        files=MemoryAudioStore(state),
    )


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Create the Supabase client once, on first use (never at import time)."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise StorageError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_service_key)


def build_supabase_repos() -> Repos:
    client = get_supabase_client()
    return Repos(
        profiles=SupabaseProfileRepo(client),
        baselines=SupabaseBaselineRepo(client),
        scripts=SupabaseScriptRepo(client),
        sessions=SupabaseSessionRepo(client),
        files=SupabaseAudioStore(client),
    )


@lru_cache(maxsize=1)
def get_repos() -> Repos:
    if settings.supabase_url:
        return build_supabase_repos()
    if settings.app_env == "dev":
        return build_memory_repos()
    raise StorageError("Persistent repositories are not configured")
