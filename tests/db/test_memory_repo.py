from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.models import (
    ConflictError,
    NewBaseline,
    NewScript,
    NewSession,
    ProfilePatch,
    ProfileUpsert,
    StorageError,
    build_object_path,
    decode_cursor,
    encode_cursor,
)


def _new_session(*, audio_path: str | None = None) -> NewSession:
    return NewSession(
        id=uuid4(),
        script_snapshot="A saved script",
        status="ok",
        result={"overall": 80.0},
        result_schema_version="2.0",
        overall=80.0,
        audio_path=audio_path,
        series_path=None if audio_path is None else audio_path.replace(".webm", ".series.json"),
    )


def _new_script(content_hash: str = "hash-1") -> NewScript:
    return NewScript(
        title="Practice",
        body="A short script.",
        word_count=3,
        source="written",
        content_hash=content_hash,
    )


def test_get_session_other_user_returns_none():
    repos = build_memory_repos()
    owner, other_user = uuid4(), uuid4()
    session = repos.sessions.create_session(owner, _new_session())

    assert repos.sessions.get_session(other_user, session.id) is None


def test_delete_session_other_user_returns_false():
    repos = build_memory_repos()
    owner, other_user = uuid4(), uuid4()
    session = repos.sessions.create_session(owner, _new_session())

    assert repos.sessions.delete_session(other_user, session.id) is False
    assert repos.sessions.get_session(owner, session.id) is not None


def test_list_sessions_newest_first_and_only_returns_own_rows():
    repos = build_memory_repos()
    owner, other_user = uuid4(), uuid4()
    older = repos.sessions.create_session(owner, _new_session())
    repos.sessions.create_session(other_user, _new_session())
    newer = repos.sessions.create_session(owner, _new_session())

    rows = repos.sessions.list_sessions(owner, limit=20, cursor=None)
    expected = sorted(
        [older, newer],
        key=lambda row: (row.created_at, str(row.id)),
        reverse=True,
    )

    assert [row.id for row in rows] == [row.id for row in expected]


def test_list_sessions_cursor_has_no_duplicates():
    repos = build_memory_repos()
    user_id = uuid4()
    sessions = [repos.sessions.create_session(user_id, _new_session()) for _ in range(3)]

    first_page = repos.sessions.list_sessions(user_id, limit=2, cursor=None)
    cursor = encode_cursor(first_page[-1].created_at, first_page[-1].id)
    second_page = repos.sessions.list_sessions(user_id, limit=2, cursor=cursor)
    expected = sorted(
        sessions,
        key=lambda row: (row.created_at, str(row.id)),
        reverse=True,
    )

    assert [row.id for row in first_page] == [row.id for row in expected[:2]]
    assert [row.id for row in second_page] == [row.id for row in expected[2:]]
    assert not {row.id for row in first_page} & {row.id for row in second_page}


def test_list_sessions_rejects_out_of_range_limit():
    repos = build_memory_repos()

    with pytest.raises(ValueError, match="limit"):
        repos.sessions.list_sessions(uuid4(), limit=21, cursor=None)


def test_insufficient_audio_session_cannot_have_score_or_audio_path():
    with pytest.raises(ValueError, match="insufficient_audio"):
        NewSession(
            id=uuid4(),
            script_snapshot="",
            status="insufficient_audio",
            result={},
            result_schema_version="2.0",
            overall=20.0,
        )


def test_list_score_history_is_oldest_first_and_keeps_null_scores():
    repos = build_memory_repos()
    user_id = uuid4()
    first = repos.sessions.create_session(user_id, _new_session())
    unscored = NewSession(
        id=uuid4(),
        script_snapshot="",
        status="insufficient_audio",
        result={},
        result_schema_version="2.0",
    )
    second = repos.sessions.create_session(user_id, unscored)
    third = repos.sessions.create_session(user_id, _new_session())

    history = repos.sessions.list_score_history(user_id, limit=20)
    expected = sorted(
        [first, second, third],
        key=lambda row: (row.created_at, str(row.id)),
    )

    assert [point.session_id for point in history] == [row.id for row in expected]
    assert [point.overall for point in history] == [row.overall for row in expected]


def test_list_full_beyond_skips_newest_full_sessions():
    repos = build_memory_repos()
    user_id = uuid4()
    rows = [repos.sessions.create_session(user_id, _new_session()) for _ in range(3)]

    candidates = repos.sessions.list_full_beyond(user_id, keep=1)
    expected = sorted(
        rows,
        key=lambda row: (row.created_at, str(row.id)),
        reverse=True,
    )[1:]

    assert [row.id for row in candidates] == [row.id for row in expected]


def test_save_compact_session_clears_file_paths_and_is_one_time():
    repos = build_memory_repos()
    user_id = uuid4()
    path = build_object_path(user_id, uuid4(), ".webm")
    session = repos.sessions.create_session(user_id, _new_session(audio_path=path))

    assert repos.sessions.save_compact_session(
        user_id, session.id, {"overall": 80.0}, [{"word": "example"}]
    )
    compacted = repos.sessions.get_session(user_id, session.id)
    assert compacted is not None
    assert compacted.is_compact is True
    assert compacted.result == {"overall": 80.0}
    assert compacted.mistakes == [{"word": "example"}]
    assert compacted.audio_path is None
    assert compacted.series_path is None
    assert repos.sessions.save_compact_session(user_id, session.id, {}, []) is False


def test_save_compact_session_for_other_user_returns_false():
    repos = build_memory_repos()
    owner, other_user = uuid4(), uuid4()
    session = repos.sessions.create_session(owner, _new_session())

    assert repos.sessions.save_compact_session(other_user, session.id, {}, []) is False


def test_replace_current_baseline_keeps_exactly_one_current():
    repos = build_memory_repos()
    user_id = uuid4()
    data = NewBaseline(hesitation_threshold_s=0.7)

    first, old_first = repos.baselines.replace_current_baseline(user_id, data)
    second, old_second = repos.baselines.replace_current_baseline(user_id, data)

    assert old_first is None
    assert old_second == first
    assert repos.baselines.get_current_baseline(user_id) == second


def test_profile_patch_only_changes_fields_that_were_set():
    repos = build_memory_repos()
    user_id = uuid4()
    created = repos.profiles.upsert_profile(
        user_id, ProfileUpsert(target_accent="US", display_name="A")
    )

    updated = repos.profiles.update_profile(user_id, ProfilePatch(display_name="B"))

    assert updated is not None
    assert updated.display_name == "B"
    assert updated.target_accent == "US"
    assert updated.created_at == created.created_at


def test_missing_profile_and_baseline_return_none():
    repos = build_memory_repos()
    user_id = uuid4()

    assert repos.profiles.get_profile(user_id) is None
    assert repos.profiles.update_profile(user_id, ProfilePatch(display_name="new")) is None
    assert repos.baselines.get_current_baseline(user_id) is None


def test_set_consent_updates_consent_timestamp():
    repos = build_memory_repos()
    user_id = uuid4()
    repos.profiles.upsert_profile(user_id, ProfileUpsert(target_accent="US"))

    updated = repos.profiles.set_consent(user_id, consent_recording=True)

    assert updated is not None
    assert updated.consent_recording is True
    assert updated.consent_updated_at is not None


def test_delete_profile_removes_user_database_rows():
    repos = build_memory_repos()
    user_id = uuid4()
    repos.profiles.upsert_profile(user_id, ProfileUpsert(target_accent="US"))
    repos.baselines.replace_current_baseline(
        user_id, NewBaseline(hesitation_threshold_s=0.7)
    )
    repos.scripts.create_script(user_id, _new_script())
    repos.sessions.create_session(user_id, _new_session())

    assert repos.profiles.delete_profile(user_id) is True
    assert repos.profiles.get_profile(user_id) is None
    assert repos.baselines.get_current_baseline(user_id) is None
    assert repos.sessions.list_sessions(user_id, limit=20, cursor=None) == []
    assert repos.scripts.list_scripts(user_id, limit=20, cursor=None) == []
    assert repos.profiles.delete_profile(user_id) is False


def test_script_lookup_hash_and_cursor_pagination():
    repos = build_memory_repos()
    user_id = uuid4()
    first = repos.scripts.create_script(user_id, _new_script("first"))
    second = repos.scripts.create_script(user_id, _new_script("second"))
    third = repos.scripts.create_script(user_id, _new_script("third"))

    page_one = repos.scripts.list_scripts(user_id, limit=2, cursor=None)
    cursor = encode_cursor(page_one[-1].created_at, page_one[-1].id)
    page_two = repos.scripts.list_scripts(user_id, limit=2, cursor=cursor)
    all_rows = [first, second, third]
    expected = sorted(
        all_rows,
        key=lambda row: (row.created_at, str(row.id)),
        reverse=True,
    )

    assert repos.scripts.find_script_by_hash(user_id, "second") == second
    assert repos.scripts.get_script(uuid4(), second.id) is None
    assert [row.id for row in page_one + page_two] == [row.id for row in expected]


def test_deleting_script_from_other_user_returns_false():
    repos = build_memory_repos()
    owner, other_user = uuid4(), uuid4()
    script = repos.scripts.create_script(owner, _new_script())

    assert repos.scripts.delete_script(other_user, script.id) is False
    assert repos.scripts.get_script(owner, script.id) is not None


def test_delete_missing_script_returns_false():
    repos = build_memory_repos()

    assert repos.scripts.delete_script(uuid4(), uuid4()) is False


def test_deleting_script_nulls_session_reference_but_keeps_snapshot():
    repos = build_memory_repos()
    user_id = uuid4()
    script = repos.scripts.create_script(user_id, _new_script())
    session_data = _new_session()
    session_data = session_data.model_copy(
        update={"script_id": script.id, "script_snapshot": script.body}
    )
    session = repos.sessions.create_session(user_id, session_data)

    assert repos.scripts.delete_script(user_id, script.id)
    updated = repos.sessions.get_session(user_id, session.id)
    assert updated is not None
    assert updated.script_id is None
    assert updated.script_snapshot == script.body


def test_upload_file_outside_user_folder_raises():
    repos = build_memory_repos()
    user_id, other_user = uuid4(), uuid4()
    path = build_object_path(other_user, uuid4(), ".webm")

    with pytest.raises(StorageError):
        repos.files.upload_file(user_id, "audio", path, b"audio", "audio/webm")


def test_upload_file_same_path_raises_conflict_unless_upsert():
    repos = build_memory_repos()
    user_id = uuid4()
    path = build_object_path(user_id, uuid4(), ".webm")
    repos.files.upload_file(user_id, "audio", path, b"first", "audio/webm")

    with pytest.raises(ConflictError):
        repos.files.upload_file(user_id, "audio", path, b"second", "audio/webm")

    repos.files.upload_file(
        user_id, "audio", path, b"second", "audio/webm", upsert=True
    )
    assert repos.files.download_file(user_id, "audio", path) == b"second"


def test_delete_files_ignores_missing_objects_and_signed_url_needs_existing_file():
    repos = build_memory_repos()
    user_id = uuid4()
    path = build_object_path(user_id, uuid4(), ".series.json")

    repos.files.delete_files(user_id, "series", [path])
    with pytest.raises(StorageError):
        repos.files.create_signed_url(user_id, "series", path, ttl_s=60)

    repos.files.upload_file(user_id, "series", path, b"{}", "application/json")
    assert repos.files.create_signed_url(user_id, "series", path, ttl_s=60).startswith(
        "memory://"
    )


def test_audio_store_delete_is_idempotent_and_owner_scoped():
    repos = build_memory_repos()
    owner, other_user = uuid4(), uuid4()
    path = build_object_path(owner, uuid4(), ".webm")
    repos.files.upload_file(owner, "audio", path, b"recording", "audio/webm")

    with pytest.raises(StorageError):
        repos.files.delete_files(other_user, "audio", [path])
    assert repos.files.download_file(owner, "audio", path) == b"recording"

    repos.files.delete_files(owner, "audio", [path, path])
    with pytest.raises(StorageError):
        repos.files.download_file(owner, "audio", path)


def test_download_missing_file_raises_storage_error():
    repos = build_memory_repos()
    user_id = uuid4()
    path = build_object_path(user_id, uuid4(), ".webm")

    with pytest.raises(StorageError):
        repos.files.download_file(user_id, "audio", path)


def test_returned_rows_are_deep_copies():
    repos = build_memory_repos()
    user_id = uuid4()
    session = repos.sessions.create_session(user_id, _new_session())
    returned = repos.sessions.get_session(user_id, session.id)
    assert returned is not None
    returned.result["overall"] = 1

    stored = repos.sessions.get_session(user_id, session.id)
    assert stored is not None
    assert stored.result["overall"] == 80.0


def test_memory_repos_do_not_share_state():
    first = build_memory_repos()
    second = build_memory_repos()
    user_id = uuid4()
    first.profiles.upsert_profile(user_id, ProfileUpsert(target_accent="US"))

    assert second.profiles.get_profile(user_id) is None


def test_cursor_round_trip_and_invalid_cursor():
    row_id = uuid4()
    timestamp = datetime.now(UTC)
    encoded = encode_cursor(timestamp, row_id)

    assert decode_cursor(encoded) == (timestamp, row_id)
    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_cursor("not-a-cursor")


def test_get_repos_returns_cached_memory_in_dev(monkeypatch):
    from src.app.db import factory

    monkeypatch.setattr(factory.settings, "app_env", "dev")
    get_repos.cache_clear()
    try:
        assert get_repos() is get_repos()
    finally:
        get_repos.cache_clear()


def test_get_repos_rejects_non_dev_without_persistent_adapter(monkeypatch):
    from src.app.db import factory

    monkeypatch.setattr(factory.settings, "app_env", "test")
    get_repos.cache_clear()
    try:
        with pytest.raises(StorageError):
            get_repos()
    finally:
        get_repos.cache_clear()
