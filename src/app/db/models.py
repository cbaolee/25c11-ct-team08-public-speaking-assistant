import base64
import binascii
import hashlib
import json
from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from src.app.constants import CONSTANTS

SessionStatus = Literal["ok", "insufficient_audio"]


class StorageError(Exception):
    """A database or object-storage operation failed."""


class ConflictError(StorageError):
    """An object or record conflicts with existing data."""


class ScriptDuplicateTitleError(ConflictError):
    def __init__(self, twin: "ScriptRow") -> None:
        self.twin = twin
        super().__init__(f'Saved script title already exists: "{twin.title}"')


class ScriptDuplicateBodyError(ConflictError):
    def __init__(self, twin: "ScriptRow") -> None:
        self.twin = twin
        super().__init__(f'Saved script body already exists: "{twin.title}"')


class ScriptLimitReachedError(Exception):
    """The user already has the maximum number of saved scripts."""

    def __init__(self, limit: int, count: int) -> None:
        self.limit = limit
        self.count = count
        super().__init__(
            f"You have saved the maximum of {limit} scripts. Delete one to save a new script."
        )


class ProfileUpsert(BaseModel):
    target_accent: str
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = None


class ProfilePatch(BaseModel):
    target_accent: str | None = None
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = None


class UserPreferences(BaseModel):
    """Per-user settings in profiles.preferences (jsonb). Only the keys sent are merged in."""

    model_config = ConfigDict(extra="forbid")  # unknown keys -> 422

    # All three are checked against follow_wpm_min/max/step in app_constants.toml
    follow_wpm: StrictInt | None = None  # follow-along speed
    follow_wpm_min_choose: StrictInt | None = None  # the user's slider minimum
    follow_wpm_max_choose: StrictInt | None = None  # the user's slider maximum
    follow_auto_speed: StrictBool | None = None  # taps on the sentence being read set the speed

    @field_validator("follow_wpm", "follow_wpm_min_choose", "follow_wpm_max_choose")
    @classmethod
    def _check_wpm(cls, value: int | None) -> int | None:
        if value is None:
            return value
        web = CONSTANTS["web"]
        low, high, step = web["follow_wpm_min"], web["follow_wpm_max"], web["follow_wpm_step"]
        if not low <= value <= high or value % step != 0:
            raise ValueError(f"speed must be {low}-{high} in steps of {step}")
        return value

    @model_validator(mode="after")
    def _check_range(self) -> "UserPreferences":
        low, high = self.follow_wpm_min_choose, self.follow_wpm_max_choose
        if (low is None) != (high is None):
            raise ValueError("follow_wpm_min_choose and follow_wpm_max_choose are sent together")
        if low is not None and low >= high:
            raise ValueError("follow_wpm_min_choose must be below follow_wpm_max_choose")
        return self


class ProfileRow(ProfileUpsert):
    id: UUID
    avatar_path: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    consent_recording: bool
    consent_updated_at: datetime | None
    created_at: datetime


class NewBaseline(BaseModel):
    id: UUID  # created by the app, the audio path needs it
    hesitation_threshold_s: float
    median_pause_s: float | None = None
    median_f0_hz: float | None = None
    mean_loudness_db: float | None = None
    flags: list[str] = Field(default_factory=list)
    audio_path: str | None = None


class BaselineRow(NewBaseline):
    user_id: UUID
    is_current: bool
    recorded_at: datetime


class NewScript(BaseModel):
    title: str
    body: str
    content_hash: str


class ScriptSummary(BaseModel):
    id: UUID
    title: str
    word_count: int
    created_at: datetime


class ScriptPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    content_hash: str | None = None


class ScriptRow(NewScript):
    id: UUID
    user_id: UUID
    created_at: datetime


class NewSession(BaseModel):
    id: UUID
    script_snapshot: str
    status: SessionStatus
    result: dict
    result_schema_version: str
    script_id: UUID | None = None
    baseline_id: UUID | None = None
    topic: str | None = None
    accent: str | None = None
    reason: str | None = None
    overall: float | None = None
    label: str | None = None
    components: dict | None = None
    audio_path: str | None = None
    series_path: str | None = None
    audio_duration_s: float | None = None
    stt_provider: str | None = None
    stt_model: str | None = None

    @model_validator(mode="after")
    def insufficient_audio_is_not_scored_or_stored(self) -> "NewSession":
        if self.status == "insufficient_audio":
            if self.overall is not None or self.audio_path is not None:
                raise ValueError(
                    "insufficient_audio sessions cannot have an overall score or stored audio"
                )
        return self


class SessionRow(NewSession):
    user_id: UUID
    is_compact: bool
    mistakes: list[dict] | None
    created_at: datetime


# Chart numbers copied from `result` into each history item, so Home can draw its charts
# without opening every session. Compacted rows keep these keys (compact_session keeps them).
SESSION_METRIC_PATHS: dict[str, tuple[str, str]] = {
    "wpm": ("fluency_detail", "wpm"),
    "pitch_range_st": ("pitch_detail", "range_semitones"),
    "p_clarity": ("subscores", "p_clarity"),
}


class SessionSummary(BaseModel):
    id: UUID
    created_at: datetime
    topic: str | None
    status: SessionStatus
    overall: float | None
    label: str | None
    components: dict | None
    is_compact: bool
    script_id: UUID | None = None
    audio_duration_s: float | None = None
    wpm: float | None = None
    pitch_range_st: float | None = None
    p_clarity: float | None = None


class ScorePoint(BaseModel):
    session_id: UUID
    created_at: datetime
    overall: float | None


# ---------- Schedule (ADR-016, db/migration_main/0012_schedule.sql) ----------

ScheduleCategory = Literal[
    "any",
    "cinematography",
    "gender_studies",
    "information_technology",
    "learning_experiences",
    "sports",
    "wildlife",
]
ScheduleColor = Literal["lime", "blue", "green", "amber", "brown", "red", "slate", "gray", "sky"]
ScriptKind = Literal["free", "saved", "ai"]
RepeatKind = Literal["none", "daily", "weekly", "custom"]
EndKind = Literal["never", "until", "count"]
ReminderStatus = Literal["sent", "failed", "skipped"]


class NewScheduleEvent(BaseModel):
    """One event as the table stores it. Dates and times are local to `timezone`."""

    start_date: date
    all_day: bool
    start_time: time | None = None
    timezone: str = Field(min_length=1, max_length=64)
    duration_min: Literal[5, 10, 15, 20] | None = None
    category: ScheduleCategory
    color: ScheduleColor
    script_kind: ScriptKind
    script_id: UUID | None = None
    script_title: str | None = None
    note: str = Field(default="", max_length=200)
    repeat_kind: RepeatKind
    repeat_days: list[int] = Field(default_factory=list)
    end_kind: EndKind
    end_until: date | None = None
    end_count: int | None = Field(default=None, ge=1, le=99)
    schedule_set_at: datetime | None = None  # None: the database sets now()
    details_edited_at: datetime | None = None

    @model_validator(mode="after")
    def _same_checks_as_the_table(self) -> "NewScheduleEvent":
        # Same rules as the checks in 0012, so the memory repo refuses what Postgres refuses.
        if self.all_day != (self.start_time is None):
            raise ValueError("start_time is set exactly when the event is not all day")
        if self.script_kind == "saved" and (self.script_id is None or self.script_title is None):
            raise ValueError("a saved script needs script_id and script_title")
        if self.script_kind == "ai" and (self.duration_min is None or self.category == "any"):
            raise ValueError("an AI script needs a duration and a category")
        if any(day not in range(1, 8) for day in self.repeat_days):
            raise ValueError("repeat_days are ISO weekdays 1-7")
        if (self.repeat_kind == "custom") != bool(self.repeat_days):
            raise ValueError("repeat_days are set exactly when repeat_kind is custom")
        if self.repeat_kind == "none" and self.end_kind != "never":
            raise ValueError("an event that does not repeat never ends")
        if (self.end_kind == "until") != (self.end_until is not None):
            raise ValueError("end_until is set exactly when end_kind is until")
        if (self.end_kind == "count") != (self.end_count is not None):
            raise ValueError("end_count is set exactly when end_kind is count")
        if self.end_until is not None and self.end_until < self.start_date:
            raise ValueError("end_until is before start_date")
        return self


class ScheduleEventPatch(BaseModel):
    """Only the fields sent change. The route sets schedule_set_at / details_edited_at."""

    start_date: date | None = None
    all_day: bool | None = None
    start_time: time | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    duration_min: Literal[5, 10, 15, 20] | None = None
    category: ScheduleCategory | None = None
    color: ScheduleColor | None = None
    script_kind: ScriptKind | None = None
    script_id: UUID | None = None
    script_title: str | None = None
    note: str | None = Field(default=None, max_length=200)
    repeat_kind: RepeatKind | None = None
    repeat_days: list[int] | None = None
    end_kind: EndKind | None = None
    end_until: date | None = None
    end_count: int | None = Field(default=None, ge=1, le=99)
    schedule_set_at: datetime | None = None
    details_edited_at: datetime | None = None


class ScheduleEventRow(NewScheduleEvent):
    id: UUID
    user_id: UUID
    schedule_set_at: datetime
    created_at: datetime
    updated_at: datetime


class ScheduleCheckinRow(BaseModel):
    event_id: UUID
    occ_day: date  # local day of the session
    user_id: UUID
    checkin_at: datetime
    done_at: datetime | None = None
    session_id: UUID | None = None


class ScheduleReminderRow(BaseModel):
    event_id: UUID
    occ_day: date
    status: ReminderStatus
    attempted_at: datetime
    sent_at: datetime | None = None


def read_session_metric(result: dict | None, name: str) -> float | None:
    """Return one SESSION_METRIC_PATHS number from a result dict, or None when it is missing."""
    section, key = SESSION_METRIC_PATHS[name]
    part = (result or {}).get(section)
    value = part.get(key) if isinstance(part, dict) else None
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def build_content_hash(body: str) -> str:
    """SHA-256 of the stored script text; the same text saved twice gets the same hash."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_object_path(user_id: UUID, object_id: UUID, suffix: str) -> str:
    if suffix not in {".webm", ".series.json"}:
        raise ValueError("Unsupported object suffix")
    return f"{user_id}/{object_id}{suffix}"


def build_avatar_path(user_id: UUID) -> str:
    return f"{user_id}/avatar.webp"


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(row_id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        created_at = datetime.fromisoformat(payload["created_at"])
        row_id = UUID(payload["id"])
    except (
        binascii.Error,
        UnicodeDecodeError,
        ValueError,
        KeyError,
        TypeError,
    ) as err:
        raise ValueError("Invalid cursor") from err
    return created_at, row_id
