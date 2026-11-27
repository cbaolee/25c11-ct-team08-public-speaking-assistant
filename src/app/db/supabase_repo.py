"""Supabase implementation of the repository interfaces in repositories.py.

The backend uses the service key, which bypasses RLS. Every query therefore
filters by the owner itself (`id` for profiles, `user_id` for other tables).
All functions are sync; async endpoints call them via run_in_threadpool.
"""

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError
from supabase import Client

from src.app.config import max_list_page_size
from src.app.db.models import (
    SESSION_METRIC_PATHS,
    BaselineRow,
    ConflictError,
    NewBaseline,
    NewScript,
    NewSession,
    ProfilePatch,
    ProfileRow,
    ProfileUpsert,
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
)

UNIQUE_VIOLATION = "23505"
MAX_BEYOND_ROWS = 1000
STORAGE_LIST_PAGE = 100  # objects per Storage list call (and per remove call)
MAX_STORAGE_LIST_CALLS = 1000  # guard against a listing that never ends

SCRIPT_SUMMARY_COLUMNS = "id,title,body,created_at"
# PostgREST JSON paths ("alias:result->section->key") read the chart numbers inside result
SESSION_SUMMARY_COLUMNS = ",".join(
    [
        "id,created_at,topic,status,overall,label,components,is_compact,script_id",
        "audio_duration_s",
        *(f"{name}:result->{a}->{b}" for name, (a, b) in SESSION_METRIC_PATHS.items()),
    ]
)


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
    if not 1 <= limit <= max_list_page_size:
        raise ValueError(f"limit must be between 1 and {max_list_page_size}")


def _newest_page(query, limit: int, cursor: str | None):
    """Order newest first by (created_at, id) and keep rows after the cursor."""
    _validate_limit(limit)
    query = query.order("created_at", desc=True).order("id", desc=True).limit(limit)
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        stamp = cursor_created_at.isoformat()
        query = query.or_(f'created_at.lt."{stamp}",and(created_at.eq."{stamp}",id.lt.{cursor_id})')
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

    def set_avatar_path(self, user_id: UUID, avatar_path: str | None) -> ProfileRow | None:
        resp = _execute(self._table().update({"avatar_path": avatar_path}).eq("id", str(user_id)))
        row = _first(resp.data)
        return ProfileRow.model_validate(row) if row else None

    def merge_preferences(self, user_id: UUID, patch: dict[str, Any]) -> ProfileRow | None:
        # One SQL statement (db/migration_main/0003): keys not in `patch` are kept.
        params = {"p_user_id": str(user_id), "p_patch": patch}
        resp = _execute(self._client.rpc("merge_profile_preferences", params))
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
            self._table().select("*").eq("user_id", str(user_id)).eq("is_current", True).limit(1)
        )
        row = _first(resp.data)
        return BaselineRow.model_validate(row) if row else None

    def replace_current_baseline(
        self, user_id: UUID, data: NewBaseline
    ) -> tuple[BaselineRow, BaselineRow | None]:
        values = data.model_dump(mode="json")
        resp = _execute(
            self._client.rpc(
                "replace_current_baseline",
                {
                    "p_user_id": str(user_id),
                    "p_id": str(values["id"]),
                    "p_hesitation_threshold_s": values["hesitation_threshold_s"],
                    "p_median_pause_s": values.get("median_pause_s"),
                    "p_median_f0_hz": values.get("median_f0_hz"),
                    "p_mean_loudness_db": values.get("mean_loudness_db"),
                    "p_flags": values["flags"],
                    "p_audio_path": values.get("audio_path"),
                },
            )
        )
        payload = resp.data
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        if not isinstance(payload, dict):
            raise StorageError("Baseline insert returned no row")
        new_row = payload.get("new_row")
        previous_row = payload.get("previous_row")
        if not isinstance(new_row, dict):
            raise StorageError("Baseline insert returned no row")
        return (
            BaselineRow.model_validate(new_row),
            BaselineRow.model_validate(previous_row) if isinstance(previous_row, dict) else None,
        )


class SupabaseScriptRepo:
    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.table("scripts")

    def create_script(self, user_id: UUID, data: NewScript) -> ScriptRow:
        values = {**data.model_dump(mode="json"), "user_id": str(user_id)}
        try:
            resp = _execute(self._table().insert(values))
        except ConflictError as err:
            twin = self.find_script_by_hash(user_id, data.content_hash)
            if twin is not None:
                raise ScriptDuplicateBodyError(twin) from err
            twin = self.find_script_by_title(user_id, data.title)
            if twin is not None:
                raise ScriptDuplicateTitleError(twin) from err
            raise
        row = _first(resp.data)
        if row is None:
            raise StorageError("Script insert returned no row")
        return ScriptRow.model_validate(row)

    def get_script(self, user_id: UUID, script_id: UUID) -> ScriptRow | None:
        resp = _execute(
            self._table().select("*").eq("id", str(script_id)).eq("user_id", str(user_id)).limit(1)
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

    def find_script_by_title(self, user_id: UUID, title: str) -> ScriptRow | None:
        resp = _execute(
            self._table()
            .select("*")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .order("id", desc=True)
        )
        normalized = title.strip().lower()
        for row in resp.data:
            if str(row.get("title", "")).strip().lower() == normalized:
                return ScriptRow.model_validate(row)
        return None

    def list_scripts(self, user_id: UUID, limit: int, cursor: str | None) -> list[ScriptSummary]:
        query = self._table().select(SCRIPT_SUMMARY_COLUMNS).eq("user_id", str(user_id))
        resp = _execute(_newest_page(query, limit, cursor))
        return [
            ScriptSummary(
                id=row["id"],
                title=row["title"],
                word_count=len(row["body"].split()),
                created_at=row["created_at"],
            )
            for row in resp.data
        ]

    def count_scripts(self, user_id: UUID) -> int:
        resp = _execute(
            self._table().select("id", count="exact", head=True).eq("user_id", str(user_id))
        )
        return resp.count or 0

    def update_script(self, user_id: UUID, script_id: UUID, patch: ScriptPatch) -> ScriptRow | None:
        values = patch.model_dump(exclude_none=True)
        if not values:
            return self.get_script(user_id, script_id)
        try:
            resp = _execute(
                self._table().update(values).eq("id", str(script_id)).eq("user_id", str(user_id))
            )
        except ConflictError as err:
            if patch.content_hash is not None:
                twin = self.find_script_by_hash(user_id, patch.content_hash)
                if twin is not None and twin.id != script_id:
                    raise ScriptDuplicateBodyError(twin) from err
            if patch.title is not None:
                twin = self.find_script_by_title(user_id, patch.title)
                if twin is not None and twin.id != script_id:
                    raise ScriptDuplicateTitleError(twin) from err
            raise
        row = _first(resp.data)
        return ScriptRow.model_validate(row) if row else None

    def delete_script(self, user_id: UUID, script_id: UUID) -> bool:
        # sessions.script_id is set to null by "on delete set null".
        resp = _execute(self._table().delete().eq("id", str(script_id)).eq("user_id", str(user_id)))
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
            self._table().select("*").eq("id", str(session_id)).eq("user_id", str(user_id)).limit(1)
        )
        row = _first(resp.data)
        return SessionRow.model_validate(row) if row else None

    def list_sessions(self, user_id: UUID, limit: int, cursor: str | None) -> list[SessionSummary]:
        query = (
            self._table().select(SESSION_SUMMARY_COLUMNS).eq("user_id", str(user_id))
            .neq("status", "insufficient_audio")
        )
        resp = _execute(_newest_page(query, limit, cursor))
        return [SessionSummary.model_validate(row) for row in resp.data]

    def list_score_history(self, user_id: UUID, limit: int) -> list[ScorePoint]:
        _validate_limit(limit)
        resp = _execute(
            self._table()
            .select("id,created_at,overall")
            .eq("user_id", str(user_id))
            .neq("status", "insufficient_audio")
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
            .neq("status", "insufficient_audio")
            .order("created_at", desc=True)
            .order("id", desc=True)
            .range(keep, keep + MAX_BEYOND_ROWS - 1)
        )
        return [SessionRow.model_validate(row) for row in resp.data]

    def list_compact_beyond(self, user_id: UUID, keep: int) -> list[SessionRow]:
        if keep < 0:
            raise ValueError("keep must be non-negative")
        resp = _execute(
            self._table()
            .select("*")
            .eq("user_id", str(user_id))
            .eq("is_compact", True)
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

    def delete_user_sessions(self, user_id: UUID) -> int:
        resp = _execute(self._table().delete().eq("user_id", str(user_id)))
        return len(resp.data or [])


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SupabaseRateLimitRepo:
    """public.hit_rate_limit() on the core project (db/migration_main/0011_auth_rate_limits.sql)."""

    def __init__(self, client: Client, now: Callable[[], datetime] = _utc_now) -> None:
        self._client = client
        self._now = now

    def hit(self, bucket: str, key: str, max_hits: int, window_s: int) -> bool:
        params = {"p_bucket": bucket, "p_key": key, "p_max": max_hits, "p_window_s": window_s}
        data = _execute(self._client.rpc("hit_rate_limit", params)).data
        if isinstance(data, list):  # some client versions wrap a scalar result in a list
            data = data[0] if data else None
        if isinstance(data, dict):
            data = data.get("hit_rate_limit")
        if not isinstance(data, bool):
            raise StorageError("hit_rate_limit returned no answer")
        return data

    def retry_after_s(self, bucket: str, key: str, window_s: int) -> int:
        query = self._client.table("auth_rate_limits").select("window_start")
        row = _first(_execute(query.eq("bucket", bucket).eq("key", key).limit(1)).data)
        try:
            start = datetime.fromisoformat(row["window_start"])
        except (KeyError, TypeError, ValueError):  # no row, no field or not a timestamp
            return window_s
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        elapsed_s = (self._now() - start).total_seconds()
        # +1 s for clock skew between this server and Postgres (heuristic, not measured)
        left_s = math.ceil(window_s - elapsed_s) + 1
        return min(max(left_s, 1), window_s)


class SupabaseAccountRepo:
    """public.accounts on the core project (db/migration_main/0010_accounts.sql)."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.table("accounts")

    def get_shard(self, user_id: UUID) -> str | None:
        resp = _execute(self._table().select("shard_ref").eq("user_id", str(user_id)).limit(1))
        row = _first(resp.data)
        return None if row is None else str(row["shard_ref"])

    def assign_shard(self, user_id: UUID, shard_ref: str) -> str:
        """Insert unless a row exists (`on conflict do nothing`), then read the stored shard."""
        if not shard_ref:
            raise ValueError("shard_ref must not be empty")
        _execute(
            self._table().upsert(
                {"user_id": str(user_id), "shard_ref": shard_ref},
                on_conflict="user_id",
                ignore_duplicates=True,
            )
        )
        stored = self.get_shard(user_id)
        if stored is None:
            raise StorageError("Account insert returned no row")
        return stored

    def count_by_shard(self) -> dict[str, int]:
        """One small row per user (100 users at most, ADR-012), so the count is done here."""
        resp = _execute(self._table().select("shard_ref"))
        counts: dict[str, int] = {}
        for row in resp.data or []:
            shard_ref = str(row["shard_ref"])
            counts[shard_ref] = counts.get(shard_ref, 0) + 1
        return counts


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
    if build_avatar_path(user_id) == path:
        return
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

    def list_user_files(self, user_id: UUID, bucket: str) -> list[str]:
        """All object paths under `{user_id}/`, page by page (Storage returns `limit` per call).

        A listing returns files (with an id) and sub-folders (id is null); sub-folders are
        listed too, so nothing is missed even though our own paths are flat.
        """
        root = str(user_id)
        folders, paths, calls = [root], [], 0
        while folders:
            folder, offset = folders.pop(), 0
            while True:
                calls += 1
                if calls > MAX_STORAGE_LIST_CALLS:
                    raise StorageError(f"Listing did not end in bucket {bucket}")
                options = {
                    "limit": STORAGE_LIST_PAGE,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                }
                try:
                    page = self._bucket(bucket).list(folder, options)
                except Exception as err:
                    raise StorageError(f"List failed in bucket {bucket}") from err
                for entry in page or []:
                    name = entry.get("name") if isinstance(entry, dict) else None
                    if not name or "/" in name or name in {".", ".."}:
                        continue
                    child = f"{folder}/{name}"
                    (paths if entry.get("id") is not None else folders).append(child)
                if len(page or []) < STORAGE_LIST_PAGE:
                    break
                offset += STORAGE_LIST_PAGE
        return sorted(paths)

    def delete_user_folder(self, user_id: UUID, bucket: str) -> None:
        """Delete the whole `{user_id}/` folder in batches, then check it is empty.

        Idempotent: running it again after a failure deletes what is left.
        """
        paths = self.list_user_files(user_id, bucket)
        prefix = f"{user_id}/"
        if any(not p.startswith(prefix) for p in paths):
            raise StorageError("Object path must be scoped to the current user")
        for start in range(0, len(paths), STORAGE_LIST_PAGE):
            try:
                self._bucket(bucket).remove(paths[start : start + STORAGE_LIST_PAGE])
            except Exception as err:
                raise StorageError(f"Delete failed in bucket {bucket}") from err
        if self.list_user_files(user_id, bucket):
            raise StorageError(f"Folder not empty after delete in bucket {bucket}")
