from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from src.app.db.models import (
    BaselineRow,
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


class RateLimitRepo(Protocol):
    # Count one hit for (bucket, key) and say whether it is allowed: at most max_hits per
    # fixed window of window_s seconds. key is a hash, never an email (0011_auth_rate_limits).
    def hit(self, bucket: str, key: str, max_hits: int, window_s: int) -> bool: ...


# Schedule tables on the core project (ADR-016). The repo only stores and reads: the rules
# (window, reminder time, locks) live in src/app/schedule/rules.py and are applied by the route.
class ScheduleRepo(Protocol):
    # Events of the user with start_date <= start_date_to; the route drops ended series.
    def list_events(self, user_id: UUID, start_date_to: date) -> list[ScheduleEventRow]: ...

    # None when the event is missing or belongs to another user.
    def get_event(self, user_id: UUID, event_id: UUID) -> ScheduleEventRow | None: ...

    def count_events(self, user_id: UUID) -> int: ...

    def create_event(self, user_id: UUID, data: NewScheduleEvent) -> ScheduleEventRow: ...

    # Changes only the fields sent; None when the user does not own the event.
    def update_event(
        self, user_id: UUID, event_id: UUID, patch: ScheduleEventPatch
    ) -> ScheduleEventRow | None: ...

    # Also deletes its check-ins and reminders (on delete cascade).
    def delete_event(self, user_id: UUID, event_id: UUID) -> bool: ...

    # "This and following" in one step: end the old event on end_until, then add new_event
    # (None for delete). Returns [old] or [old, new]; [] when the user does not own the event.
    def split_event(
        self,
        user_id: UUID,
        event_id: UUID,
        end_until: date,
        new_event: NewScheduleEvent | None,
    ) -> list[ScheduleEventRow]: ...

    # Check-ins of the user with from_day <= occ_day <= to_day.
    def list_checkins(
        self, user_id: UUID, from_day: date, to_day: date
    ) -> list[ScheduleCheckinRow]: ...

    def get_checkin(
        self, user_id: UUID, event_id: UUID, occ_day: date
    ) -> ScheduleCheckinRow | None: ...

    # Insert the check-in, or return the one already there with its first checkin_at.
    def upsert_checkin(
        self, user_id: UUID, event_id: UUID, occ_day: date, checkin_at: datetime
    ) -> ScheduleCheckinRow: ...

    # Set done_at and session_id once; a done check-in is returned unchanged. None: no check-in.
    def mark_done(
        self, user_id: UUID, event_id: UUID, occ_day: date, session_id: UUID, done_at: datetime
    ) -> ScheduleCheckinRow | None: ...

    # Reminder rows of the user's events with from_day <= occ_day <= to_day.
    def list_reminders(
        self, user_id: UUID, from_day: date, to_day: date
    ) -> list[ScheduleReminderRow]: ...

    # Events of every user with start_date <= until_day, for the reminder job.
    def list_reminder_candidates(self, until_day: date) -> list[ScheduleEventRow]: ...

    # Insert the row only if none exists. True only for the call that inserted it, so at
    # most one run sends the email of a session.
    def claim_reminder(
        self, event_id: UUID, occ_day: date, status: ReminderStatus, attempted_at: datetime
    ) -> bool: ...

    def set_reminder_status(
        self, event_id: UUID, occ_day: date, status: ReminderStatus, sent_at: datetime | None
    ) -> None: ...

    # Every event of the user (check-ins and reminders go with them), for deleting an account.
    def delete_user_schedule(self, user_id: UUID) -> int: ...


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
