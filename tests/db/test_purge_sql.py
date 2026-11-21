import re
from pathlib import Path

from src.app.constants import CONSTANTS


def test_purge_sql_matches_retention_constant():
    path = Path(__file__).resolve().parents[2] / "db/migrations"
    path = path / "0005_purge_insufficient_sessions.sql"
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
