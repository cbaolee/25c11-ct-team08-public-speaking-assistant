import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.config import settings
from src.app.db.factory import build_memory_repos, get_repos
from src.app.db.models import NewSession, StorageError, build_object_path
from src.app.db.session_helpers import split_series
from src.app.deps import CurrentUser, get_current_user
from src.audio_processing.result_schema import EvaluationResultV2

FIXTURE = Path(__file__).parent / "fixtures" / "evaluation_ok.json"
INSUFFICIENT_FIXTURE = Path(__file__).parent / "fixtures" / "evaluation_insufficient.json"
USER_A = uuid4()
USER_B = uuid4()


@pytest.fixture
def session_api(monkeypatch):
    repos = build_memory_repos()
    current_user = {"id": USER_A}
    main.app.dependency_overrides[get_repos] = lambda: repos
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=current_user["id"])
    monkeypatch.setattr(settings, "retention_full_sessions", 10)
    monkeypatch.setattr(settings, "max_compact_sessions", 30)
    yield repos, current_user
    main.app.dependency_overrides.clear()


def _create_session(repos, user_id, *, files=False):
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))
    session_id = uuid4()
    audio_path = build_object_path(user_id, session_id, ".webm") if files else None
    series_path = build_object_path(user_id, session_id, ".series.json") if files else None
    without_series, series_json = split_series(result)
    row = repos.sessions.create_session(
        user_id,
        NewSession(
            id=session_id,
            script_snapshot="Practice script",
            status="ok",
            result=without_series,
            result_schema_version="2.1",
            overall=result["overall"],
            label=result["label"],
            components=result["components"],
            audio_path=audio_path,
            series_path=series_path,
        ),
    )
    if files:
        repos.files.upload_file(user_id, settings.audio_bucket, audio_path, b"audio", "audio/webm")
        repos.files.upload_file(
            user_id,
            settings.series_bucket,
            series_path,
            json.dumps(series_json).encode("utf-8"),
            "application/json",
        )
    return row


def test_insufficient_session_is_hidden_from_list_but_available_by_id(session_api):
    repos, _ = session_api
    visible = _create_session(repos, USER_A)
    result = EvaluationResultV2.model_validate_json(
        INSUFFICIENT_FIXTURE.read_text(encoding="utf-8")
    )
    session_id = main._save_result_to_history(
        repos=repos, user_id=USER_A, script="Practice script", result=result,
        source_audio_path=None,
    )
    client = TestClient(main.app)

    response = client.get("/api/sessions")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(visible.id)]
    detail = client.get(f"/api/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "insufficient_audio"


def test_list_sessions_uses_cursor_pagination(session_api):
    repos, _ = session_api
    rows = [_create_session(repos, USER_A) for _ in range(3)]
    client = TestClient(main.app)

    first = client.get("/api/sessions", params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    expected = sorted(rows, key=lambda row: (row.created_at, str(row.id)), reverse=True)
    assert [item["id"] for item in first_body["items"]] == [str(row.id) for row in expected[:2]]
    assert first_body["next_cursor"]

    second = client.get(
        "/api/sessions",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None
    assert not {item["id"] for item in first_body["items"]} & {
        item["id"] for item in second.json()["items"]
    }


def test_list_sessions_limit_twenty_detects_another_page(session_api):
    repos, _ = session_api
    for _ in range(21):
        _create_session(repos, USER_A)

    response = TestClient(main.app).get("/api/sessions", params={"limit": 20})

    assert response.status_code == 200
    assert len(response.json()["items"]) == 20
    assert response.json()["next_cursor"]


def test_list_sessions_rejects_invalid_limit(session_api):
    response = TestClient(main.app).get("/api/sessions", params={"limit": 0})

    assert response.status_code == 422


def test_list_sessions_rejects_invalid_cursor(session_api):
    response = TestClient(main.app).get("/api/sessions", params={"cursor": "abc"})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_cursor"}


def test_get_full_session_with_missing_files_still_returns_scores(session_api):
    repos, _ = session_api
    row = _create_session(repos, USER_A, files=True)
    # Simulate a retention run that deleted the files but stopped before compacting.
    repos.files.delete_files(USER_A, settings.audio_bucket, [row.audio_path])
    repos.files.delete_files(USER_A, settings.series_bucket, [row.series_path])

    response = TestClient(main.app).get(f"/api/sessions/{row.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == row.overall
    assert body["media_available"] is False
    assert "audio_url" not in body


@pytest.mark.parametrize("method", ["get", "delete"])
def test_session_of_another_user_returns_404(session_api, method):
    repos, _ = session_api
    row = _create_session(repos, USER_B, files=True)

    response = getattr(TestClient(main.app), method)(f"/api/sessions/{row.id}")

    assert response.status_code == 404


def test_get_full_session_restores_series_and_returns_signed_audio_url(session_api):
    repos, _ = session_api
    row = _create_session(repos, USER_A, files=True)

    response = TestClient(main.app).get(f"/api/sessions/{row.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["pitch_detail"]["contour_st"] is not None
    assert body["audio_url"].startswith("memory://")
    assert body["media_available"] is True
    assert "audio_path" not in body
    assert "series_path" not in body
    assert "user_id" not in body


def test_retention_compacts_sessions_beyond_ten(session_api):
    repos, _ = session_api
    rows = [_create_session(repos, USER_A, files=True) for _ in range(12)]

    main._prune_old_sessions(repos, USER_A)

    stored = [repos.sessions.get_session(USER_A, row.id) for row in rows]
    assert sum(not row.is_compact for row in stored) == 10
    compacted = [row for row in stored if row.is_compact]
    assert len(compacted) == 2
    assert all(row.mistakes is not None for row in compacted)
    assert all(row.audio_path is None and row.series_path is None for row in compacted)
    compacted_ids = {row.id for row in compacted}
    original_rows = [row for row in rows if row.id in compacted_ids]
    for row in original_rows:
        assert (settings.audio_bucket, row.audio_path) not in repos.profiles._state.files
        assert (settings.series_bucket, row.series_path) not in repos.profiles._state.files


def test_retention_deletes_oldest_compact_sessions_beyond_cap(session_api, monkeypatch):
    repos, _ = session_api
    monkeypatch.setattr(settings, "retention_full_sessions", 2)
    monkeypatch.setattr(settings, "max_compact_sessions", 3)
    rows = [_create_session(repos, USER_A, files=True) for _ in range(7)]
    newest_first = sorted(rows, key=lambda row: (row.created_at, str(row.id)), reverse=True)

    main._prune_old_sessions(repos, USER_A)

    stored = {row.id: repos.sessions.get_session(USER_A, row.id) for row in rows}
    # 2 newest stay full, the next 3 become compact, the 2 oldest are deleted
    assert [stored[row.id].is_compact for row in newest_first[:2]] == [False, False]
    assert [stored[row.id].is_compact for row in newest_first[2:5]] == [True, True, True]
    assert [stored[row.id] for row in newest_first[5:]] == [None, None]


def test_retention_retries_file_cleanup_before_compacting(session_api, monkeypatch):
    repos, _ = session_api
    rows = [_create_session(repos, USER_A, files=True) for _ in range(11)]
    oldest = min(rows, key=lambda row: (row.created_at, str(row.id)))
    delete_files = repos.files.delete_files

    def fail_delete(user_id, bucket, paths):
        if bucket == settings.audio_bucket and paths == [oldest.audio_path]:
            raise StorageError("storage unavailable")
        delete_files(user_id, bucket, paths)

    monkeypatch.setattr(repos.files, "delete_files", fail_delete)
    main._prune_old_sessions(repos, USER_A)
    unchanged = repos.sessions.get_session(USER_A, oldest.id)
    assert unchanged.is_compact is False
    assert unchanged.audio_path == oldest.audio_path

    monkeypatch.setattr(repos.files, "delete_files", delete_files)
    main._prune_old_sessions(repos, USER_A)
    retried = repos.sessions.get_session(USER_A, oldest.id)
    assert retried.is_compact is True
    assert retried.audio_path is None


def test_retention_failure_does_not_fail_session_save(session_api, monkeypatch):
    repos, _ = session_api

    def fail_list(user_id, *, keep):
        raise StorageError("database unavailable")

    monkeypatch.setattr(repos.sessions, "list_full_beyond", fail_list)
    result = EvaluationResultV2.model_validate_json(
        INSUFFICIENT_FIXTURE.read_text(encoding="utf-8")
    )

    session_id = main._save_result_to_history(
        repos=repos,
        user_id=USER_A,
        script="Practice script",
        result=result,
        source_audio_path=None,
    )

    assert session_id is not None
    assert repos.sessions.get_session(USER_A, UUID(session_id)) is not None


def test_delete_session_preserves_row_when_storage_delete_fails(session_api, monkeypatch):
    repos, _ = session_api
    row = _create_session(repos, USER_A, files=True)

    def fail_delete(*args, **kwargs):
        raise StorageError("storage unavailable")

    monkeypatch.setattr(repos.files, "delete_files", fail_delete)
    response = TestClient(main.app).delete(f"/api/sessions/{row.id}")

    assert response.status_code == 503
    assert repos.sessions.get_session(USER_A, row.id) is not None
