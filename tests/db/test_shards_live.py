"""Live check of the core project and every shard project (ADR-012).

Skipped by default. Run with:
    uv run pytest -m integration tests/db/test_shards_live.py
Needs SUPABASE_URL, SUPABASE_SERVICE_KEY and SUPABASE_SHARDS in .env, migration 0010 on the
core and migration_shard/0001 on every shard.

It creates 10 test accounts (emails TEST_EMAIL_PATTERN), gives each a profile, a 10 s
baseline and one short practice session, checks that every shard project received a
session, then deletes everything it created: auth users, accounts, profiles, baselines,
sessions in every project and the users' folders in every bucket of every project.
Leftovers of an interrupted run are deleted before and after the test, matched by email.
"""

import math
import struct
import tempfile
import wave
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from src.app.auth import SupabaseAuthProvider
from src.app.config import CORE_SHARD_REF, settings
from src.app.db import factory
from src.app.db.models import NewBaseline, NewSession, ProfileUpsert, build_object_path
from src.app.db.session_helpers import encode_opus
from src.app.db.supabase_repo import SupabaseAudioStore, SupabaseSessionRepo

pytestmark = pytest.mark.integration

USERS = 10
EMAIL_PREFIX, EMAIL_DOMAIN = "psc-shardcheck-", "@example.com"
TEST_EMAIL_PATTERN = f"{EMAIL_PREFIX}NN{EMAIL_DOMAIN}"
PASSWORD = "shard-check-" + uuid4().hex[:12]
BUCKETS = ("audio", "series", "baselines", "avatars")
SESSION_BUCKETS = ("audio", "series")


def _need_config() -> None:
    if not settings.supabase_url or not settings.supabase_service_key:
        pytest.skip("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    if not settings.supabase_shards:
        pytest.skip("SUPABASE_SHARDS not set")


def _project_refs() -> list[str]:
    return [CORE_SHARD_REF, *settings.supabase_shards]


def _label(ref: str) -> str:
    shard = settings.supabase_shards.get(ref)
    return "core" if shard is None else f"shard {shard.number:02d} ({ref})"


def _wav_10s(path: Path) -> None:
    """10 s of a quiet 220 Hz tone, 16 kHz mono 16-bit."""
    rate = 16_000
    frames = b"".join(
        struct.pack("<h", int(3000 * math.sin(2 * math.pi * 220 * i / rate)))
        for i in range(rate * 10)
    )
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)


def _test_users() -> list[UUID]:
    """Auth users whose email matches the test pattern (all pages)."""
    admin = factory.get_supabase_client().auth.admin
    found, page = [], 1
    while True:
        users = admin.list_users(page=page, per_page=100)
        for user in users:
            email = (user.email or "").lower()
            if email.startswith(EMAIL_PREFIX) and email.endswith(EMAIL_DOMAIN):
                found.append(UUID(user.id))
        if len(users) < 100:
            return found
        page += 1


def _delete_everywhere(user_id: UUID) -> None:
    """Delete one test user's data in every project, then the auth user. Safe to repeat."""
    for ref in _project_refs():
        client = factory.get_shard_client(ref)
        store = SupabaseAudioStore(client)
        buckets = BUCKETS if ref == CORE_SHARD_REF else SESSION_BUCKETS
        for bucket in buckets:
            store.delete_user_folder(user_id, bucket)
        SupabaseSessionRepo(client).delete_user_sessions(user_id)
    # Cascade removes accounts, profiles, baselines, scripts and core sessions.
    _auth().delete_user(user_id)


def _auth() -> SupabaseAuthProvider:
    return SupabaseAuthProvider(settings.supabase_url, settings.supabase_service_key)


def _leftovers(user_ids: list[UUID]) -> list[str]:
    """Everything of these users still found anywhere; empty means clean."""
    ids = [str(u) for u in user_ids]
    left = []
    core = factory.get_supabase_client()
    for table, column in (("accounts", "user_id"), ("profiles", "id"), ("baselines", "user_id")):
        rows = core.table(table).select(column).in_(column, ids).execute().data
        if rows:
            left.append(f"core {table}: {len(rows)} rows")
    for ref in _project_refs():
        client = factory.get_shard_client(ref)
        rows = client.table("sessions").select("id").in_("user_id", ids).execute().data
        if rows:
            left.append(f"{_label(ref)} sessions: {len(rows)} rows")
        store = SupabaseAudioStore(client)
        buckets = BUCKETS if ref == CORE_SHARD_REF else SESSION_BUCKETS
        for user_id in user_ids:
            for bucket in buckets:
                if store.list_user_files(user_id, bucket):
                    left.append(f"{_label(ref)} bucket {bucket}: files of {user_id}")
    still = set(_test_users()) & set(user_ids)
    if still:
        left.append(f"auth users: {len(still)}")
    return left


@pytest.fixture
def clean_slate():
    _need_config()
    factory.get_shard_client.cache_clear()
    for user_id in _test_users():  # an earlier run that stopped half way
        _delete_everywhere(user_id)
    created: list[UUID] = []
    yield created
    for user_id in set(created) | set(_test_users()):
        _delete_everywhere(user_id)
    assert _leftovers(created) == []


def test_every_project_is_reachable():
    _need_config()
    factory.get_shard_client.cache_clear()
    problems = []
    for ref in _project_refs():
        client = factory.get_shard_client(ref)
        try:
            client.table("sessions").select("id").limit(1).execute()
            for bucket in SESSION_BUCKETS:
                client.storage.from_(bucket).list("", {"limit": 1})
        except Exception as err:  # paused project, wrong key, migration not run
            problems.append(f"{_label(ref)}: {type(err).__name__}: {err}")
    try:
        factory.get_supabase_client().table("accounts").select("user_id").limit(1).execute()
    except Exception as err:
        problems.append(f"core accounts (run 0010_accounts.sql): {err}")
    assert problems == []


def test_ten_users_fill_every_shard_then_leave_no_trace(clean_slate):
    repos = factory.build_supabase_repos()
    auth = _auth()
    used: dict[UUID, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        wav, opus = Path(tmp) / "tone.wav", Path(tmp) / "tone.webm"
        _wav_10s(wav)
        encode_opus(wav, opus)
        audio = opus.read_bytes()

        for n in range(1, USERS + 1):
            email = f"{EMAIL_PREFIX}{n:02d}{EMAIL_DOMAIN}"
            user_id = auth.create_user(email, PASSWORD)
            clean_slate.append(user_id)
            assert auth.sign_in(email, PASSWORD).user_id == user_id  # core Auth works

            repos.profiles.upsert_profile(user_id, ProfileUpsert(target_accent="American"))

            baseline_id = uuid4()
            baseline_path = build_object_path(user_id, baseline_id, ".webm")
            repos.files.upload_file(user_id, "baselines", baseline_path, audio, "audio/webm")
            repos.baselines.replace_current_baseline(
                user_id,
                NewBaseline(id=baseline_id, hesitation_threshold_s=0.9, audio_path=baseline_path),
            )

            session_id = uuid4()
            audio_path = build_object_path(user_id, session_id, ".webm")
            repos.files.upload_file(user_id, "audio", audio_path, audio, "audio/webm")
            repos.sessions.create_session(
                user_id,
                NewSession(
                    id=session_id,
                    script_snapshot="Shard check.",
                    status="ok",
                    result={"overall": 80.0},
                    result_schema_version="2.0",
                    overall=80.0,
                    audio_path=audio_path,
                    audio_duration_s=10.0,
                    baseline_id=baseline_id,
                ),
            )

            shard_ref = repos.accounts.get_shard(user_id)
            used[user_id] = shard_ref
            # Read back through the router and straight from the chosen project
            assert repos.sessions.get_session(user_id, session_id) is not None
            direct = SupabaseSessionRepo(factory.get_shard_client(shard_ref))
            assert direct.get_session(user_id, session_id) is not None
            assert repos.files.download_file(user_id, "audio", audio_path) == audio
            assert repos.baselines.get_current_baseline(user_id).id == baseline_id

    missing = set(settings.supabase_shards) - set(used.values())
    assert not missing, f"no session landed in: {[_label(r) for r in missing]}"
