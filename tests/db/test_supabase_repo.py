"""Tests for the Supabase repositories.

Unit tests at the top run offline. Tests marked `integration` call the real
psc-dev project and are skipped by default; run them with:
    uv run pytest -m integration
They need SUPABASE_URL, SUPABASE_SERVICE_KEY, DEV_USER_ID and DEV2_USER_ID
(the second test user) in .env, and both users must already have a profiles row.
"""

import os
from io import BytesIO
from unittest.mock import MagicMock, call
from uuid import UUID, uuid4

import httpx
import pytest
from dotenv import dotenv_values
from PIL import Image

from src.app import main as app_main
from src.app.config import max_list_page_size, settings
from src.app.db import factory
from src.app.db.models import (
    ConflictError,
    NewBaseline,
    NewScript,
    NewSession,
    ScriptLimitReachedError,
    StorageError,
    build_avatar_path,
    build_content_hash,
    build_object_path,
    encode_cursor,
)
from src.app.db.supabase_repo import (
    SupabaseBaselineRepo,
    SupabaseSessionRepo,
    _execute,
    _newest_page,
    _validate_object_path,
)

# ---------- offline unit tests ----------


def test_list_sessions_excludes_insufficient_audio_offline():
    client = MagicMock()
    query = client.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.neq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value.data = []

    assert SupabaseSessionRepo(client).list_sessions(uuid4(), 20, None) == []
    query.neq.assert_called_once_with("status", "insufficient_audio")
    calls = query.mock_calls
    neq_index = calls.index(call.neq("status", "insufficient_audio"))
    assert neq_index < calls.index(call.order("created_at", desc=True))
    assert neq_index < calls.index(call.order("id", desc=True))
    assert neq_index < calls.index(call.limit(20))


@pytest.mark.parametrize(
    "method, terminal", [("list_score_history", "limit"), ("list_full_beyond", "range")]
)
def test_session_queries_filter_before_pagination_offline(method, terminal):
    client = MagicMock()
    query = client.table.return_value
    for name in ("select", "eq", "neq", "order", "limit", "range"):
        getattr(query, name).return_value = query
    query.execute.return_value.data = []

    assert getattr(SupabaseSessionRepo(client), method)(uuid4(), 10) == []
    query.neq.assert_called_once_with("status", "insufficient_audio")
    calls = query.mock_calls
    neq_index = calls.index(call.neq("status", "insufficient_audio"))
    assert neq_index < calls.index(call.order("created_at", desc=True))
    assert neq_index < calls.index(call.order("id", desc=True))
    assert neq_index < next(i for i, item in enumerate(calls) if item[0] == terminal)


def test_get_repos_uses_supabase_when_url_is_set(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(factory.settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(factory, "build_supabase_repos", lambda: sentinel)
    factory.get_repos.cache_clear()
    try:
        assert factory.get_repos() is sentinel
    finally:
        factory.get_repos.cache_clear()


def test_get_supabase_client_without_key_raises(monkeypatch):
    monkeypatch.setattr(factory.settings, "supabase_url", "")
    monkeypatch.setattr(factory.settings, "supabase_service_key", "")
    factory.get_supabase_client.cache_clear()
    try:
        with pytest.raises(StorageError):
            factory.get_supabase_client()
    finally:
        factory.get_supabase_client.cache_clear()


def test_validate_object_path_outside_user_folder_raises():
    owner, other_user = uuid4(), uuid4()
    with pytest.raises(StorageError):
        _validate_object_path(owner, build_object_path(other_user, uuid4(), ".webm"))
    with pytest.raises(StorageError):
        _validate_object_path(owner, f"{owner}/../x.webm")
    _validate_object_path(owner, build_object_path(owner, uuid4(), ".series.json"))


def test_newest_page_rejects_bad_limit():
    with pytest.raises(ValueError):
        _newest_page(None, 0, None)
    with pytest.raises(ValueError):
        _newest_page(None, max_list_page_size + 1, None)


class _FakeRpcClient:
    """Stands in for the Supabase client: records the RPC call, returns fixed data."""

    def __init__(self, data):
        self.data, self.params = data, None

    def rpc(self, name, params):
        assert name == "replace_current_baseline"
        self.params = params
        data = self.data

        class _Request:
            def execute(self):
                return type("Response", (), {"data": data})()

        return _Request()


def _baseline_json(baseline_id, user_id, *, is_current: bool) -> dict:
    return {
        "id": str(baseline_id),
        "user_id": str(user_id),
        "median_pause_s": 0.5,
        "hesitation_threshold_s": 0.9,
        "median_f0_hz": 120.0,
        "mean_loudness_db": 65.0,
        "flags": [],
        "audio_path": None,
        "is_current": is_current,
        "recorded_at": "2026-11-20T11:00:00+00:00",
    }


def test_replace_baseline_calls_single_rpc_transaction():
    user_id = uuid4()
    new = NewBaseline(id=uuid4(), hesitation_threshold_s=0.9)
    client = _FakeRpcClient(
        {"new_row": _baseline_json(new.id, user_id, is_current=True), "previous_row": None}
    )
    row, previous = SupabaseBaselineRepo(client).replace_current_baseline(user_id, new)

    assert row.id == new.id
    assert row.is_current is True
    assert previous is None
    assert client.params["p_user_id"] == str(user_id)
    assert client.params["p_id"] == str(new.id)


def test_replace_baseline_returns_previous_row():
    user_id, old_id = uuid4(), uuid4()
    new = NewBaseline(id=uuid4(), hesitation_threshold_s=0.9)
    client = _FakeRpcClient(
        {
            "new_row": _baseline_json(new.id, user_id, is_current=True),
            "previous_row": _baseline_json(old_id, user_id, is_current=False),
        }
    )
    _, previous = SupabaseBaselineRepo(client).replace_current_baseline(user_id, new)

    assert previous.id == old_id


@pytest.mark.parametrize("data", [{"new_row": None, "previous_row": None}, [], None])
def test_replace_baseline_without_new_row_raises(data):
    new = NewBaseline(id=uuid4(), hesitation_threshold_s=0.9)
    with pytest.raises(StorageError):
        SupabaseBaselineRepo(_FakeRpcClient(data)).replace_current_baseline(uuid4(), new)


# ---------- integration tests (psc-dev only) ----------


def _test_user_id(name: str) -> str:
    # Read only this one value; load_dotenv() would leak all of .env into os.environ
    # and change other tests that read os.getenv (for example the Groq generator).
    # The app no longer reads DEV_USER_ID / DEV2_USER_ID: they only name the test users.
    return os.getenv(name) or dotenv_values(".env").get(name) or ""


def _new_session(*, overall: float = 80.0) -> NewSession:
    return NewSession(
        id=uuid4(),
        script_snapshot="Integration test script",
        status="ok",
        result={"overall": overall},
        result_schema_version="2.0",
        overall=overall,
    )


@pytest.fixture
def env():
    first, second = _test_user_id("DEV_USER_ID"), _test_user_id("DEV2_USER_ID")
    required = (settings.supabase_url, settings.supabase_service_key, first, second)
    if not all(required):
        pytest.skip("Supabase dev config (incl. DEV_USER_ID, DEV2_USER_ID) is missing")
    factory.get_supabase_client.cache_clear()
    repos = factory.build_supabase_repos()
    owner, other_user = UUID(first), UUID(second)
    created = {"sessions": [], "scripts": [], "baselines": [], "files": []}
    yield repos, owner, other_user, created
    # clean up everything the test created
    client = factory.get_supabase_client()
    for session_id in created["sessions"]:
        repos.sessions.delete_session(owner, session_id)
    for script_id in created["scripts"]:
        repos.scripts.delete_script(owner, script_id)
    if created["baselines"]:
        client.table("baselines").delete().eq("user_id", str(owner)).in_(
            "id", [str(b) for b in created["baselines"]]
        ).execute()
    for bucket, path in created["files"]:
        repos.files.delete_files(owner, bucket, [path])


@pytest.mark.integration
def test_session_other_user_cannot_read_or_delete(env):
    repos, owner, other_user, created = env
    row = repos.sessions.create_session(owner, _new_session())
    created["sessions"].append(row.id)

    assert repos.sessions.get_session(owner, row.id).id == row.id
    assert repos.sessions.get_session(other_user, row.id) is None
    assert repos.sessions.delete_session(other_user, row.id) is False


@pytest.mark.integration
def test_create_session_duplicate_id_raises_conflict(env):
    repos, owner, _, created = env
    data = _new_session()
    created["sessions"].append(repos.sessions.create_session(owner, data).id)

    with pytest.raises(ConflictError):
        repos.sessions.create_session(owner, data)


@pytest.mark.integration
def test_list_sessions_newest_first_and_cursor_has_no_duplicates(env):
    repos, owner, _, created = env
    for _ in range(3):
        created["sessions"].append(repos.sessions.create_session(owner, _new_session()).id)

    first = repos.sessions.list_sessions(owner, limit=2, cursor=None)
    keys = [(r.created_at, str(r.id)) for r in first]
    assert keys == sorted(keys, reverse=True)

    last = first[-1]
    second = repos.sessions.list_sessions(
        owner, limit=2, cursor=encode_cursor(last.created_at, last.id)
    )
    assert not {r.id for r in first} & {r.id for r in second}
    assert all((r.created_at, str(r.id)) < (last.created_at, str(last.id)) for r in second)


@pytest.mark.integration
def test_list_sessions_summary_reads_chart_metrics_from_result(env):
    repos, owner, _, created = env
    data = _new_session().model_copy(
        update={
            "audio_duration_s": 35.0,
            "result": {
                "overall": 80.0,
                "fluency_detail": {"wpm": 132.5},
                "pitch_detail": {"range_semitones": 6.2},
                "subscores": {"p_clarity": None},
            },
        }
    )
    created["sessions"].append(repos.sessions.create_session(owner, data).id)

    item = next(
        r for r in repos.sessions.list_sessions(owner, limit=20, cursor=None) if r.id == data.id
    )
    assert (item.audio_duration_s, item.wpm, item.pitch_range_st) == (35.0, 132.5, 6.2)
    assert item.p_clarity is None


@pytest.mark.integration
def test_list_score_history_oldest_first(env):
    repos, owner, _, created = env
    for score in (70.0, 75.0, 80.0):
        created["sessions"].append(
            repos.sessions.create_session(owner, _new_session(overall=score)).id
        )

    points = repos.sessions.list_score_history(owner, limit=3)
    assert [p.overall for p in points] == [70.0, 75.0, 80.0]


@pytest.mark.integration
def test_save_compact_session_clears_paths_once(env):
    repos, owner, other_user, created = env
    session_id = uuid4()
    data = _new_session().model_copy(
        update={
            "id": session_id,
            "audio_path": build_object_path(owner, session_id, ".webm"),
            "series_path": build_object_path(owner, session_id, ".series.json"),
        }
    )
    created["sessions"].append(repos.sessions.create_session(owner, data).id)

    summary, mistakes = {"overall": 80.0}, [{"ref_index": 1}]
    assert repos.sessions.save_compact_session(other_user, session_id, summary, []) is False
    assert repos.sessions.save_compact_session(owner, session_id, summary, mistakes)
    row = repos.sessions.get_session(owner, session_id)
    assert row.is_compact and row.audio_path is None and row.series_path is None
    assert row.mistakes == [{"ref_index": 1}]
    assert repos.sessions.save_compact_session(owner, session_id, {}, []) is False


@pytest.mark.integration
def test_script_owner_only_and_find_by_hash(env):
    repos, owner, other_user, created = env
    content_hash = f"it-{uuid4()}"
    script = repos.scripts.create_script(
        owner,
        NewScript(
            title="IT",
            body="Hello there.",
            content_hash=content_hash,
        ),
    )
    created["scripts"].append(script.id)

    assert repos.scripts.find_script_by_hash(owner, content_hash).id == script.id
    assert repos.scripts.get_script(other_user, script.id) is None
    assert repos.scripts.find_script_by_hash(other_user, content_hash) is None


@pytest.mark.integration
def test_count_scripts_counts_only_own_rows(env):
    repos, owner, other_user, created = env
    before = repos.scripts.count_scripts(owner)
    script = repos.scripts.create_script(
        owner,
        NewScript(
            title="IT",
            body="Count me.",
            content_hash=f"it-{uuid4()}",
        ),
    )
    created["scripts"].append(script.id)

    assert repos.scripts.count_scripts(owner) == before + 1
    assert repos.scripts.count_scripts(other_user) >= 0


@pytest.mark.integration
def test_replace_current_baseline_keeps_one_current(env):
    repos, owner, _, created = env
    original = repos.baselines.get_current_baseline(owner)

    first = NewBaseline(id=uuid4(), hesitation_threshold_s=0.8)
    second = NewBaseline(id=uuid4(), hesitation_threshold_s=0.9)
    created["baselines"] += [first.id, second.id]
    repos.baselines.replace_current_baseline(owner, first)
    new_row, previous = repos.baselines.replace_current_baseline(owner, second)

    assert previous.id == first.id
    assert repos.baselines.get_current_baseline(owner).id == new_row.id == second.id

    _restore_current_baseline(owner, original)


def _restore_current_baseline(owner: UUID, original) -> None:
    """Give the dev user back the baseline it had before the test."""
    if original is None:
        return
    client = factory.get_supabase_client()
    client.table("baselines").update({"is_current": False}).eq("user_id", str(owner)).execute()
    client.table("baselines").update({"is_current": True}).eq("id", str(original.id)).execute()


@pytest.mark.integration
def test_replace_baseline_failed_insert_keeps_old_current(env):
    repos, owner, _, created = env
    original = repos.baselines.get_current_baseline(owner)
    keep = NewBaseline(id=uuid4(), hesitation_threshold_s=0.8)
    created["baselines"].append(keep.id)
    repos.baselines.replace_current_baseline(owner, keep)

    # hesitation_threshold_s is "not null": the insert inside the function fails,
    # so Postgres must also undo the "is_current = false" it ran just before.
    with pytest.raises(StorageError):
        _execute(
            factory.get_supabase_client().rpc(
                "replace_current_baseline",
                {"p_user_id": str(owner), "p_id": str(uuid4()), "p_hesitation_threshold_s": None},
            )
        )

    assert repos.baselines.get_current_baseline(owner).id == keep.id
    _restore_current_baseline(owner, original)


@pytest.mark.integration
def test_audio_store_upload_conflict_signed_url_and_delete(env):
    repos, owner, _, created = env
    bucket = settings.audio_bucket
    path = build_object_path(owner, uuid4(), ".webm")
    created["files"].append((bucket, path))

    repos.files.upload_file(owner, bucket, path, b"abc", "audio/webm")
    with pytest.raises(ConflictError):
        repos.files.upload_file(owner, bucket, path, b"xyz", "audio/webm")
    repos.files.upload_file(owner, bucket, path, b"xyz", "audio/webm", upsert=True)

    assert repos.files.download_file(owner, bucket, path) == b"xyz"
    assert repos.files.create_signed_url(owner, bucket, path, 60).startswith("http")

    repos.files.delete_files(owner, bucket, [path])
    repos.files.delete_files(owner, bucket, [path])  # missing file is ignored
    with pytest.raises(StorageError):
        repos.files.download_file(owner, bucket, path)


# ---------- avatar and preferences (psc-dev, needs db/migrations/0003) ----------


@pytest.fixture
def profile_restore(env):
    """Put the test user's avatar_path and preferences back as they were."""
    repos, owner, _, _ = env
    before = repos.profiles.get_profile(owner)
    yield env
    client = factory.get_supabase_client()
    client.table("profiles").update(
        {"avatar_path": before.avatar_path, "preferences": before.preferences}
    ).eq("id", str(owner)).execute()


def _webp(color: str) -> bytes:
    out = BytesIO()
    Image.new("RGB", (8, 8), color).save(out, format="WEBP")
    return out.getvalue()


@pytest.mark.integration
def test_avatar_upload_twice_sign_and_delete(profile_restore):
    repos, owner, _, created = profile_restore
    bucket, path = settings.avatars_bucket, build_avatar_path(owner)
    created["files"].append((bucket, path))

    repos.files.upload_file(owner, bucket, path, _webp("red"), "image/webp", True)
    repos.files.upload_file(owner, bucket, path, _webp("blue"), "image/webp", True)
    listed = factory.get_supabase_client().storage.from_(bucket).list(str(owner))
    assert [item["name"] for item in listed] == ["avatar.webp"]  # upsert keeps one file

    url = repos.files.create_signed_url(owner, bucket, path, settings.signed_url_ttl_s)
    assert httpx.get(url, timeout=10).status_code == 200

    assert repos.profiles.set_avatar_path(owner, path).avatar_path == path
    assert repos.profiles.set_avatar_path(owner, None).avatar_path is None

    repos.files.delete_files(owner, bucket, [path])
    assert factory.get_supabase_client().storage.from_(bucket).list(str(owner)) == []


@pytest.mark.integration
def test_merge_preferences_keeps_other_keys(profile_restore):
    repos, owner, _, _ = profile_restore
    factory.get_supabase_client().table("profiles").update({"preferences": {"theme": "dark"}}).eq(
        "id", str(owner)
    ).execute()

    row = repos.profiles.merge_preferences(owner, {"follow_wpm": 150})
    assert row.preferences == {"theme": "dark", "follow_wpm": 150}
    row = repos.profiles.merge_preferences(owner, {"follow_wpm": 155})
    assert row.preferences == {"theme": "dark", "follow_wpm": 155}
    assert repos.profiles.get_profile(owner).preferences["follow_wpm"] == 155


# ---------- saved-script cap and list (psc-dev) ----------


def _new_script(body: str) -> NewScript:
    return NewScript(
        title="Integration test script",
        body=body,
        content_hash=build_content_hash(body),
    )


@pytest.mark.integration
def test_list_scripts_returns_more_than_twenty(env):
    repos, owner, _, created = env
    before = repos.scripts.count_scripts(owner)
    for index in range(21):
        row = repos.scripts.create_script(owner, _new_script(f"List test {uuid4()} {index}."))
        created["scripts"].append(row.id)

    assert repos.scripts.count_scripts(owner) == before + 21
    rows = repos.scripts.list_scripts(owner, max_list_page_size, None)
    assert len(rows) >= 21  # the old repo limit stopped at 20


@pytest.mark.integration
def test_save_script_at_cap_raises_and_duplicate_still_returns(env, monkeypatch):
    repos, owner, _, created = env
    first = repos.scripts.create_script(owner, _new_script(f"Cap test {uuid4()}."))
    created["scripts"].append(first.id)
    count = repos.scripts.count_scripts(owner)
    monkeypatch.setattr(app_main, "max_saved_scripts", count)  # the user is now at the cap

    with pytest.raises(ScriptLimitReachedError) as err:
        app_main._save_script_row(repos, owner, _new_script(f"New text {uuid4()}."))
    assert (err.value.limit, err.value.count) == (count, count)

    same, created_new = app_main._save_script_row(repos, owner, _new_script(first.body))
    assert (same.id, created_new) == (first.id, False)  # a duplicate wins even at the cap


@pytest.mark.integration
def test_delete_script_keeps_session_snapshot(env):
    repos, owner, _, created = env
    script = repos.scripts.create_script(owner, _new_script(f"Snapshot test {uuid4()}."))
    session = repos.sessions.create_session(
        owner, _new_session().model_copy(update={"script_id": script.id})
    )
    created["sessions"].append(session.id)

    assert repos.scripts.delete_script(owner, script.id) is True  # deleted here, not in cleanup
    kept = repos.sessions.get_session(owner, session.id)
    assert kept.script_id is None  # sessions.script_id is "on delete set null"
    assert kept.script_snapshot == "Integration test script"
