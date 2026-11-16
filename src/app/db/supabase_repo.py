"""Supabase implementation of the repository interfaces in repositories.py.

The backend uses the service key, which bypasses RLS. Every query therefore
filters by the owner itself (`id` for profiles, `user_id` for other tables).
All functions are sync; async endpoints call them via run_in_threadpool.
"""

from datetime import UTC, datetime
from uuid import UUID

from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError
from supabase import Client

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

UNIQUE_VIOLATION = "23505"
MAX_BEYOND_ROWS = 1000

SCRIPT_SUMMARY_COLUMNS = "id,title,topic,source,word_count,created_at"
SESSION_SUMMARY_COLUMNS = "id,created_at,topic,status,overall,label,components,is_compact"


def _execute(query):
    """Run a PostgREST query and turn library errors into StorageError."""
    try:
        return query.execute()
    except APIError as err:
        if err.code == UNIQUE_VIOLATION:
            raise ConflictError("Record already exists") from err
        raise StorageError("Database request failed") from err
    except Exception as err:
        raise StorageError("Database request failed") from err


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")


def _newest_page(query, limit: int, cursor: str | None):
    """Order newest first by (created_at, id) and keep rows after the cursor."""
    _validate_limit(limit)
    query = query.order("created_at", desc=True).order("id", desc=True).limit(limit)
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        stamp = cursor_created_at.isoformat()
        query = query.or_(
            f'created_at.lt."{stamp}",and(created_at.eq."{stamp}",id.lt.{cursor_id})'
        )
    return query


def _first(rows: list[dict]) -> dict | None:
    return rows[0] if rows else None


class SupabaseProfileRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.table("profiles")

    def get_profile(self, user_id: UUID) -> ProfileRow | None:
        resp = _execute(self._table().select("*").eq("id", str(user_id)).limit(1))
        row = _first(resp.data)
        return ProfileRow.model_validate(row) if row else None

    def upsert_profile(self, user_id: UUID, data: ProfileUpsert) -> ProfileRow:
        values = {"id": str(user_id), **data.model_dump(mode="json")}
        resp = _execute(self._table().upsert(values, on_conflict="id"))
        row = _first(resp.data)
        if row is None:
            raise StorageError("Profile upsert returned no row")
        return ProfileRow.model_validate(row)

    def update_profile(self, user_id: UUID, patch: ProfilePatch) -> ProfileRow | None:
        values = patch.model_dump(mode="json", exclude_unset=True)
        if not values:
            return self.get_profile(user_id)
        resp = _execute(self._table().update(values).eq("id", str(user_id)))
        row = _first(resp.data)
        return ProfileRow.model_validate(row) if row else None

    def set_consent(self, user_id: UUID, consent_recording: bool) -> ProfileRow | None:
        values = {
            "consent_recording": consent_recording,
            "consent_updated_at": datetime.now(UTC).isoformat(),
        }
        resp = _execute(self._table().update(values).eq("id", str(user_id)))
        row = _first(resp.data)
        return ProfileRow.model_validate(row) if row else None

    def delete_profile(self, user_id: UUID) -> bool:
        # Child rows go via "on delete cascade"; files are removed by the caller.
        resp = _execute(self._table().delete().eq("id", str(user_id)))
        return len(resp.data) > 0


class SupabaseBaselineRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.table("baselines")

    def get_current_baseline(self, user_id: UUID) -> BaselineRow | None:
        resp = _execute(
            self._table()
            .select("*")
            .eq("user_id", str(user_id))
            .eq("is_current", True)
            .limit(1)
        )
        row = _first(resp.data)
        return BaselineRow.model_validate(row) if row else None

    def _set_current(self, user_id: UUID, baseline_id: UUID, is_current: bool) -> None:
        _execute(
            self._table()
            .update({"is_current": is_current})
            .eq("id", str(baseline_id))
            .eq("user_id", str(user_id))
        )

    def replace_current_baseline(
        self, user_id: UUID, data: NewBaseline
    ) -> tuple[BaselineRow, BaselineRow | None]:
        # The unique index baselines_one_current allows one current row per user,
        # so the old row must be switched off before the new row is inserted.
        previous = self.get_current_baseline(user_id)
        if previous is not None:
            self._set_current(user_id, previous.id, False)

        values = {
            **data.model_dump(mode="json"),
            "user_id": str(user_id),
            "is_current": True,
        }
        try:
            resp = _execute(self._table().insert(values))
        except StorageError:
            if previous is not None:
                self._set_current(user_id, previous.id, True)  # best-effort rollback
            raise
        row = _first(resp.data)
        if row is None:
            raise StorageError("Baseline insert returned no row")
        return BaselineRow.model_validate(row), previous


class SupabaseScriptRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.table("scripts")

    def create_script(self, user_id: UUID, data: NewScript) -> ScriptRow:
        values = {**data.model_dump(mode="json"), "user_id": str(user_id)}
        resp = _execute(self._table().insert(values))
        row = _first(resp.data)
        if row is None:
            raise StorageError("Script insert returned no row")
        return ScriptRow.model_validate(row)

    def get_script(self, user_id: UUID, script_id: UUID) -> ScriptRow | None:
        resp = _execute(
            self._table()
            .select("*")
            .eq("id", str(script_id))
            .eq("user_id", str(user_id))
            .limit(1)
        )
        row = _first(resp.data)
        return ScriptRow.model_validate(row) if row else None

    def find_script_by_hash(self, user_id: UUID, content_hash: str) -> ScriptRow | None:
        resp = _execute(
            self._table()
            .select("*")
            .eq("user_id", str(user_id))
            .eq("content_hash", content_hash)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(1)
        )
        row = _first(resp.data)
        return ScriptRow.model_validate(row) if row else None

    def list_scripts(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[ScriptSummary]:
        query = self._table().select(SCRIPT_SUMMARY_COLUMNS).eq("user_id", str(user_id))
        resp = _execute(_newest_page(query, limit, cursor))
        return [ScriptSummary.model_validate(row) for row in resp.data]

    def delete_script(self, user_id: UUID, script_id: UUID) -> bool:
        # sessions.script_id is set to null by "on delete set null".
        resp = _execute(
            self._table().delete().eq("id", str(script_id)).eq("user_id", str(user_id))
        )
        return len(resp.data) > 0


class SupabaseSessionRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.table("sessions")

    def create_session(self, user_id: UUID, data: NewSession) -> SessionRow:
        values = {
            **data.model_dump(mode="json"),
            "user_id": str(user_id),
            "is_compact": False,
            "mistakes": None,
        }
        resp = _execute(self._table().insert(values))
        row = _first(resp.data)
        if row is None:
            raise StorageError("Session insert returned no row")
        return SessionRow.model_validate(row)

    def get_session(self, user_id: UUID, session_id: UUID) -> SessionRow | None:
        resp = _execute(
            self._table()
            .select("*")
            .eq("id", str(session_id))
            .eq("user_id", str(user_id))
            .limit(1)
        )
        row = _first(resp.data)
        return SessionRow.model_validate(row) if row else None

    def list_sessions(
        self, user_id: UUID, limit: int, cursor: str | None
    ) -> list[SessionSummary]:
        query = self._table().select(SESSION_SUMMARY_COLUMNS).eq("user_id", str(user_id))
        resp = _execute(_newest_page(query, limit, cursor))
        return [SessionSummary.model_validate(row) for row in resp.data]

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]:
        _validate_limit(limit)
        resp = _execute(
            self._table()
            .select("id,created_at,overall")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(limit)
        )
        rows = reversed(resp.data)  # the newest `limit` rows, returned OLD -> NEW
        return [
            ScorePoint(session_id=row["id"], created_at=row["created_at"], overall=row["overall"])
            for row in rows
        ]

    def list_full_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]:
        if keep < 0:
            raise ValueError("keep must be non-negative")
        resp = _execute(
            self._table()
            .select("*")
            .eq("user_id", str(user_id))
            .eq("is_compact", False)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .range(keep, keep + MAX_BEYOND_ROWS - 1)
        )
        return [SessionRow.model_validate(row) for row in resp.data]

    def save_compact_session(
        self,
        user_id: UUID,
        session_id: UUID,
        summary: dict,
        mistakes: list[dict],
    ) -> bool:
        # The repo only updates the row; the caller deletes the files via AudioStore.
        values = {
            "result": summary,
            "mistakes": mistakes,
            "is_compact": True,
            "audio_path": None,
            "series_path": None,
        }
        resp = _execute(
            self._table()
            .update(values)
            .eq("id", str(session_id))
            .eq("user_id", str(user_id))
            .eq("is_compact", False)
        )
        return len(resp.data) > 0

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool:
        resp = _execute(
            self._table().delete().eq("id", str(session_id)).eq("user_id", str(user_id))
        )
        return len(resp.data) > 0


def _validate_object_path(user_id: UUID, path: str) -> None:
    """Allow only paths made by build_object_path inside the user's own folder."""
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


def _is_duplicate(err: Exception) -> bool:
    status = str(getattr(err, "status", ""))
    text = str(err).lower()
    return status == "409" or "duplicate" in text or "already exists" in text


class SupabaseAudioStore:
    def __init__(self, client: Client) -> None:
        self._client = client

    def _bucket(self, bucket: str):
        return self._client.storage.from_(bucket)

    def upload_file(
        self,
        user_id: UUID,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str,
        upsert: bool = False,
    ) -> None:
        _validate_object_path(user_id, path)
        if not bucket or not content_type:
            raise ValueError("bucket and content_type are required")
        options = {"content-type": content_type}
        if upsert:
            options["upsert"] = "true"
        try:
            self._bucket(bucket).upload(path, bytes(content), options)
        except StorageApiError as err:
            if _is_duplicate(err):
                raise ConflictError(f"Object already exists: {bucket}/{path}") from err
            raise StorageError(f"Upload failed: {bucket}/{path}") from err
        except Exception as err:
            raise StorageError(f"Upload failed: {bucket}/{path}") from err

    def download_file(self, user_id: UUID, bucket: str, path: str) -> bytes:
        _validate_object_path(user_id, path)
        try:
            return self._bucket(bucket).download(path)
        except Exception as err:
            raise StorageError(f"Download failed: {bucket}/{path}") from err

    def delete_files(self, user_id: UUID, bucket: str, paths: list[str]) -> None:
        for path in paths:
            _validate_object_path(user_id, path)
        if not paths:
            return
        try:
            self._bucket(bucket).remove(list(paths))  # missing files are ignored
        except Exception as err:
            raise StorageError(f"Delete failed in bucket {bucket}") from err

    def create_signed_url(self, user_id: UUID, bucket: str, path: str, ttl_s: int) -> str:
        _validate_object_path(user_id, path)
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        try:
            resp = self._bucket(bucket).create_signed_url(path, ttl_s)
        except Exception as err:
            raise StorageError(f"Signed URL failed: {bucket}/{path}") from err
        url = resp.get("signedURL") or resp.get("signedUrl")
        if not url:
            raise StorageError(f"Object not found: {bucket}/{path}")
        return url
