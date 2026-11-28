"""Static checks for the Schedule reminder pg_cron migration."""

from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "db"


def test_schedule_cron_migration_is_rerunnable_and_uses_vault():
    path = DB / "migration_main" / "0013_schedule_reminder_cron.sql"
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    sql = path.read_text(encoding="utf-8")

    assert "Applied: not yet run on Supabase" in sql
    assert "create extension if not exists pg_cron" in sql
    assert "create extension if not exists pg_net" in sql
    assert "cron.unschedule('schedule_reminders')" in sql
    assert "cron.schedule(" in sql
    assert "'*/5 * * * *'" in sql
    assert "/internal/schedule/reminders/run" in sql
    assert "X-Cron-Secret" in sql
    assert "timeout_milliseconds := 30000" in sql
    assert "vault.decrypted_secrets" in sql
    assert "name = 'schedule_app_url'" in sql
    assert "name = 'schedule_cron_secret'" in sql
