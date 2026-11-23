import re
from pathlib import Path

import pytest

from src.app.constants import CONSTANTS

MIGRATIONS = Path(__file__).resolve().parents[2] / "db/migrations"


# The core project (0005) and every shard project (shard/0002) run the same job.
@pytest.mark.parametrize(
    "name", ["0005_purge_insufficient_sessions.sql", "shard/0002_purge_insufficient_sessions.sql"]
)
def test_purge_sql_matches_retention_constant(name):
    path = MIGRATIONS / name
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    sql = path.read_text(encoding="utf-8")
    interval = re.search(r"interval '(\d+) days'", sql)
    assert interval is not None
    assert int(interval.group(1)) == CONSTANTS["retention"]["insufficient_days"]
    assert "delete from public.sessions" in sql
    assert "status = 'insufficient_audio'" in sql
    assert "cron.schedule('purge_insufficient_sessions'" in sql


def test_frontend_insufficient_days_matches_retention_constant():
    path = Path(__file__).resolve().parents[2] / "src/web/static/js/state.js"
    fallback = re.search(r"insufficientDays:\s*(\d+)", path.read_text(encoding="utf-8"))
    assert fallback is not None
    assert int(fallback.group(1)) == CONSTANTS["retention"]["insufficient_days"]


def _unconfirmed_sql() -> tuple[bytes, str]:
    path = Path(__file__).resolve().parents[2] / "db/migrations"
    path = path / "0009_purge_unconfirmed_accounts.sql"
    return path.read_bytes(), path.read_text(encoding="utf-8")


def test_unconfirmed_purge_sql_matches_auth_constant():
    data, sql = _unconfirmed_sql()
    assert not data.startswith(b"\xef\xbb\xbf")
    interval = re.search(r"interval '(\d+) minutes'", sql)
    assert interval is not None
    assert int(interval.group(1)) == CONSTANTS["auth"]["unconfirmed_ttl_min"] == 60
    assert "delete from auth.users" in sql
    assert "email_confirmed_at is null" in sql
    assert "coalesce(u.confirmation_sent_at, u.created_at)" in sql
    assert "cron.schedule('purge_unconfirmed_accounts', '*/15 * * * *'" in sql
    assert re.search(r"not exists \(\s*select 1 from storage\.objects", sql)
    assert "cron.unschedule('purge_unconfirmed_accounts')" in sql


def test_frontend_unconfirmed_ttl_matches_auth_constant():
    path = Path(__file__).resolve().parents[2] / "src/web/static/js/state.js"
    fallback = re.search(r"unconfirmed_ttl_min:\s*(\d+)", path.read_text(encoding="utf-8"))
    assert fallback is not None
    assert int(fallback.group(1)) == CONSTANTS["auth"]["unconfirmed_ttl_min"]
