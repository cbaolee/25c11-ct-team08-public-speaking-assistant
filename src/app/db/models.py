import base64
import binascii
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ScriptSource = Literal["generated_template", "generated_llm", "written"]
SessionStatus = Literal["ok", "insufficient_audio"]
ScriptDuration = Literal[5, 10, 15, 20]


class StorageError(Exception):
    """A database or object-storage operation failed."""


class ConflictError(StorageError):
    """An object or record conflicts with existing data."""


class ProfileUpsert(BaseModel):
    target_accent: str
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = None
    topics: list[str] = Field(default_factory=list)


class ProfilePatch(BaseModel):
    target_accent: str | None = None
    display_name: str | None = Field(default=None, max_length=50)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = None
    topics: list[str] | None = None


class ProfileRow(ProfileUpsert):
    id: UUID
    consent_recording: bool
    consent_updated_at: datetime | None
    created_at: datetime


class NewBaseline(BaseModel):
    id: UUID                                # created by the app, the audio path needs it
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
    word_count: int
    source: ScriptSource
    content_hash: str
    topic: str | None = None
    category: str | None = None
    duration_min: ScriptDuration | None = None
    citations: list[dict] = Field(default_factory=list)
    template_id: str | None = None
    models_used: list[str] = Field(default_factory=list)


class ScriptSummary(BaseModel):
    id: UUID
    title: str
    topic: str | None
    source: ScriptSource
    word_count: int
    created_at: datetime


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
                    "insufficient_audio sessions cannot have an overall score "
                    "or stored audio"
                )
        return self


class SessionRow(NewSession):
    user_id: UUID
    is_compact: bool
    mistakes: list[dict] | None
    created_at: datetime


class SessionSummary(BaseModel):
    id: UUID
    created_at: datetime
    topic: str | None
    status: SessionStatus
    overall: float | None
    label: str | None
    components: dict | None
    is_compact: bool


class ScorePoint(BaseModel):
    session_id: UUID
    created_at: datetime
    overall: float | None


def build_object_path(user_id: UUID, object_id: UUID, suffix: str) -> str:
    if suffix not in {".webm", ".series.json"}:
        raise ValueError("Unsupported object suffix")
    return f"{user_id}/{object_id}{suffix}"


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
