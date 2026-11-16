from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID, uuid4

from src.app.db.models import (
    BaselineRow,
    ConflictError,
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
    StorageError,
    build_object_path,
    decode_cursor,
)


@dataclass
class MemoryState:
    profiles: dict[UUID, ProfileRow] = field(default_factory=dict)
    baselines: dict[UUID, list[BaselineRow]] = field(default_factory=dict)
    scripts: dict[UUID, ScriptRow] = field(default_factory=dict)
    sessions: dict[UUID, SessionRow] = field(default_factory=dict)
    files: dict[tuple[str, str], bytes] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")


def _newest_first(rows):
    return sorted(rows, key=lambda row: (row.created_at, str(row.id)), reverse=True)


def _after_cursor(rows, cursor: str | None):
    if cursor is None:
        return rows
    cursor_created_at, cursor_id = decode_cursor(cursor)
    cursor_key = (cursor_created_at, str(cursor_id))
    return [
        row
        for row in rows
        if (row.created_at, str(row.id)) < cursor_key
    ]


class MemoryProfileRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def get_profile(self, user_id: UUID) -> ProfileRow | None:
        row = self._state.profiles.get(user_id)
        return row.model_copy(deep=True) if row is not None else None

    def upsert_profile(self, user_id: UUID, data: ProfileUpsert) -> ProfileRow:
        existing = self._state.profiles.get(user_id)
        values = data.model_dump()
        if existing is None:
            row = ProfileRow(
                id=user_id,
                consent_recording=False,
                consent_updated_at=None,
                created_at=_now(),
                **values,
            )
        else:
            row = ProfileRow.model_validate({**existing.model_dump(), **values})
        self._state.profiles[user_id] = row.model_copy(deep=True)
        return row.model_copy(deep=True)

    def update_profile(self, user_id: UUID, patch: ProfilePatch) -> ProfileRow | None:
        existing = self._state.profiles.get(user_id)
        if existing is None:
            return None
        row = ProfileRow.model_validate(
            {**existing.model_dump(), **patch.model_dump(exclude_unset=True)}
        )
        self._state.profiles[user_id] = row.model_copy(deep=True)
        return row.model_copy(deep=True)

    def set_consent(self, user_id: UUID, consent_recording: bool) -> ProfileRow | None:
        existing = self._state.profiles.get(user_id)
        if existing is None:
            return None
        row = existing.model_copy(
            update={
                "consent_recording": consent_recording,
                "consent_updated_at": _now(),
            },
            deep=True,
        )
        self._state.profiles[user_id] = row
        return row.model_copy(deep=True)

    def delete_profile(self, user_id: UUID) -> bool:
        if user_id not in self._state.profiles:
            return False
        del self._state.profiles[user_id]
        self._state.baselines.pop(user_id, None)

        script_ids = {
            script_id
            for script_id, row in self._state.scripts.items()
            if row.user_id == user_id
        }
        for script_id in script_ids:
            del self._state.scripts[script_id]

        for session_id, row in list(self._state.sessions.items()):
            if row.user_id == user_id:
                del self._state.sessions[session_id]
        return True


class MemoryBaselineRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def get_current_baseline(self, user_id: UUID) -> BaselineRow | None:
        current = next(
            (
                row
                for row in self._state.baselines.get(user_id, [])
                if row.is_current
            ),
            None,
        )
        return current.model_copy(deep=True) if current is not None else None

    def replace_current_baseline(
        self, user_id: UUID, data: NewBaseline
    ) -> tuple[BaselineRow, BaselineRow | None]:
        if any(row.id == data.id for rows in self._state.baselines.values() for row in rows):
            raise ConflictError(f"Baseline already exists: {data.id}")
        existing_rows = self._state.baselines.get(user_id, [])
        previous = next((row for row in existing_rows if row.is_current), None)
        new_row = BaselineRow(
            user_id=user_id,
            is_current=True,
            recorded_at=_now(),
            **data.model_dump(),
        )
        updated_rows = [
            row.model_copy(update={"is_current": False}, deep=True)
            if row.is_current
            else row.model_copy(deep=True)
            for row in existing_rows
        ]
        updated_rows.append(new_row.model_copy(deep=True))
        self._state.baselines[user_id] = updated_rows
        return (
            new_row.model_copy(deep=True),
            previous.model_copy(deep=True) if previous is not None else None,
        )


class MemoryScriptRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def create_script(self, user_id: UUID, data: NewScript) -> ScriptRow:
        row = ScriptRow(
            id=uuid4(),
            user_id=user_id,
            created_at=_now(),
            **data.model_dump(),
        )
        self._state.scripts[row.id] = row.model_copy(deep=True)
        return row.model_copy(deep=True)

    def get_script(self, user_id: UUID, script_id: UUID) -> ScriptRow | None:
        row = self._state.scripts.get(script_id)
        if row is None or row.user_id != user_id:
            return None
        return row.model_copy(deep=True)

    def find_script_by_hash(
        self, user_id: UUID, content_hash: str
    ) -> ScriptRow | None:
        matches = _newest_first(
            row
            for row in self._state.scripts.values()
            if row.user_id == user_id and row.content_hash == content_hash
        )
        return matches[0].model_copy(deep=True) if matches else None

    def list_scripts(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[ScriptSummary]:
        _validate_limit(limit)
        rows = _newest_first(
            row for row in self._state.scripts.values() if row.user_id == user_id
        )
        rows = _after_cursor(rows, cursor)
        return [
            ScriptSummary.model_validate(row.model_dump())
            for row in rows[:limit]
        ]

    def delete_script(self, user_id: UUID, script_id: UUID) -> bool:
        row = self._state.scripts.get(script_id)
        if row is None or row.user_id != user_id:
            return False
        del self._state.scripts[script_id]
        for session_id, session in list(self._state.sessions.items()):
            if session.user_id == user_id and session.script_id == script_id:
                self._state.sessions[session_id] = session.model_copy(
                    update={"script_id": None}, deep=True
                )
        return True


class MemorySessionRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def create_session(self, user_id: UUID, data: NewSession) -> SessionRow:
        if data.id in self._state.sessions:
            raise ConflictError(f"Session already exists: {data.id}")
        row = SessionRow(
            **data.model_dump(),
            user_id=user_id,
            is_compact=False,
            mistakes=None,
            created_at=_now(),
        )
        self._state.sessions[row.id] = row.model_copy(deep=True)
        return row.model_copy(deep=True)

    def get_session(self, user_id: UUID, session_id: UUID) -> SessionRow | None:
        row = self._state.sessions.get(session_id)
        if row is None or row.user_id != user_id:
            return None
        return row.model_copy(deep=True)

    def list_sessions(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[SessionSummary]:
        _validate_limit(limit)
        rows = _newest_first(
            row for row in self._state.sessions.values() if row.user_id == user_id
        )
        rows = _after_cursor(rows, cursor)
        return [
            SessionSummary.model_validate(row.model_dump())
            for row in rows[:limit]
        ]

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]:
        _validate_limit(limit)
        rows = sorted(
            (row for row in self._state.sessions.values() if row.user_id == user_id),
            key=lambda row: (row.created_at, str(row.id)),
        )
        rows = rows[-limit:]
        return [
            ScorePoint(
                session_id=row.id,
                created_at=row.created_at,
                overall=row.overall,
            )
            for row in rows
        ]

    def list_full_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]:
        if keep < 0:
            raise ValueError("keep must be non-negative")
        rows = _newest_first(
            row
            for row in self._state.sessions.values()
            if row.user_id == user_id and not row.is_compact
        )
        return [row.model_copy(deep=True) for row in rows[keep:]]

    def save_compact_session(
        self,
        user_id: UUID,
        session_id: UUID,
        summary: dict,
        mistakes: list[dict],
    ) -> bool:
        row = self._state.sessions.get(session_id)
        if row is None or row.user_id != user_id or row.is_compact:
            return False
        compacted = row.model_copy(
            update={
                "result": summary,
                "mistakes": mistakes,
                "is_compact": True,
                "audio_path": None,
                "series_path": None,
            },
            deep=True,
        )
        self._state.sessions[session_id] = compacted
        return True

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool:
        row = self._state.sessions.get(session_id)
        if row is None or row.user_id != user_id:
            return False
        del self._state.sessions[session_id]
        return True


class MemoryAudioStore:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    @staticmethod
    def _validate_path(user_id: UUID, path: str) -> None:
        prefix = f"{user_id}/"
        if not isinstance(path, str) or not path.startswith(prefix) or "\\" in path:
            raise StorageError("Object path must be scoped to the current user")
        for suffix in (".series.json", ".webm"):
            object_id = path[len(prefix) : -len(suffix)] if path.endswith(suffix) else ""
            try:
                if build_object_path(user_id, UUID(object_id), suffix) == path:
                    return
            except ValueError:
                continue
        raise StorageError("Object path must be created with build_object_path")

    def upload_file(
        self,
        user_id: UUID,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
    ) -> None:
        self._validate_path(user_id, path)
        if not bucket or not content_type:
            raise ValueError("bucket and content_type are required")
        key = (bucket, path)
        if key in self._state.files and not upsert:
            raise ConflictError(f"Object already exists: {bucket}/{path}")
        self._state.files[key] = bytes(content)

    def download_file(self, user_id: UUID, bucket: str, path: str) -> bytes:
        self._validate_path(user_id, path)
        try:
            return bytes(self._state.files[(bucket, path)])
        except KeyError as err:
            raise StorageError(f"Object not found: {bucket}/{path}") from err

    def delete_files(self, user_id: UUID, bucket: str, paths: list[str]) -> None:
        for path in paths:
            self._validate_path(user_id, path)
        for path in paths:
            self._state.files.pop((bucket, path), None)

    def create_signed_url(
        self, user_id: UUID, bucket: str, path: str, ttl_s: int
    ) -> str:
        self._validate_path(user_id, path)
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        if (bucket, path) not in self._state.files:
            raise StorageError(f"Object not found: {bucket}/{path}")
        return f"memory://{quote(bucket, safe='')}/{quote(path, safe='/')}?ttl={ttl_s}"
