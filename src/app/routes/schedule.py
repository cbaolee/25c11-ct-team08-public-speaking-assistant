"""Schedule API routes and server-verified check-ins."""

import datetime as dt
import hashlib
import hmac
import logging
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.app.config import settings
from src.app.constants import CONSTANTS
from src.app.db.factory import Repos, get_repos
from src.app.db.models import NewScheduleEvent, ScheduleEventPatch, ScheduleEventRow, StorageError
from src.app.deps import CurrentUser, get_current_user
from src.app.schedule import rules

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedule")
cron_router = APIRouter(prefix="/internal/schedule/reminders")
_cron_secret_missing_logged = False

_schedule_config = CONSTANTS["schedule"]
SCHEDULE_CONFIG = _schedule_config


def _now() -> datetime:
    return datetime.now(UTC)


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message},
    )


class ScriptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    script_id: UUID | None = None
    title: str | None = None


class RecurrenceEndPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    until: dt.date | None = None
    count: int | None = None


class RecurrencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    days: list[int] = []
    end: RecurrenceEndPayload


class ScheduleEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: dt.date
    time: str | None = None
    all_day: bool
    timezone: str
    duration_min: int | None = None
    category: str
    color: str
    script: ScriptPayload
    note: str = ""
    recurrence: RecurrencePayload


class ScheduleEventPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: dt.date | None = None
    time: str | None = None
    all_day: bool | None = None
    timezone: str | None = None
    duration_min: int | None = None
    category: str | None = None
    color: str | None = None
    script: ScriptPayload | None = None
    note: str | None = None
    recurrence: RecurrencePayload | None = None


class CheckinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    day: dt.date


class CompletePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID


def _valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def _parse_time(value: str | None) -> time | None:
    if value is None:
        return None
    return time.fromisoformat(value)


def _nested_event(row: ScheduleEventRow) -> dict:
    script = (
        {"kind": "saved", "script_id": row.script_id, "title": row.script_title}
        if row.script_kind == "saved"
        else {"kind": row.script_kind}
    )
    recurrence_end = (
        {"kind": "never"}
        if row.end_kind == "never"
        else {"kind": "until", "until": row.end_until}
        if row.end_kind == "until"
        else {"kind": "count", "count": row.end_count}
    )
    return {
        "id": str(row.id),
        "date": row.start_date.isoformat(),
        "time": None if row.all_day else row.start_time.isoformat(timespec="minutes"),
        "all_day": row.all_day,
        "timezone": row.timezone,
        "duration_min": row.duration_min,
        "category": row.category,
        "color": row.color,
        "script": script,
        "note": row.note,
        "recurrence": {
            "kind": row.repeat_kind,
            "days": row.repeat_days,
            "end": recurrence_end,
        },
        "schedule_set_at": row.schedule_set_at.isoformat(),
        "details_edited_at": row.details_edited_at.isoformat()
        if row.details_edited_at is not None
        else None,
    }


def _from_payload(
    payload: ScheduleEventPayload,
    schedule_set_at: datetime | None = None,
) -> NewScheduleEvent:
    script = payload.script
    recurrence = payload.recurrence
    end = recurrence.end
    return NewScheduleEvent(
        start_date=payload.date,
        all_day=payload.all_day,
        start_time=None if payload.all_day else _parse_time(payload.time),
        timezone=payload.timezone,
        duration_min=payload.duration_min,
        category=payload.category,
        color=payload.color,
        script_kind=script.kind,
        script_id=script.script_id,
        script_title=script.title,
        note=payload.note,
        repeat_kind=recurrence.kind,
        repeat_days=recurrence.days if recurrence.kind == "custom" else [],
        end_kind=end.kind,
        end_until=end.until,
        end_count=end.count,
        schedule_set_at=schedule_set_at,
    )


def _row_payload(row: ScheduleEventRow) -> dict:
    data = _nested_event(row)
    data["id"] = row.id
    data["schedule_set_at"] = row.schedule_set_at
    data["details_edited_at"] = row.details_edited_at
    return data


def _count_before(event: ScheduleEventRow, day: dt.date) -> int:
    count = 0
    for occ in rules.expand_occurrences([event], event.start_date, day - timedelta(days=1)):
        if occ["day"] < day:
            count += 1
    return count


def _occurrence(event: ScheduleEventRow, day: dt.date) -> dict | None:
    return next(
        (
            occ
            for occ in rules.expand_occurrences([event], day, day)
            if occ["day"] == day
        ),
        None,
    )


def _previous_day(day: dt.date) -> dt.date:
    return day - timedelta(days=1)


def _rate_limit_key(user_id: UUID) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()


async def _allowed(repos: Repos, user_id: UUID) -> bool:
    def hit() -> bool:
        try:
            return repos.rate_limits.hit(
                "schedule_write",
                _rate_limit_key(user_id),
                SCHEDULE_CONFIG["writes_per_window"],
                SCHEDULE_CONFIG["window_s"],
            )
        except StorageError:
            logger.warning("Schedule rate limit counter unavailable; allowing the write")
            return True

    return await run_in_threadpool(hit)


@router.get("")
async def list_schedule(
    from_: Annotated[dt.date, Query(alias="from")],
    to: Annotated[dt.date, Query(alias="to")],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    if to < from_ or (to - from_).days > SCHEDULE_CONFIG["range_max_days"]:
        return _error(
            422,
            "validation_failed",
            "The schedule range is invalid.",
        )
    try:
        events = await run_in_threadpool(repos.schedule.list_events, user.id, to)
        checkins = await run_in_threadpool(repos.schedule.list_checkins, user.id, from_, to)
        reminders = await run_in_threadpool(repos.schedule.list_reminders, user.id, from_, to)
    except StorageError:
        return _error(503, "storage_unavailable", "The schedule could not be loaded.")

    visible = []
    for event in events:
        until = rules.series_until(event)
        if until is None or until >= from_:
            visible.append(_nested_event(event))
    return {
        "events": visible,
        "checkins": [row.model_dump(mode="json") for row in checkins],
        "reminders": [row.model_dump(mode="json") for row in reminders],
    }


@router.post("/events", status_code=201)
async def create_event(
    payload: ScheduleEventPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    if not await _allowed(repos, user.id):
        return _error(429, "rate_limited", "Too many schedule changes.")
    if not _valid_timezone(payload.timezone):
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_failed",
                "message": "The event could not be validated.",
                "fields": {"timezone": "invalid"},
            },
        )
    now = _now()
    fields = rules.validate_event(payload.model_dump(mode="python"), now)
    if fields:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_failed",
                "message": "The event could not be validated.",
                "fields": fields,
            },
        )
    try:
        count = await run_in_threadpool(repos.schedule.count_events, user.id)
    except StorageError:
        return _error(503, "storage_unavailable", "The schedule could not be checked.")
    if count >= SCHEDULE_CONFIG["max_events_per_user"]:
        return _error(409, "schedule_limit", "You have reached the schedule event limit.")
    try:
        row = await run_in_threadpool(
            repos.schedule.create_event,
            user.id,
            _from_payload(payload, schedule_set_at=now),
        )
    except (StorageError, ValueError):
        return _error(503, "storage_unavailable", "The event could not be created.")
    return _nested_event(row)


@router.patch("/events/{event_id}/occurrences/{day}")
async def patch_occurrence(
    event_id: UUID,
    day: dt.date,
    payload: ScheduleEventPatchPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    if not await _allowed(repos, user.id):
        return _error(429, "rate_limited", "Too many schedule changes.")
    try:
        event = await run_in_threadpool(repos.schedule.get_event, user.id, event_id)
    except StorageError:
        return _error(503, "storage_unavailable", "The schedule could not be loaded.")
    if event is None or _occurrence(event, day) is None:
        return _error(404, "event_not_found", "The schedule event was not found.")
    if payload.timezone is not None and not _valid_timezone(payload.timezone):
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_failed",
                "message": "The event could not be validated.",
                "fields": {"timezone": "invalid"},
            },
        )

    now = _now()
    occ = _occurrence(event, day)
    sent_fields = payload.model_fields_set
    schedule_changed = bool(sent_fields & {"date", "time", "all_day", "timezone", "recurrence"})
    details_changed = bool(sent_fields & {"duration_min", "category", "color", "script", "note"})
    if schedule_changed and not rules.can_edit_schedule(occ, now):
        return _error(403, "schedule_locked", "The schedule timing is locked.")
    if details_changed and not rules.can_edit_details(occ, now):
        return _error(403, "details_locked", "The schedule details are locked.")

    old = _nested_event(event)
    merged = {**old, **payload.model_dump(exclude_unset=True)}
    merged_payload = ScheduleEventPayload.model_validate({
        "date": merged["date"],
        "time": merged["time"],
        "all_day": merged["all_day"],
        "timezone": merged["timezone"],
        "duration_min": merged["duration_min"],
        "category": merged["category"],
        "color": merged["color"],
        "script": merged["script"],
        "note": merged["note"],
        "recurrence": merged["recurrence"],
    })
    fields = rules.validate_event(merged_payload.model_dump(mode="python"), now)
    if fields:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_failed",
                "message": "The event could not be validated.",
                "fields": fields,
            },
        )

    patch = ScheduleEventPatch(
        schedule_set_at=now if schedule_changed else None,
        details_edited_at=now if details_changed else None,
    )
    if event.repeat_kind == "none":
        flat_patch = {
            key: value
            for key, value in patch.model_dump(exclude_unset=True).items()
            if value is not None
        }
        flat_patch.update({
            "start_date": payload.date if payload.date is not None else event.start_date,
            "all_day": payload.all_day if payload.all_day is not None else event.all_day,
            "start_time": _parse_time(payload.time) if "time" in sent_fields else event.start_time,
            "timezone": payload.timezone if payload.timezone is not None else event.timezone,
            "duration_min": (
                payload.duration_min
                if payload.duration_min is not None
                else event.duration_min
            ),
            "category": payload.category if payload.category is not None else event.category,
            "color": payload.color if payload.color is not None else event.color,
            "script_kind": payload.script.kind if payload.script is not None else event.script_kind,
            "script_id": (
                payload.script.script_id
                if payload.script is not None
                else event.script_id
            ),
            "script_title": (
                payload.script.title
                if payload.script is not None
                else event.script_title
            ),
            "note": payload.note if payload.note is not None else event.note,
        })
        if payload.recurrence is not None:
            end = payload.recurrence.end
            flat_patch.update(
                repeat_kind=payload.recurrence.kind,
                repeat_days=payload.recurrence.days if payload.recurrence.kind == "custom" else [],
                end_kind=end.kind,
                end_until=end.until,
                end_count=end.count,
            )
        try:
            updated = await run_in_threadpool(
                repos.schedule.update_event,
                user.id,
                event_id,
                ScheduleEventPatch.model_validate(flat_patch),
            )
        except StorageError:
            return _error(503, "storage_unavailable", "The event could not be updated.")
        if updated is None:
            return _error(404, "event_not_found", "The schedule event was not found.")
        return {"events": [_nested_event(updated)]}

    before = _count_before(event, day)
    if before == 0:
        try:
            updated = await run_in_threadpool(
                repos.schedule.update_event,
                user.id,
                event_id,
                ScheduleEventPatch.model_validate({
                    **_split_patch_payload(payload, merged_payload),
                    "schedule_set_at": now if schedule_changed else None,
                    "details_edited_at": now if details_changed else None,
                }),
            )
        except StorageError:
            return _error(503, "storage_unavailable", "The event could not be updated.")
        if updated is None:
            return _error(404, "event_not_found", "The schedule event was not found.")
        return {"events": [_nested_event(updated)]}

    new_payload = merged_payload.model_copy(update={"date": payload.date or day})
    new_event = _from_payload(
        new_payload,
        schedule_set_at=now if schedule_changed else event.schedule_set_at,
    )
    if new_event.end_kind == "count":
        new_event.end_count = rules.remaining_count(event, day)
    try:
        rows = await run_in_threadpool(
            repos.schedule.split_event,
            user.id,
            event_id,
            _previous_day(day),
            new_event,
        )
    except StorageError:
        return _error(503, "storage_unavailable", "The event could not be split.")
    if not rows:
        return _error(404, "event_not_found", "The schedule event was not found.")
    return {"events": [_nested_event(row) for row in rows]}


def _split_patch_payload(payload: ScheduleEventPatchPayload, merged: ScheduleEventPayload) -> dict:
    return {
        "start_date": merged.date,
        "all_day": merged.all_day,
        "start_time": None if merged.all_day else _parse_time(merged.time),
        "timezone": merged.timezone,
        "duration_min": merged.duration_min,
        "category": merged.category,
        "color": merged.color,
        "script_kind": merged.script.kind,
        "script_id": merged.script.script_id,
        "script_title": merged.script.title,
        "note": merged.note,
        "repeat_kind": merged.recurrence.kind,
        "repeat_days": merged.recurrence.days if merged.recurrence.kind == "custom" else [],
        "end_kind": merged.recurrence.end.kind,
        "end_until": merged.recurrence.end.until,
        "end_count": merged.recurrence.end.count,
    }


@router.delete("/events/{event_id}/occurrences/{day}", status_code=204)
async def delete_occurrence(
    event_id: UUID,
    day: dt.date,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    if not await _allowed(repos, user.id):
        return _error(429, "rate_limited", "Too many schedule changes.")
    try:
        event = await run_in_threadpool(repos.schedule.get_event, user.id, event_id)
    except StorageError:
        return _error(503, "storage_unavailable", "The schedule could not be loaded.")
    if event is None or _occurrence(event, day) is None:
        return _error(404, "event_not_found", "The schedule event was not found.")
    now = _now()
    if not rules.can_edit_details(_occurrence(event, day), now):
        return _error(403, "details_locked", "The schedule details are locked.")
    if event.repeat_kind == "none" or _count_before(event, day) == 0:
        try:
            deleted = await run_in_threadpool(repos.schedule.delete_event, user.id, event_id)
        except StorageError:
            return _error(503, "storage_unavailable", "The event could not be deleted.")
        if not deleted:
            return _error(404, "event_not_found", "The schedule event was not found.")
        return JSONResponse(status_code=204, content=None)
    try:
        rows = await run_in_threadpool(
            repos.schedule.split_event,
            user.id,
            event_id,
            _previous_day(day),
            None,
        )
    except StorageError:
        return _error(503, "storage_unavailable", "The event could not be cut.")
    if not rows:
        return _error(404, "event_not_found", "The schedule event was not found.")
    return JSONResponse(status_code=204, content=None)


@router.post("/checkins")
async def checkin(
    payload: CheckinPayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    if not await _allowed(repos, user.id):
        return _error(429, "rate_limited", "Too many schedule changes.")
    try:
        event = await run_in_threadpool(repos.schedule.get_event, user.id, payload.event_id)
    except StorageError:
        return _error(503, "storage_unavailable", "The schedule could not be loaded.")
    if event is None:
        return _error(404, "event_not_found", "The schedule event was not found.")
    occ = _occurrence(event, payload.day)
    if occ is None:
        return _error(404, "event_not_found", "The schedule event was not found.")
    now = _now()
    if now < occ["start"]:
        return _error(409, "not_started", "The check-in has not started.")
    if now >= rules.window_closes_at(occ):
        return _error(409, "window_closed", "The check-in window is closed.")
    try:
        row = await run_in_threadpool(
            repos.schedule.upsert_checkin,
            user.id,
            payload.event_id,
            payload.day,
            now,
        )
    except StorageError:
        return _error(503, "storage_unavailable", "The check-in could not be saved.")
    return row.model_dump(mode="json")


@router.post("/checkins/{event_id}/{day}/complete")
async def complete_checkin(
    event_id: UUID,
    day: dt.date,
    payload: CompletePayload,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    repos: Annotated[Repos, Depends(get_repos)],
):
    if not await _allowed(repos, user.id):
        return _error(429, "rate_limited", "Too many schedule changes.")
    try:
        checkin_row = await run_in_threadpool(
            repos.schedule.get_checkin, user.id, event_id, day
        )
    except StorageError:
        return _error(503, "storage_unavailable", "The check-in could not be loaded.")
    if checkin_row is None:
        return _error(409, "not_checked_in", "Check in before completing a session.")
    if checkin_row.done_at is not None:
        return checkin_row.model_dump(mode="json")
    try:
        session = await run_in_threadpool(
            repos.sessions.get_session, user.id, payload.session_id
        )
    except StorageError:
        return _error(503, "storage_unavailable", "The session could not be loaded.")
    if session is None:
        return _error(404, "session_not_found", "The session was not found.")
    if session.status != "ok" or session.overall is None:
        return _error(
            422,
            "session_not_scorable",
            "The session is not a scorable completed practice.",
        )
    if session.created_at <= checkin_row.checkin_at:
        return _error(
            422,
            "session_not_scorable",
            "The session was not created after the check-in.",
        )
    try:
        done = await run_in_threadpool(
            repos.schedule.mark_done,
            user.id,
            event_id,
            day,
            payload.session_id,
            _now(),
        )
    except StorageError:
        return _error(503, "storage_unavailable", "The completion could not be saved.")
    if done is None:
        return _error(409, "not_checked_in", "Check in before completing a session.")
    return done.model_dump(mode="json")


@cron_router.post("/run")
async def run_schedule_reminders(
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
):
    global _cron_secret_missing_logged

    expected = settings.schedule_cron_secret
    if not expected:
        if not _cron_secret_missing_logged:
            logger.error("SCHEDULE_CRON_SECRET is not configured")
            _cron_secret_missing_logged = True
        return _error(
            503,
            "cron_not_configured",
            "The schedule reminder job is not configured.",
        )
    if x_cron_secret is None or not hmac.compare_digest(x_cron_secret, expected):
        return _error(401, "unauthorized", "The schedule reminder job was not authorized.")

    # P2-4.2 will replace this placeholder with the reminder claim/send loop.
    return {"sent": 0, "skipped": 0, "failed": 0}
