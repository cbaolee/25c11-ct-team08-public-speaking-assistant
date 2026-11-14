from dataclasses import dataclass
from functools import lru_cache

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
def get_repos() -> Repos:
    if settings.app_env == "dev":
        return build_memory_repos()
    raise StorageError("Persistent repositories are not configured")
