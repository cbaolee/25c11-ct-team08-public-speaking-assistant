"""Send each user's sessions and session files to the project that holds them (ADR-012).

The core project keeps auth, accounts, profiles, baselines, scripts and the avatars,
baselines buckets. Sessions and the audio, series buckets of a user live in one project:
the core (shard ref "core") or a shard project (its project ref), written in
`accounts.shard_ref`. Routes keep calling `repos.sessions` and `repos.files` with `user_id`
as before; the classes below pick the project.
"""

from collections.abc import Callable, Mapping
from threading import Lock
from uuid import UUID

from src.app.config import CORE_SHARD_REF as CORE_SHARD
from src.app.db.models import NewSession, ScorePoint, SessionRow, SessionSummary
from src.app.db.repositories import AccountRepo, AudioStore, SessionRepo


class ShardRouter:
    """user_id -> shard ref, read from `accounts` and kept in RAM (it never changes).

    A user without an account row gets one the first time a write needs a shard: the shard
    project with the fewest users (ties: SUPABASE_SHARDS order). The core never gets new
    users while a shard project exists: it already holds every user's profile, baseline and
    scripts. With no shard project configured (dev, tests) everything stays in the core.
    Users already stored as "core" keep their sessions there. Reads do not create a row: a
    user without one has no sessions yet, so the core project (empty for them) is used.
    """

    def __init__(self, accounts: AccountRepo, shard_refs: list[str]) -> None:
        if CORE_SHARD not in shard_refs:
            raise ValueError("The core project must be one of the shards")
        self._accounts = accounts
        self._shard_refs = list(dict.fromkeys(shard_refs))  # keep order, drop repeats
        self._cache: dict[UUID, str] = {}
        self._lock = Lock()  # one new user at a time, so two sign ups see fresh counts

    def shard_for(self, user_id: UUID, *, assign: bool) -> str:
        cached = self._cache.get(user_id)
        if cached is not None:
            return cached
        shard_ref = self._accounts.get_shard(user_id)
        if shard_ref is None:
            if not assign:
                return CORE_SHARD
            with self._lock:
                shard_ref = self._accounts.assign_shard(user_id, self._least_used())
        self._cache[user_id] = shard_ref
        return shard_ref

    def _least_used(self) -> str:
        candidates = [ref for ref in self._shard_refs if ref != CORE_SHARD] or [CORE_SHARD]
        counts = self._accounts.count_by_shard()
        order = {ref: i for i, ref in enumerate(candidates)}
        return min(candidates, key=lambda ref: (counts.get(ref, 0), order[ref]))


class ShardedSessionRepo:
    """SessionRepo that forwards every call to the user's shard."""

    def __init__(self, router: ShardRouter, shards: Mapping[str, SessionRepo]) -> None:
        self._router = router
        self._shards = shards

    def _repo(self, user_id: UUID, *, assign: bool = False) -> SessionRepo:
        shard_ref = self._router.shard_for(user_id, assign=assign)
        repo = self._shards.get(shard_ref)
        if repo is None:
            raise RuntimeError(f"Shard {shard_ref} is not configured (SUPABASE_SHARDS)")
        return repo

    def create_session(self, user_id: UUID, data: NewSession) -> SessionRow:
        return self._repo(user_id, assign=True).create_session(user_id, data)

    def get_session(self, user_id: UUID, session_id: UUID) -> SessionRow | None:
        return self._repo(user_id).get_session(user_id, session_id)

    def list_sessions(self, user_id: UUID, limit: int, cursor: str | None) -> list[SessionSummary]:
        return self._repo(user_id).list_sessions(user_id, limit, cursor)

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]:
        return self._repo(user_id).list_score_history(user_id, limit)

    def list_full_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]:
        return self._repo(user_id).list_full_beyond(user_id, keep)

    def list_compact_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]:
        return self._repo(user_id).list_compact_beyond(user_id, keep)

    def save_compact_session(
        self, user_id: UUID, session_id: UUID, summary: dict, mistakes: list[dict]
    ) -> bool:
        return self._repo(user_id).save_compact_session(user_id, session_id, summary, mistakes)

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool:
        return self._repo(user_id).delete_session(user_id, session_id)

    def delete_user_sessions(self, user_id: UUID) -> int:
        return self._repo(user_id).delete_user_sessions(user_id)


class ShardedAudioStore:
    """AudioStore that sends the session buckets to the user's shard, the rest to the core."""

    def __init__(
        self,
        router: ShardRouter,
        shards: Mapping[str, AudioStore],
        session_buckets: Callable[[], set[str]],
    ) -> None:
        self._router = router
        self._shards = shards
        self._session_buckets = session_buckets  # read late, so tests can change the names

    def _store(self, user_id: UUID, bucket: str, *, assign: bool = False) -> AudioStore:
        if bucket not in self._session_buckets():
            return self._shards[CORE_SHARD]
        shard_ref = self._router.shard_for(user_id, assign=assign)
        store = self._shards.get(shard_ref)
        if store is None:
            raise RuntimeError(f"Shard {shard_ref} is not configured (SUPABASE_SHARDS)")
        return store

    def upload_file(
        self,
        user_id: UUID,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
    ) -> None:
        store = self._store(user_id, bucket, assign=True)
        store.upload_file(user_id, bucket, path, content, content_type, upsert)

    def download_file(self, user_id: UUID, bucket: str, path: str) -> bytes:
        return self._store(user_id, bucket).download_file(user_id, bucket, path)

    def delete_files(self, user_id: UUID, bucket: str, paths: list[str]) -> None:
        self._store(user_id, bucket).delete_files(user_id, bucket, paths)

    def create_signed_url(self, user_id: UUID, bucket: str, path: str, ttl_s: int) -> str:
        return self._store(user_id, bucket).create_signed_url(user_id, bucket, path, ttl_s)

    def list_user_files(self, user_id: UUID, bucket: str) -> list[str]:
        return self._store(user_id, bucket).list_user_files(user_id, bucket)

    def delete_user_folder(self, user_id: UUID, bucket: str) -> None:
        self._store(user_id, bucket).delete_user_folder(user_id, bucket)
