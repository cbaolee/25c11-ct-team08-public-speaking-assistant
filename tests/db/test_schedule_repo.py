"""Schedule repositories (ADR-016, migration 0012).

The in-memory repository is tested for real; the Supabase repository with a fake client, to
check which queries it sends. 0012 has not run on Supabase yet, so there is no live test here.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.app.auth import MemoryAuthProvider
from src.app.db.factory import build_memory_repos
from src.app.db.memory import MemoryScheduleRepo, MemoryState
from src.app.db.models import NewScheduleEvent, ScheduleEventPatch, StorageError
from src.app.db.supabase_repo import SupabaseScheduleRepo

USER_A = uuid4()
USER_B = uuid4()
DAY = date(2026, 12, 1)
NOW = datetime(2026, 11, 28, 9, 30, tzinfo=UTC)


def _event(**changes) -> NewScheduleEvent:
    values = {
        "start_date": DAY,
        "all_day": False,
        "start_time": time(19, 30),
        "timezone": "Asia/Ho_Chi_Minh",
        "category": "any",
        "color": "lime",
        "script_kind": "free",
        "repeat_kind": "daily",
        "end_kind": "never",
    }
    return NewScheduleEvent(**(values | changes))


@pytest.fixture
def repo() -> MemoryScheduleRepo:
    return MemoryScheduleRepo(MemoryState())


# ---------- model checks (same as the SQL checks in 0012) ----------


@pytest.mark.parametrize(
    "changes",
    [
        {"all_day": True},  # all day with a start time
        {"start_time": None},  # timed without a start time
        {"script_kind": "saved"},  # saved script without id and title
        {"script_kind": "ai", "duration_min": 10},  # AI script with category "any"
        {"repeat_kind": "custom"},  # custom without days
        {"repeat_days": [1]},  # days on a non-custom repeat
        {"repeat_kind": "custom", "repeat_days": [8]},
        {"repeat_kind": "none", "end_kind": "count", "end_count": 3},
        {"end_kind": "until"},
        {"end_kind": "until", "end_until": DAY - timedelta(days=1)},
        {"end_kind": "count", "end_count": 100},
        {"note": "x" * 201},
        {"duration_min": 7},
        {"color": "pink"},
    ],
)
def test_event_model_refuses_what_the_table_refuses(changes):
    with pytest.raises(ValidationError):
        _event(**changes)


def test_event_model_accepts_valid_kinds():
    _event(script_kind="saved", script_id=uuid4(), script_title="My pitch")
    _event(script_kind="ai", duration_min=10, category="sports")
    _event(repeat_kind="custom", repeat_days=[1, 3, 5], end_kind="count", end_count=5)
    _event(all_day=True, start_time=None, repeat_kind="none")


# ---------- events ----------


def test_create_get_update_delete_event(repo):
    row = repo.create_event(USER_A, _event())
    assert row.user_id == USER_A and row.schedule_set_at is not None
    assert repo.get_event(USER_A, row.id) == row
    assert repo.count_events(USER_A) == 1

    updated = repo.update_event(USER_A, row.id, ScheduleEventPatch(note="Breathe", color="sky"))
    assert updated.note == "Breathe" and updated.color == "sky"
    assert updated.start_time == row.start_time  # fields not sent stay

    assert repo.delete_event(USER_A, row.id) is True
    assert repo.get_event(USER_A, row.id) is None
    assert repo.delete_event(USER_A, row.id) is False


def test_update_that_breaks_a_check_is_refused(repo):
    row = repo.create_event(USER_A, _event())
    with pytest.raises(ValidationError):
        repo.update_event(USER_A, row.id, ScheduleEventPatch(all_day=True))
    assert repo.get_event(USER_A, row.id) == row


def test_list_events_keeps_events_that_start_by_the_end_day(repo):
    early = repo.create_event(USER_A, _event())
    repo.create_event(USER_A, _event(start_date=DAY + timedelta(days=10)))
    assert repo.list_events(USER_A, DAY + timedelta(days=5)) == [early]


def test_user_cannot_see_or_change_another_users_event(repo):
    row = repo.create_event(USER_A, _event())
    assert repo.get_event(USER_B, row.id) is None
    assert repo.list_events(USER_B, DAY) == []
    assert repo.count_events(USER_B) == 0
    assert repo.update_event(USER_B, row.id, ScheduleEventPatch(note="x")) is None
    assert repo.delete_event(USER_B, row.id) is False
    assert repo.split_event(USER_B, row.id, DAY, None) == []
    with pytest.raises(StorageError):
        repo.upsert_checkin(USER_B, row.id, DAY, NOW)


# ---------- this and following ----------


def test_split_event_ends_the_old_one_and_adds_the_new_one(repo):
    old = repo.create_event(USER_A, _event(end_kind="count", end_count=5))
    later = DAY + timedelta(days=2)
    rows = repo.split_event(USER_A, old.id, later - timedelta(days=1), _event(start_date=later))
    assert [r.id for r in rows][0] == old.id and len(rows) == 2
    cut, new = rows
    assert (cut.end_kind, cut.end_until, cut.end_count) == ("until", DAY + timedelta(days=1), None)
    assert new.start_date == later and new.user_id == USER_A
    assert repo.count_events(USER_A) == 2


def test_split_event_without_a_new_event_only_cuts(repo):
    old = repo.create_event(USER_A, _event())
    rows = repo.split_event(USER_A, old.id, DAY + timedelta(days=3), None)
    assert len(rows) == 1 and rows[0].end_until == DAY + timedelta(days=3)
    assert repo.count_events(USER_A) == 1


# ---------- check-ins ----------


def test_upsert_checkin_keeps_the_first_checkin_time(repo):
    event = repo.create_event(USER_A, _event())
    first = repo.upsert_checkin(USER_A, event.id, DAY, NOW)
    again = repo.upsert_checkin(USER_A, event.id, DAY, NOW + timedelta(minutes=20))
    assert again.checkin_at == first.checkin_at == NOW
    assert repo.list_checkins(USER_A, DAY, DAY) == [first]
    assert repo.list_checkins(USER_B, DAY, DAY) == []


def test_mark_done_sets_done_once(repo):
    event = repo.create_event(USER_A, _event())
    assert repo.mark_done(USER_A, event.id, DAY, uuid4(), NOW) is None  # no check-in yet
    repo.upsert_checkin(USER_A, event.id, DAY, NOW)
    session_id = uuid4()
    done = repo.mark_done(USER_A, event.id, DAY, session_id, NOW + timedelta(minutes=5))
    assert done.session_id == session_id and done.done_at == NOW + timedelta(minutes=5)
    again = repo.mark_done(USER_A, event.id, DAY, uuid4(), NOW + timedelta(hours=1))
    assert again == done


# ---------- reminders ----------


def test_claim_reminder_only_the_first_call_wins(repo):
    event = repo.create_event(USER_A, _event())
    assert repo.claim_reminder(event.id, DAY, "failed", NOW) is True
    assert repo.claim_reminder(event.id, DAY, "failed", NOW) is False
    repo.set_reminder_status(event.id, DAY, "sent", NOW)
    [row] = repo.list_reminders(USER_A, DAY, DAY)
    assert (row.status, row.sent_at) == ("sent", NOW)
    assert repo.list_reminders(USER_B, DAY, DAY) == []


def test_claim_reminder_at_the_same_moment_has_one_winner(repo):
    event = repo.create_event(USER_A, _event())
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = [pool.submit(repo.claim_reminder, event.id, DAY, "failed", NOW) for _ in range(16)]
    wins = [claim.result() for claim in claims]
    assert wins.count(True) == 1


def test_reminder_candidates_cover_every_user(repo):
    a = repo.create_event(USER_A, _event())
    b = repo.create_event(USER_B, _event())
    repo.create_event(USER_B, _event(start_date=DAY + timedelta(days=30)))
    assert {r.id for r in repo.list_reminder_candidates(DAY)} == {a.id, b.id}


# ---------- cascade ----------


def test_deleting_an_event_removes_its_checkins_and_reminders(repo):
    event = repo.create_event(USER_A, _event())
    repo.upsert_checkin(USER_A, event.id, DAY, NOW)
    repo.claim_reminder(event.id, DAY, "sent", NOW)
    repo.delete_event(USER_A, event.id)
    assert repo.list_checkins(USER_A, DAY, DAY) == []
    # the event is gone, so a new claim fails like the foreign key
    with pytest.raises(StorageError):
        repo.claim_reminder(event.id, DAY, "sent", NOW)


def test_delete_user_schedule_keeps_other_users(repo):
    a = repo.create_event(USER_A, _event())
    repo.create_event(USER_A, _event())
    b = repo.create_event(USER_B, _event())
    repo.upsert_checkin(USER_A, a.id, DAY, NOW)
    assert repo.delete_user_schedule(USER_A) == 2
    assert repo.count_events(USER_A) == 0 and repo.list_checkins(USER_A, DAY, DAY) == []
    assert repo.get_event(USER_B, b.id) == b


def test_memory_repos_have_a_schedule_repo():
    assert isinstance(build_memory_repos().schedule, MemoryScheduleRepo)


# ---------- Supabase repository, fake client ----------


def _event_row(user_id=USER_A) -> dict:
    return _event().model_dump(mode="json") | {
        "id": str(uuid4()),
        "user_id": str(user_id),
        "schedule_set_at": NOW.isoformat(),
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }


def test_supabase_create_event_lets_the_database_set_schedule_set_at():
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [_event_row()]
    row = SupabaseScheduleRepo(client).create_event(USER_A, _event())
    assert row.user_id == USER_A
    sent = client.table.return_value.insert.call_args.args[0]
    assert "schedule_set_at" not in sent and sent["user_id"] == str(USER_A)
    client.table.assert_called_with("schedule_events")


@pytest.mark.parametrize(("data", "won"), [([{"event_id": "x"}], True), ([], False)])
def test_supabase_claim_reminder_is_true_only_when_a_row_was_inserted(data, won):
    client = MagicMock()
    upsert = client.table.return_value.upsert
    upsert.return_value.execute.return_value.data = data
    assert SupabaseScheduleRepo(client).claim_reminder(uuid4(), DAY, "failed", NOW) is won
    assert upsert.call_args.kwargs == {"on_conflict": "event_id,occ_day", "ignore_duplicates": True}


def test_supabase_split_event_calls_the_sql_function():
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [_event_row(), _event_row()]
    event_id = uuid4()
    rows = SupabaseScheduleRepo(client).split_event(USER_A, event_id, DAY, _event())
    assert len(rows) == 2
    name, params = client.rpc.call_args.args
    assert name == "split_schedule_event"
    assert params["p_event_id"] == str(event_id) and params["p_end_until"] == "2026-12-01"
    assert params["p_new_event"]["start_time"] == "19:30:00"


def test_supabase_errors_become_storage_errors():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.limit.return_value
    query.execute.side_effect = RuntimeError("network down")
    with pytest.raises(StorageError):
        SupabaseScheduleRepo(client).count_events(USER_A)


# ---------- email_for_user ----------


def test_memory_email_for_user():
    auth = MemoryAuthProvider()
    user_id = auth.create_user("ana@example.com", "password-1")
    assert auth.email_for_user(user_id) == "ana@example.com"
    assert auth.email_for_user(uuid4()) is None
