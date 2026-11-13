from typing import Protocol
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

    def list_scripts(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[ScriptSummary]: ...

    def delete_script(self, user_id: UUID, script_id: UUID) -> bool: ...


class SessionRepo(Protocol):
    def create_session(self, user_id: UUID, data: NewSession) -> SessionRow: ...

    def get_session(self, user_id: UUID, session_id: UUID) -> SessionRow | None: ...

    def list_sessions(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[SessionSummary]: ...

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]: ...

    def list_full_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]: ...

    def save_compact_session(
        self,
        user_id: UUID,
        session_id: UUID,
        summary: dict,
        mistakes: list[dict],
    ) -> bool: ...

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool: ...


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

    def create_signed_url(
        self, user_id: UUID, bucket: str, path: str, ttl_s: int
    ) -> str: ...
