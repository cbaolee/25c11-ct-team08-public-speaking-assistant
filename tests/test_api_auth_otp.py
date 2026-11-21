import hashlib
import logging
from uuid import UUID, uuid4

import pytest
from conftest import TEST_OTP
from fastapi.testclient import TestClient

from src.app.auth import InvalidCredentialsError, MemoryAuthProvider, SignUpResult, get_auth
from src.app.db.factory import get_repos
from src.app.db.models import NewBaseline, NewSession, ProfileUpsert, StorageError
from src.app.deps import get_current_user
from src.app.main import app
from src.app.routes.auth import _resend_limiter, _verify_limiter, reset_auth_limiters

EMAIL = "otp@example.com"
PAYLOAD = {"email": EMAIL, "password": "password-1", "target_accent": "American"}


@pytest.fixture
def client():
    return TestClient(app)


def verify(client, token=TEST_OTP, email=EMAIL):
    return client.post("/api/auth/verify-otp", json={"email": email, "token": token})


def test_signup_verify_login(client):
    response = client.post("/api/auth/signup", json=PAYLOAD)
    assert response.status_code == 201 and response.json()["verification_required"] is True
    assert (
        client.post("/api/auth/login", json=PAYLOAD).json()["error_code"] == "email_not_confirmed"
    )
    for token in ("000000", "12ab56", "12345"):
        response = verify(client, token)
        assert response.status_code == 422 and response.json()["error_code"] == "otp_invalid"
    assert verify(client).json() == {
        "verified": True,
        "password_updated": None,  # no sign-up form sent with the code
        "profile_updated": None,
    }
    assert client.post("/api/auth/login", json=PAYLOAD).status_code == 200


def test_verify_limit(client):
    client.post("/api/auth/signup", json=PAYLOAD)
    for _ in range(5):
        assert verify(client, "000000").status_code == 422
    assert verify(client).status_code == 429


def test_resend_and_hash(client):
    client.post("/api/auth/signup", json=PAYLOAD)
    assert EMAIL not in _resend_limiter._hits
    assert hashlib.sha256(EMAIL.encode()).hexdigest() in _resend_limiter._hits
    assert client.post("/api/auth/resend-otp", json={"email": EMAIL}).status_code == 429
    reset_auth_limiters()
    a = client.post("/api/auth/resend-otp", json={"email": EMAIL})
    assert a.json() == {"sent": True}
    assert client.post("/api/auth/resend-otp", json={"email": EMAIL}).status_code == 429
    assert verify(client).status_code == 200
    assert EMAIL not in _verify_limiter._hits
    reset_auth_limiters()
    b = client.post("/api/auth/resend-otp", json={"email": EMAIL})
    c = client.post("/api/auth/resend-otp", json={"email": "missing@example.com"})
    assert a.status_code == b.status_code == c.status_code == 200
    assert a.json() == b.json() == c.json()


def test_repeat_signup_preserves_profile_and_password(client):
    first = client.post("/api/auth/signup", json=PAYLOAD).json()
    response = client.post(
        "/api/auth/signup", json={**PAYLOAD, "target_accent": "British", "password": "new-password"}
    )
    assert response.status_code == 200 and response.json()["verification_required"]
    resend = client.post("/api/auth/resend-otp", json={"email": EMAIL})
    assert resend.status_code == 429 and resend.json()["error_code"] == "rate_limited"
    repos = app.dependency_overrides[get_repos]()
    assert repos.profiles.get_profile(UUID(first["user_id"])).target_accent == "American"
    assert verify(client).status_code == 200
    assert client.post("/api/auth/login", json=PAYLOAD).status_code == 200
    assert client.post("/api/auth/signup", json=PAYLOAD).status_code == 409


@pytest.mark.parametrize("mode", ["new", "existing", "confirmed"])
def test_signup_failure_preserves_safe_accounts(client, monkeypatch, mode):
    auth = app.dependency_overrides[get_auth]()
    if mode == "existing":
        auth.sign_up(EMAIL, PAYLOAD["password"])
    if mode == "confirmed":
        auth = MemoryAuthProvider(require_email_otp=False)
        app.dependency_overrides[get_auth] = lambda: auth
    repos = app.dependency_overrides[get_repos]()

    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.profiles, "upsert_profile", broken)
    assert client.post("/api/auth/signup", json=PAYLOAD).status_code == 503
    if mode == "new":
        with pytest.raises(InvalidCredentialsError):
            auth.sign_in(EMAIL, PAYLOAD["password"])
    elif mode == "existing":
        auth.verify_signup_otp(EMAIL, TEST_OTP)
        assert auth.sign_in(EMAIL, PAYLOAD["password"])
    else:
        assert auth.sign_in(EMAIL, PAYLOAD["password"])


def test_config_and_no_sensitive_logs(client, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    config = client.get("/api/config").json()
    assert config["auth"] == {
        "otp_length": 6, "resend_cooldown_s": 60, "unconfirmed_ttl_min": 60
    }
    from src.app.constants import CONSTANTS

    assert all(config[k] == v for k, v in CONSTANTS["web"].items())
    repos = app.dependency_overrides[get_repos]()

    def broken(*args, **kwargs):
        raise StorageError("down")

    with monkeypatch.context() as patch:
        patch.setattr(repos.profiles, "upsert_profile", broken)
        assert client.post("/api/auth/signup", json=PAYLOAD).status_code == 503
    client.post("/api/auth/signup", json=PAYLOAD)
    assert client.post("/api/auth/login", json=PAYLOAD).status_code == 403
    verify(client)
    reset_auth_limiters()
    client.post("/api/auth/resend-otp", json={"email": EMAIL})
    client.post("/api/auth/login", json=PAYLOAD)
    assert all(
        EMAIL not in record.getMessage() and TEST_OTP not in record.getMessage()
        for record in caplog.records
    )


def test_verify_token_too_long(client):
    assert verify(client, "1" * 33).status_code == 422


@pytest.mark.parametrize("existing", [False, True])
def test_signup_profile_read_failure_preserves_account(client, monkeypatch, existing):
    auth = app.dependency_overrides[get_auth]()
    repos = app.dependency_overrides[get_repos]()
    if existing:
        result = auth.sign_up(EMAIL, PAYLOAD["password"])
        repos.profiles.upsert_profile(
            UUID(str(result.user_id)), ProfileUpsert(target_accent="British", display_name="Old")
        )

    def broken(*args, **kwargs):
        raise StorageError("down")

    with monkeypatch.context() as patch:
        patch.setattr(repos.profiles, "get_profile", broken)
        response = client.post("/api/auth/signup", json=PAYLOAD)
    assert response.status_code == 503 and response.json()["error_code"] == "profile_not_saved"
    if existing:
        assert repos.profiles.get_profile(UUID(str(result.user_id))).display_name == "Old"
    auth.verify_signup_otp(EMAIL, TEST_OTP)
    assert auth.sign_in(EMAIL, PAYLOAD["password"])


def test_consent_failure_removes_new_profile_for_existing_account(client, monkeypatch):
    auth = app.dependency_overrides[get_auth]()
    repos = app.dependency_overrides[get_repos]()
    result = auth.sign_up(EMAIL, PAYLOAD["password"])
    user_id = UUID(str(result.user_id))

    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.profiles, "set_consent", broken)
    response = client.post("/api/auth/signup", json={**PAYLOAD, "consent_recording": True})
    assert response.status_code == 503 and response.json()["error_code"] == "profile_not_saved"
    assert repos.profiles.get_profile(user_id) is None
    auth.verify_signup_otp(EMAIL, TEST_OTP)
    assert auth.sign_in(EMAIL, PAYLOAD["password"])


def test_existing_account_data_survives_signup_and_login(client, monkeypatch):
    auth = app.dependency_overrides[get_auth]()
    repos = app.dependency_overrides[get_repos]()
    user_id = auth.create_user(EMAIL, PAYLOAD["password"])
    repos.profiles.upsert_profile(
        user_id, ProfileUpsert(target_accent="British", display_name="Old")
    )
    baseline_id = uuid4()
    repos.baselines.replace_current_baseline(
        user_id, NewBaseline(id=baseline_id, hesitation_threshold_s=0.7)
    )
    session_id = uuid4()
    repos.sessions.create_session(
        user_id,
        NewSession(
            id=session_id, script_snapshot="old", status="ok", result={}, result_schema_version="2"
        ),
    )

    def broken(*args, **kwargs):
        raise StorageError("down")

    monkeypatch.setattr(repos.profiles, "upsert_profile", broken)
    monkeypatch.setattr(auth, "sign_up", lambda *args: SignUpResult(str(user_id), True, False))
    response = client.post("/api/auth/signup", json=PAYLOAD)
    assert response.status_code == 200
    assert repos.profiles.get_profile(user_id).display_name == "Old"
    assert repos.baselines.get_current_baseline(user_id).id == baseline_id
    assert repos.sessions.get_session(user_id, session_id).id == session_id
    override = app.dependency_overrides.pop(get_current_user)
    try:
        login = client.post("/api/auth/login", json=PAYLOAD)
        assert login.status_code == 200
        profile = client.get(
            "/api/profile", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
        )
        assert profile.status_code == 200 and profile.json()["display_name"] == "Old"
    finally:
        app.dependency_overrides[get_current_user] = override
