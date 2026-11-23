from typing import Any, Protocol
from uuid import UUID

from src.app.db.models import (
    BaselineRow,
    NewBaseline,
    NewScript,
    NewSession,
    ProfilePatch,
    ProfileRow,
    ProfileUpsert,
    ScorePoint,
    ScriptPatch,
    ScriptRow,
    ScriptSummary,
    SessionRow,
    SessionSummary,
)


class ProfileRepo(Protocol):
    def get_profile(self, user_id: UUID) -> ProfileRow | None: ...

    def upsert_profile(self, user_id: UUID, data: ProfileUpsert) -> ProfileRow: ...

    def update_profile(self, user_id: UUID, patch: ProfilePatch) -> ProfileRow | None: ...

    def set_consent(self, user_id: UUID, consent_recording: bool) -> ProfileRow | None: ...

    def set_avatar_path(self, user_id: UUID, avatar_path: str | None) -> ProfileRow | None: ...

    def merge_preferences(self, user_id: UUID, patch: dict[str, Any]) -> ProfileRow | None: ...

    def delete_profile(self, user_id: UUID) -> bool: ...


class BaselineRepo(Protocol):
    def get_current_baseline(self, user_id: UUID) -> BaselineRow | None: ...

    def replace_current_baseline(
        self, user_id: UUID, data: NewBaseline
    ) -> tuple[BaselineRow, BaselineRow | None]: ...


class ScriptRepo(Protocol):
    def create_script(self, user_id: UUID, data: NewScript) -> ScriptRow: ...

    def get_script(self, user_id: UUID, script_id: UUID) -> ScriptRow | None: ...

    def find_script_by_hash(self, user_id: UUID, content_hash: str) -> ScriptRow | None: ...

    def find_script_by_title(self, user_id: UUID, title: str) -> ScriptRow | None: ...

    def list_scripts(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[ScriptSummary]: ...

    def count_scripts(self, user_id: UUID) -> int: ...

    def update_script(
        self, user_id: UUID, script_id: UUID, patch: ScriptPatch
    ) -> ScriptRow | None: ...

    def delete_script(self, user_id: UUID, script_id: UUID) -> bool: ...


class SessionRepo(Protocol):
    def create_session(self, user_id: UUID, data: NewSession) -> SessionRow: ...

    def get_session(self, user_id: UUID, session_id: UUID) -> SessionRow | None: ...

    def list_sessions(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[SessionSummary]: ...

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]: ...

    def list_full_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]: ...

    def list_compact_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]: ...

    def save_compact_session(
        self,
        user_id: UUID,
        session_id: UUID,
        summary: dict,
        mistakes: list[dict],
    ) -> bool: ...

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool: ...

    # Every session row of the user, for deleting an account. Returns how many were deleted.
    def delete_user_sessions(self, user_id: UUID) -> int: ...


# Which shard project holds a user's sessions and session files (core project, ADR-012).
class AccountRepo(Protocol):
    # Shard ref: "core" or a shard project's ref (config.ShardProject.ref).
    def get_shard(self, user_id: UUID) -> str | None: ...

    # Keeps the shard already stored for the user, so two first requests agree on one shard.
    def assign_shard(self, user_id: UUID, shard_ref: str) -> str: ...

    # Users per shard ref; shards with no user are missing from the dict.
    def count_by_shard(self) -> dict[str, int]: ...


class AudioStore(Protocol):
    def upload_file(
        self,
        user_id: UUID,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
    ) -> None: ...

    def download_file(self, user_id: UUID, bucket: str, path: str) -> bytes: ...

    def delete_files(self, user_id: UUID, bucket: str, paths: list[str]) -> None: ...

    def create_signed_url(self, user_id: UUID, bucket: str, path: str, ttl_s: int) -> str: ...

    # Every object under `{user_id}/` in the bucket (all pages), for deleting an account.
    def list_user_files(self, user_id: UUID, bucket: str) -> list[str]: ...

    # Delete every object under `{user_id}/`, then list again; StorageError unless it is empty.
    def delete_user_folder(self, user_id: UUID, bucket: str) -> None: ...
