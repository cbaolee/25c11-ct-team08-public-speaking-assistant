import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import RLock
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from src.app.config import max_list_page_size
from src.app.db.models import (
    BaselineRow,
    ConflictError,
    NewBaseline,
    NewScheduleEvent,
    NewScript,
    NewSession,
    ProfilePatch,
    ProfileRow,
    ProfileUpsert,
    ReminderStatus,
    ScheduleCheckinRow,
    ScheduleEventPatch,
    ScheduleEventRow,
    ScheduleReminderRow,
    ScorePoint,
    ScriptDuplicateBodyError,
    ScriptDuplicateTitleError,
    ScriptPatch,
    ScriptRow,
    ScriptSummary,
    SessionRow,
    SessionSummary,
    StorageError,
    build_avatar_path,
    build_object_path,
    decode_cursor,
    read_session_metric,
)


@dataclass
class MemoryState:
    profiles: dict[UUID, ProfileRow] = field(default_factory=dict)
    baselines: dict[UUID, list[BaselineRow]] = field(default_factory=dict)
    baselines_lock: RLock = field(default_factory=RLock)
    scripts: dict[UUID, ScriptRow] = field(default_factory=dict)
    scripts_lock: RLock = field(default_factory=RLock)
    sessions: dict[UUID, SessionRow] = field(default_factory=dict)
    files: dict[tuple[str, str], bytes] = field(default_factory=dict)
    accounts: dict[UUID, str] = field(default_factory=dict)  # user_id -> shard_ref
    accounts_lock: RLock = field(default_factory=RLock)
    # (bucket, key) -> (window start, hits), like public.auth_rate_limits
    rate_limits: dict[tuple[str, str], tuple[float, int]] = field(default_factory=dict)
    rate_limits_lock: RLock = field(default_factory=RLock)
    # Schedule (0012): one lock for the three dicts, so cascade, claim and split stay whole
    schedule_events: dict[UUID, ScheduleEventRow] = field(default_factory=dict)
    schedule_checkins: dict[tuple[UUID, date], ScheduleCheckinRow] = field(default_factory=dict)
    schedule_reminders: dict[tuple[UUID, date], ScheduleReminderRow] = field(default_factory=dict)
    schedule_lock: RLock = field(default_factory=RLock)


def _now() -> datetime:
    return datetime.now(UTC)


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= max_list_page_size:
        raise ValueError(f"limit must be between 1 and {max_list_page_size}")


def _newest_first(rows):
    return sorted(rows, key=lambda row: (row.created_at, str(row.id)), reverse=True)


def _after_cursor(rows, cursor: str | None):
    if cursor is None:
        return rows
    cursor_created_at, cursor_id = decode_cursor(cursor)
    cursor_key = (cursor_created_at, str(cursor_id))
    return [row for row in rows if (row.created_at, str(row.id)) < cursor_key]


def _session_summary(row: SessionRow) -> SessionSummary:
    metrics = {
        name: read_session_metric(row.result, name)
        for name in ("wpm", "pitch_range_st", "p_clarity")
    }
    return SessionSummary.model_validate({**row.model_dump(), **metrics})


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

    def set_avatar_path(self, user_id: UUID, avatar_path: str | None) -> ProfileRow | None:
        existing = self._state.profiles.get(user_id)
        if existing is None:
            return None
        row = existing.model_copy(update={"avatar_path": avatar_path}, deep=True)
        self._state.profiles[user_id] = row
        return row.model_copy(deep=True)

    def merge_preferences(self, user_id: UUID, patch: dict[str, Any]) -> ProfileRow | None:
        existing = self._state.profiles.get(user_id)
        if existing is None:
            return None
        merged = {**existing.preferences, **patch}
        row = existing.model_copy(update={"preferences": merged}, deep=True)
        self._state.profiles[user_id] = row
        return row.model_copy(deep=True)

    def delete_profile(self, user_id: UUID) -> bool:
        if user_id not in self._state.profiles:
            return False
        del self._state.profiles[user_id]
        self._state.baselines.pop(user_id, None)

        script_ids = {
            script_id for script_id, row in self._state.scripts.items() if row.user_id == user_id
        }
        for script_id in script_ids:
            del self._state.scripts[script_id]

        for session_id, row in list(self._state.sessions.items()):
            if row.user_id == user_id:
                del self._state.sessions[session_id]
        self._state.accounts.pop(user_id, None)  # Supabase: accounts cascade from auth.users
        return True


class MemoryBaselineRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def get_current_baseline(self, user_id: UUID) -> BaselineRow | None:
        current = next(
            (row for row in self._state.baselines.get(user_id, []) if row.is_current),
            None,
        )
        return current.model_copy(deep=True) if current is not None else None

    def replace_current_baseline(
        self, user_id: UUID, data: NewBaseline
    ) -> tuple[BaselineRow, BaselineRow | None]:
        """Same steps as the SQL function: copy the old row, add the new one, drop the old ones."""
        with self._state.baselines_lock:
            if any(row.id == data.id for rows in self._state.baselines.values() for row in rows):
                raise ConflictError(f"Baseline already exists: {data.id}")
            existing_rows = self._state.baselines.get(user_id, [])
            previous = next((row for row in existing_rows if row.is_current), None)
            previous = previous.model_copy(deep=True) if previous is not None else None
            new_row = BaselineRow(
                user_id=user_id,
                is_current=True,
                recorded_at=_now(),
                **data.model_dump(),
            )
            self._state.baselines[user_id] = [new_row.model_copy(deep=True)]
            # sessions.baseline_id is "on delete set null" in the database
            dropped_ids = {row.id for row in existing_rows}
            for session_id, session in self._state.sessions.items():
                if session.baseline_id in dropped_ids:
                    self._state.sessions[session_id] = session.model_copy(
                        update={"baseline_id": None}
                    )
            return new_row.model_copy(deep=True), previous


class MemoryScriptRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def create_script(self, user_id: UUID, data: NewScript) -> ScriptRow:
        with self._state.scripts_lock:
            twin = self.find_script_by_hash(user_id, data.content_hash)
            if twin is not None:
                raise ScriptDuplicateBodyError(twin)
            twin = self.find_script_by_title(user_id, data.title)
            if twin is not None:
                raise ScriptDuplicateTitleError(twin)
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

    def find_script_by_hash(self, user_id: UUID, content_hash: str) -> ScriptRow | None:
        matches = _newest_first(
            row
            for row in self._state.scripts.values()
            if row.user_id == user_id and row.content_hash == content_hash
        )
        return matches[0].model_copy(deep=True) if matches else None

    def find_script_by_title(self, user_id: UUID, title: str) -> ScriptRow | None:
        normalized = title.strip().lower()
        matches = _newest_first(
            row
            for row in self._state.scripts.values()
            if row.user_id == user_id and row.title.strip().lower() == normalized
        )
        return matches[0].model_copy(deep=True) if matches else None

    def list_scripts(self, user_id: UUID, limit: int, cursor: str | None) -> list[ScriptSummary]:
        _validate_limit(limit)
        rows = _newest_first(row for row in self._state.scripts.values() if row.user_id == user_id)
        rows = _after_cursor(rows, cursor)
        return [
            ScriptSummary(
                id=row.id,
                title=row.title,
                word_count=len(row.body.split()),
                created_at=row.created_at,
            )
            for row in rows[:limit]
        ]

    def count_scripts(self, user_id: UUID) -> int:
        return sum(1 for row in self._state.scripts.values() if row.user_id == user_id)

    def update_script(self, user_id: UUID, script_id: UUID, patch: ScriptPatch) -> ScriptRow | None:
        with self._state.scripts_lock:
            row = self._state.scripts.get(script_id)
            if row is None or row.user_id != user_id:
                return None
            values = patch.model_dump(exclude_none=True)
            if values.get("content_hash"):
                twin = self.find_script_by_hash(user_id, values["content_hash"])
                if twin is not None and twin.id != script_id:
                    raise ScriptDuplicateBodyError(twin)
            if values.get("title"):
                twin = self.find_script_by_title(user_id, values["title"])
                if twin is not None and twin.id != script_id:
                    raise ScriptDuplicateTitleError(twin)
            renamed = row.model_copy(update=values, deep=True)
            self._state.scripts[script_id] = renamed
            return renamed.model_copy(deep=True)

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

    def list_sessions(self, user_id: UUID, limit: int, cursor: str | None) -> list[SessionSummary]:
        _validate_limit(limit)
        rows = _newest_first(
            row for row in self._state.sessions.values()
            if row.user_id == user_id and row.status != "insufficient_audio"
        )
        rows = _after_cursor(rows, cursor)
        return [_session_summary(row) for row in rows[:limit]]

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]:
        _validate_limit(limit)
        rows = sorted(
            (row for row in self._state.sessions.values()
             if row.user_id == user_id and row.status != "insufficient_audio"),
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
            if row.user_id == user_id and not row.is_compact and row.status != "insufficient_audio"
        )
        return [row.model_copy(deep=True) for row in rows[keep:]]

    def list_compact_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]:
        if keep < 0:
            raise ValueError("keep must be non-negative")
        rows = _newest_first(
            row
            for row in self._state.sessions.values()
            if row.user_id == user_id and row.is_compact
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

    def delete_user_sessions(self, user_id: UUID) -> int:
        ids = [sid for sid, row in self._state.sessions.items() if row.user_id == user_id]
        for session_id in ids:
            del self._state.sessions[session_id]
        return len(ids)


class MemoryRateLimitRepo:
    """Same fixed window as public.hit_rate_limit() (0011), kept in RAM for dev and tests."""

    def __init__(self, state: MemoryState, clock: Callable[[], float] = time.monotonic) -> None:
        self._state = state
        self._clock = clock

    def hit(self, bucket: str, key: str, max_hits: int, window_s: int) -> bool:
        with self._state.rate_limits_lock:
            now = self._clock()
            start, hits = self._state.rate_limits.get((bucket, key), (now, 0))
            if now - start >= window_s:
                start, hits = now, 0
            hits += 1
            self._state.rate_limits[(bucket, key)] = (start, hits)
            return hits <= max_hits

    def reset(self) -> None:
        with self._state.rate_limits_lock:
            self._state.rate_limits.clear()


class MemoryScheduleRepo:
    """Schedule tables of 0012 kept in RAM. Every write holds schedule_lock, like one SQL
    statement or transaction, so two calls at the same moment cannot both win a claim."""

    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def _owned(self, user_id: UUID, event_id: UUID) -> ScheduleEventRow | None:
        row = self._state.schedule_events.get(event_id)
        return row if row is not None and row.user_id == user_id else None

    def _new_row(self, user_id: UUID, data: NewScheduleEvent) -> ScheduleEventRow:
        now = _now()
        values = data.model_dump() | {"schedule_set_at": data.schedule_set_at or now}
        row = ScheduleEventRow(
            **values, id=uuid4(), user_id=user_id, created_at=now, updated_at=now
        )
        self._state.schedule_events[row.id] = row
        return row

    def _drop_event(self, event_id: UUID) -> None:
        del self._state.schedule_events[event_id]
        for table in (self._state.schedule_checkins, self._state.schedule_reminders):
            for key in [k for k in table if k[0] == event_id]:
                del table[key]

    def list_events(self, user_id: UUID, start_date_to: date) -> list[ScheduleEventRow]:
        with self._state.schedule_lock:
            rows = list(self._state.schedule_events.values())
        return [r for r in rows if r.user_id == user_id and r.start_date <= start_date_to]

    def get_event(self, user_id: UUID, event_id: UUID) -> ScheduleEventRow | None:
        return self._owned(user_id, event_id)

    def count_events(self, user_id: UUID) -> int:
        with self._state.schedule_lock:
            return sum(r.user_id == user_id for r in self._state.schedule_events.values())

    def create_event(self, user_id: UUID, data: NewScheduleEvent) -> ScheduleEventRow:
        with self._state.schedule_lock:
            return self._new_row(user_id, data)

    def update_event(
        self, user_id: UUID, event_id: UUID, patch: ScheduleEventPatch
    ) -> ScheduleEventRow | None:
        with self._state.schedule_lock:
            row = self._owned(user_id, event_id)
            if row is None:
                return None
            values = row.model_dump() | patch.model_dump(exclude_unset=True)
            updated = ScheduleEventRow.model_validate(values | {"updated_at": _now()})
            self._state.schedule_events[event_id] = updated
            return updated

    def delete_event(self, user_id: UUID, event_id: UUID) -> bool:
        with self._state.schedule_lock:
            if self._owned(user_id, event_id) is None:
                return False
            self._drop_event(event_id)
            return True

    def split_event(
        self,
        user_id: UUID,
        event_id: UUID,
        end_until: date,
        new_event: NewScheduleEvent | None,
    ) -> list[ScheduleEventRow]:
        with self._state.schedule_lock:
            row = self._owned(user_id, event_id)
            if row is None:
                return []
            cut = {"end_kind": "until", "end_until": end_until, "end_count": None}
            old = ScheduleEventRow.model_validate(row.model_dump() | cut | {"updated_at": _now()})
            self._state.schedule_events[event_id] = old
            return [old] if new_event is None else [old, self._new_row(user_id, new_event)]

    def list_checkins(
        self, user_id: UUID, from_day: date, to_day: date
    ) -> list[ScheduleCheckinRow]:
        with self._state.schedule_lock:
            rows = list(self._state.schedule_checkins.values())
        return [r for r in rows if r.user_id == user_id and from_day <= r.occ_day <= to_day]

    def get_checkin(
        self, user_id: UUID, event_id: UUID, occ_day: date
    ) -> ScheduleCheckinRow | None:
        row = self._state.schedule_checkins.get((event_id, occ_day))
        return row if row is not None and row.user_id == user_id else None

    def upsert_checkin(
        self, user_id: UUID, event_id: UUID, occ_day: date, checkin_at: datetime
    ) -> ScheduleCheckinRow:
        with self._state.schedule_lock:
            if self._owned(user_id, event_id) is None:
                raise StorageError("Event not found")  # like the foreign key in 0012
            row = ScheduleCheckinRow(
                event_id=event_id, occ_day=occ_day, user_id=user_id, checkin_at=checkin_at
            )
            # setdefault keeps the first check-in time: the window counts from it
            return self._state.schedule_checkins.setdefault((event_id, occ_day), row)

    def mark_done(
        self, user_id: UUID, event_id: UUID, occ_day: date, session_id: UUID, done_at: datetime
    ) -> ScheduleCheckinRow | None:
        with self._state.schedule_lock:
            row = self.get_checkin(user_id, event_id, occ_day)
            if row is None or row.done_at is not None:
                return row
            done = row.model_copy(update={"done_at": done_at, "session_id": session_id})
            self._state.schedule_checkins[(event_id, occ_day)] = done
            return done

    def list_reminders(
        self, user_id: UUID, from_day: date, to_day: date
    ) -> list[ScheduleReminderRow]:
        with self._state.schedule_lock:
            mine = {k for k, r in self._state.schedule_events.items() if r.user_id == user_id}
            rows = list(self._state.schedule_reminders.values())
        return [r for r in rows if r.event_id in mine and from_day <= r.occ_day <= to_day]

    def list_reminder_candidates(self, until_day: date) -> list[ScheduleEventRow]:
        with self._state.schedule_lock:
            rows = list(self._state.schedule_events.values())
        return [r for r in rows if r.start_date <= until_day]

    def claim_reminder(
        self, event_id: UUID, occ_day: date, status: ReminderStatus, attempted_at: datetime
    ) -> bool:
        with self._state.schedule_lock:
            key = (event_id, occ_day)
            if event_id not in self._state.schedule_events:
                raise StorageError("Event not found")
            if key in self._state.schedule_reminders:
                return False
            self._state.schedule_reminders[key] = ScheduleReminderRow(
                event_id=event_id, occ_day=occ_day, status=status, attempted_at=attempted_at
            )
            return True

    def set_reminder_status(
        self, event_id: UUID, occ_day: date, status: ReminderStatus, sent_at: datetime | None
    ) -> None:
        with self._state.schedule_lock:
            row = self._state.schedule_reminders.get((event_id, occ_day))
            if row is not None:
                self._state.schedule_reminders[(event_id, occ_day)] = row.model_copy(
                    update={"status": status, "sent_at": sent_at}
                )

    def delete_user_schedule(self, user_id: UUID) -> int:
        with self._state.schedule_lock:
            ids = [k for k, r in self._state.schedule_events.items() if r.user_id == user_id]
            for event_id in ids:
                self._drop_event(event_id)
            return len(ids)


class MemoryAccountRepo:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    def get_shard(self, user_id: UUID) -> str | None:
        return self._state.accounts.get(user_id)

    def assign_shard(self, user_id: UUID, shard_ref: str) -> str:
        if not shard_ref:
            raise ValueError("shard_ref must not be empty")
        with self._state.accounts_lock:
            return self._state.accounts.setdefault(user_id, shard_ref)

    def count_by_shard(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for shard_ref in list(self._state.accounts.values()):
            counts[shard_ref] = counts.get(shard_ref, 0) + 1
        return counts


class MemoryAudioStore:
    def __init__(self, state: MemoryState) -> None:
        self._state = state

    @staticmethod
    def _validate_path(user_id: UUID, path: str) -> None:
        prefix = f"{user_id}/"
        if not isinstance(path, str) or not path.startswith(prefix) or "\\" in path:
            raise StorageError("Object path must be scoped to the current user")
        if build_avatar_path(user_id) == path:
            return
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

    def create_signed_url(self, user_id: UUID, bucket: str, path: str, ttl_s: int) -> str:
        self._validate_path(user_id, path)
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        if (bucket, path) not in self._state.files:
            raise StorageError(f"Object not found: {bucket}/{path}")
        return f"memory://{quote(bucket, safe='')}/{quote(path, safe='/')}?ttl={ttl_s}"

    def list_user_files(self, user_id: UUID, bucket: str) -> list[str]:
        prefix = f"{user_id}/"
        return sorted(p for b, p in self._state.files if b == bucket and p.startswith(prefix))

    def delete_user_folder(self, user_id: UUID, bucket: str) -> None:
        for path in self.list_user_files(user_id, bucket):
            self._state.files.pop((bucket, path), None)
        if self.list_user_files(user_id, bucket):
            raise StorageError(f"Folder not empty after delete in bucket {bucket}")
