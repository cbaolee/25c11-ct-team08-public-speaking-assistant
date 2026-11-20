"""Tests for the Supabase repositories.

Unit tests at the top run offline. Tests marked `integration` call the real
psc-dev project and are skipped by default; run them with:
    uv run pytest -m integration
They need SUPABASE_URL, SUPABASE_SERVICE_KEY, DEV_USER_ID and DEV2_USER_ID
(the second test user) in .env, and both users must already have a profiles row.
"""

import os
from uuid import UUID, uuid4

import pytest
from dotenv import dotenv_values

from src.app.config import max_list_page_size, settings
from src.app.db import factory
from src.app.db.models import (
    ConflictError,
    NewBaseline,
    NewScript,
    NewSession,
    StorageError,
    build_object_path,
    encode_cursor,
)
from src.app.db.supabase_repo import (
    SupabaseBaselineRepo,
    _newest_page,
    _validate_object_path,
)

# ---------- offline unit tests ----------


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


def test_replace_baseline_calls_single_rpc_transaction():
    class FakeRpcRequest:
        def execute(self):
            class Response:
                data = {
                    "new_row": {
                        "id": str(new.id),
                        "user_id": str(user_id),
                        "median_pause_s": 0.5,
                        "hesitation_threshold_s": 0.9,
                        "median_f0_hz": 120.0,
                        "mean_loudness_db": 65.0,
                        "flags": [],
                        "audio_path": None,
                        "is_current": True,
                        "recorded_at": "2026-11-20T11:00:00+00:00",
                    },
                    "previous_row": None,
                }

            return Response()

    class FakeClient:
        def __init__(self):
            self.params = None

        def rpc(self, name, params):
            assert name == "replace_current_baseline"
            self.params = params
            return FakeRpcRequest()

    user_id = uuid4()
    new = NewBaseline(id=uuid4(), hesitation_threshold_s=0.9)
    client = FakeClient()
    row, previous = SupabaseBaselineRepo(client).replace_current_baseline(user_id, new)

    assert row.id == new.id
    assert row.is_current is True
    assert previous is None
    assert client.params["p_user_id"] == str(user_id)
    assert client.params["p_id"] == str(new.id)


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
            word_count=2,
            source="written",
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
            word_count=2,
            source="written",
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

    if original is not None:  # give the dev user back the baseline it had before
        factory.get_supabase_client().table("baselines").update({"is_current": False}).eq(
            "user_id", str(owner)
        ).execute()
        factory.get_supabase_client().table("baselines").update({"is_current": True}).eq(
            "id", str(original.id)
        ).execute()


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
