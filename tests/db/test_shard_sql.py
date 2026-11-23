"""The shard migrations must keep the same sessions columns as the core project (ADR-012)."""

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "db/migrations"


def _read(name: str) -> str:
    data = (MIGRATIONS / name).read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    return data.decode("utf-8")


def _sessions_columns(sql: str) -> list[str]:
    body = re.search(r"create table public\.sessions \((.*?)\n\);", sql, re.S)
    assert body is not None
    return [line.split()[0] for line in body.group(1).strip().splitlines() if line.strip()]


def test_shard_sessions_has_the_core_columns():
    core = _sessions_columns(_read("0001_init.sql"))
    shard = _sessions_columns(_read("shard/0001_sessions.sql"))
    assert shard == core


def test_shard_sessions_has_no_foreign_key_and_no_policy():
    sql = _read("shard/0001_sessions.sql")
    assert "references" not in sql.lower()
    assert "create policy" not in sql.lower()
    assert "enable row level security" in sql
    assert "('audio', 'audio', false), ('series', 'series', false)" in sql


def test_accounts_migration_backfills_core_and_is_rerunnable():
    sql = _read("0010_accounts.sql")
    assert "create table if not exists public.accounts" in sql
    assert "references auth.users(id) on delete cascade" in sql
    assert "create policy" not in sql.lower()
    backfill = r"select p\.id, 'core' from public\.profiles p\s+on conflict \(user_id\) do nothing"
    assert re.search(backfill, sql)
