"""Stub for the Part 1 Schedule rules.

This temporary implementation has the ADR-016 signatures. Replace it with the merged
Part 1 implementation without changing route call sites.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CHECKIN_WINDOW_H = 6
REMINDER_LEAD_MIN = 30
ALL_DAY_REMINDER_HOUR = 8


def _event_dict(event):
    return event.model_dump(mode="python") if hasattr(event, "model_dump") else dict(event)


def _zone(event):
    return ZoneInfo(str(event.get("timezone", "UTC")))


def _local_start(event, day):
    start_time = time(0, 0) if event["all_day"] else event["start_time"]
    return datetime.combine(day, start_time, tzinfo=_zone(event))


def _occurrence(event, day):
    aware = _local_start(event, day)
    return {
        "key": f"{event['id']}@{day.isoformat()}",
        "event_id": event["id"],
        "day": day,
        "start": aware.astimezone(UTC),
        "all_day": event["all_day"],
        "timezone": event["timezone"],
    }


def _matches(event, day):
    kind = event["repeat_kind"]
    if kind == "none":
        return day == event["start_date"]
    if kind == "daily":
        return True
    if kind == "weekly":
        return day.isoweekday() == event["start_date"].isoweekday()
    return day.isoweekday() in event["repeat_days"]


def series_until(event) -> date | None:
    event = _event_dict(event)
    if event["repeat_kind"] == "none":
        return event["start_date"]
    if event["end_kind"] == "never":
        return None
    if event["end_kind"] == "until":
        return event["end_until"]
    count = event["end_count"]
    found = 0
    day = event["start_date"]
    while found < count:
        if _matches(event, day):
            found += 1
        if found == count:
            return day
        day += timedelta(days=1)
    return None


def expand_occurrences(events: list, from_day: date, to_day: date) -> list[dict]:
    result = []
    for event in events:
        row = _event_dict(event)
        until = series_until(row)
        day = max(row["start_date"], from_day)
        while day <= to_day and (until is None or day <= until):
            if _matches(row, day):
                occ = _occurrence(row, day)
                result.append(occ)
            day += timedelta(days=1)
    return sorted(result, key=lambda occ: (occ["start"], occ["event_id"].hex))


def reminder_at(occ: dict) -> datetime:
    if occ["all_day"]:
        local = datetime.combine(occ["day"], time(8, 0), tzinfo=ZoneInfo(occ["timezone"]))
        return local.astimezone(UTC)
    return occ["start"] - timedelta(minutes=REMINDER_LEAD_MIN)


def window_closes_at(occ: dict) -> datetime:
    if occ["all_day"]:
        local = datetime.combine(
            occ["day"] + timedelta(days=1),
            time(0, 0),
            tzinfo=ZoneInfo(occ["timezone"]),
        )
    else:
        close = occ["start"] + timedelta(hours=CHECKIN_WINDOW_H)
        local_midnight = datetime.combine(
            occ["day"] + timedelta(days=1),
            time(0, 0),
            tzinfo=ZoneInfo(occ["timezone"]),
        )
        local_midnight_utc = local_midnight.astimezone(UTC)
        close = min(close, local_midnight_utc)
        return close
    return local.astimezone(UTC)


def occurrence_status(occ: dict, checkin: dict | None, now: datetime) -> str:
    if checkin is not None and checkin.get("done_at") is not None:
        return "done"
    if now < occ["start"]:
        return "upcoming"
    return "active" if now < window_closes_at(occ) else "missed"


def can_check_in(occ: dict, at: datetime) -> bool:
    return occ["start"] <= at < window_closes_at(occ)


def can_edit_schedule(occ: dict, now: datetime) -> bool:
    return now < reminder_at(occ) and now < occ["start"]


def can_edit_details(occ: dict, now: datetime) -> bool:
    return now < occ["start"]


def validate_event(payload: dict, now: datetime) -> dict[str, str]:
    errors = {}
    all_day = payload.get("all_day")
    start_date = payload.get("date")
    start_time = payload.get("time")
    timezone_name = payload.get("timezone")
    try:
        zone = ZoneInfo(timezone_name) if timezone_name else None
    except (ZoneInfoNotFoundError, ValueError):
        zone = None
        errors["timezone"] = "invalid"
    if not isinstance(all_day, bool) or not isinstance(start_date, date):
        errors["start"] = "invalid"
    elif all_day and start_time is not None:
        errors["start"] = "invalid"
    elif not all_day and (not isinstance(start_time, str) or not start_time):
        errors["start"] = "invalid"
    elif not all_day and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time):
        errors["start"] = "invalid"
    if isinstance(start_date, date) and isinstance(all_day, bool) and zone is not None:
        local_now = now.astimezone(zone)
        if all_day:
            if start_date <= local_now.date():
                errors["start"] = (
                    "all_day_today" if start_date == local_now.date() else "past"
                )
        else:
            try:
                hour, minute = map(int, start_time.split(":"))
                local_start = datetime.combine(start_date, time(hour, minute), tzinfo=zone)
                if local_start.astimezone(UTC) <= now:
                    errors["start"] = "past"
            except (AttributeError, ValueError):
                pass
    if payload.get("duration_min") not in (None, 5, 10, 15, 20):
        errors["duration_min"] = "invalid"
    if payload.get("category") not in {
        "any",
        "cinematography",
        "gender_studies",
        "information_technology",
        "learning_experiences",
        "sports",
        "wildlife",
    }:
        errors["category"] = "invalid"
    if payload.get("color") not in {
        "lime",
        "blue",
        "green",
        "amber",
        "brown",
        "red",
        "slate",
        "gray",
        "sky",
    }:
        errors["color"] = "invalid"
    script = payload.get("script") or {}
    if script.get("kind") not in {"free", "saved", "ai"}:
        errors["script"] = "invalid"
    if script.get("kind") == "saved" and (
        not script.get("script_id") or not script.get("title")
    ):
        errors["script"] = "saved_missing"
    if script.get("kind") == "ai":
        if payload.get("duration_min") is None:
            errors["duration_min"] = "ai_needs_length"
        if payload.get("category") == "any":
            errors["category"] = "ai_needs_category"
    note = payload.get("note", "")
    if len(note) > 200:
        errors["note"] = "too_long"
    recurrence = payload.get("recurrence") or {}
    if recurrence:
        kind = recurrence.get("kind")
        if kind not in {"none", "daily", "weekly", "custom"}:
            errors["recurrence"] = "invalid"
        if kind == "custom" and not recurrence.get("days"):
            errors["days"] = "empty"
        end = recurrence.get("end") or {}
        if end.get("kind") not in {"never", "until", "count"}:
            errors["recurrence"] = "invalid"
        if kind == "none" and end.get("kind") != "never":
            errors["recurrence"] = "invalid"
        if end.get("kind") == "until" and end.get("until") is not None:
            if end["until"] < start_date:
                errors["until"] = "before_start"
        if end.get("kind") == "count":
            count = end.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 99:
                errors["count"] = "invalid"
    return errors


def remaining_count(event, from_day: date) -> int:
    row = _event_dict(event)
    if row["end_kind"] != "count":
        return 0
    count = 0
    day = row["start_date"]
    while day < from_day:
        if _matches(row, day):
            count += 1
        day += timedelta(days=1)
    return max(0, row["end_count"] - count)


def reminder_state(occ: dict, event, now: datetime) -> str:
    row = _event_dict(event)
    at = reminder_at(occ)
    if row["schedule_set_at"] > at:
        return "skipped"
    if now < at:
        return "scheduled"
    return "sent"
