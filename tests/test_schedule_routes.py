from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from src.app.db.factory import get_repos
from src.app.main import app
from src.app.routes import schedule


def _event(day="2026-12-02", time="22:00"):
    return {
        "date": day,
        "time": time,
        "all_day": False,
        "timezone": "UTC",
        "duration_min": 10,
        "category": "sports",
        "color": "lime",
        "script": {"kind": "free"},
        "note": "Practice",
        "recurrence": {"kind": "none", "days": [], "end": {"kind": "never"}},
    }


def test_schedule_reminder_endpoint_requires_config(monkeypatch, caplog):
    monkeypatch.setattr(schedule.settings, "schedule_cron_secret", "")
    schedule._cron_secret_missing_logged = False
    client = TestClient(app)

    first = client.post("/internal/schedule/reminders/run")
    second = client.post("/internal/schedule/reminders/run")

    assert first.status_code == 503
    assert second.status_code == 503
    assert first.json()["error_code"] == "cron_not_configured"
    assert sum("SCHEDULE_CRON_SECRET is not configured" in r.message for r in caplog.records) == 1


def test_schedule_reminder_endpoint_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr(schedule.settings, "schedule_cron_secret", "correct-secret")
    client = TestClient(app)

    missing = client.post("/internal/schedule/reminders/run")
    wrong = client.post(
        "/internal/schedule/reminders/run",
        headers={"X-Cron-Secret": "wrong-secret"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["error_code"] == "unauthorized"


def test_schedule_reminder_endpoint_accepts_correct_secret(monkeypatch):
    monkeypatch.setattr(schedule.settings, "schedule_cron_secret", "correct-secret")
    client = TestClient(app)

    response = client.post(
        "/internal/schedule/reminders/run",
        headers={"X-Cron-Secret": "correct-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"sent": 0, "skipped": 0, "failed": 0}


def test_create_list_patch_delete_schedule(monkeypatch):
    fixed = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(schedule, "_now", lambda: fixed)
    client = TestClient(app)

    created = client.post("/api/schedule/events", json=_event())
    assert created.status_code == 201
    event_id = created.json()["id"]

    listed = client.get("/api/schedule", params={"from": "2026-12-01", "to": "2026-12-31"})
    assert listed.status_code == 200
    assert listed.json()["events"][0]["id"] == event_id

    patched = client.patch(
        f"/api/schedule/events/{event_id}/occurrences/2026-12-02",
        json={"note": "Updated"},
    )
    assert patched.status_code == 200
    assert patched.json()["events"][0]["note"] == "Updated"

    deleted = client.delete(
        f"/api/schedule/events/{event_id}/occurrences/2026-12-02"
    )
    assert deleted.status_code == 204


def test_checkin_and_complete(monkeypatch):
    fixed = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(schedule, "_now", lambda: fixed)
    client = TestClient(app)
    repos = app.dependency_overrides[get_repos]()

    event = client.post("/api/schedule/events", json=_event()).json()

    first = client.post(
        "/api/schedule/checkins",
        json={"event_id": event["id"], "day": "2026-12-02"},
    )
    assert first.json()["error_code"] == "not_started"

    monkeypatch.setattr(
        schedule,
        "_now",
        lambda: datetime(2026, 12, 2, 22, 30, tzinfo=UTC),
    )
    checkin = client.post(
        "/api/schedule/checkins",
        json={"event_id": event["id"], "day": "2026-12-02"},
    )
    assert checkin.status_code == 200

    session_id = uuid4()
    monkeypatch.setattr(
        repos.sessions,
        "get_session",
        lambda user_id, sid: SimpleNamespace(
            status="ok",
            overall=80.0,
            created_at=datetime(2026, 12, 2, 22, 31, tzinfo=UTC),
        ),
    )
    complete = client.post(
        f"/api/schedule/checkins/{event['id']}/2026-12-02/complete",
        json={"session_id": str(session_id)},
    )
    assert complete.status_code == 200, complete.json()
    assert complete.json()["done_at"] is not None

    repeated = client.post(
        f"/api/schedule/checkins/{event['id']}/2026-12-02/complete",
        json={"session_id": str(session_id)},
    )
    assert repeated.json()["done_at"] == complete.json()["done_at"]
