"""Unconfirmed accounts expire 60 min after the last code (ADR-011), MemoryAuth side."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import src.app.main as main
from src.app.auth import (
    EmailNotConfirmedError,
    InvalidCredentialsError,
    MemoryAuthProvider,
    OtpInvalidError,
    get_auth,
)
from src.app.constants import CONSTANTS
from src.app.db.factory import build_memory_repos, get_repos
from src.app.routes.auth import reset_auth_limiters

EMAIL, PASSWORD = "alice@example.com", "password-1"
TTL_S = CONSTANTS["auth"]["unconfirmed_ttl_min"] * 60


def _provider(now, **kwargs):
    codes = iter(f"{i:06d}" for i in range(100, 200))
    return MemoryAuthProvider(
        code_factory=lambda: next(codes), clock=lambda: now[0], otp_ttl_s=10**6, **kwargs
    )


def test_default_ttl_comes_from_constants():
    assert MemoryAuthProvider()._unconfirmed_ttl_s == 3600


def test_unconfirmed_account_is_gone_after_ttl():
    now = [0.0]
    purged = []
    provider = _provider(now, on_purge=purged.append)
    first = provider.sign_up(EMAIL, PASSWORD)
    now[0] = TTL_S - 1
    with pytest.raises(EmailNotConfirmedError):
        provider.sign_in(EMAIL, PASSWORD)  # still there just before the deadline
    now[0] = TTL_S
    with pytest.raises(InvalidCredentialsError):
        provider.sign_in(EMAIL, PASSWORD)  # same answer as an unknown email
    assert purged == [UUID(first.user_id)]


def test_resend_moves_the_deadline():
    now = [0.0]
    provider = _provider(now)
    provider.sign_up(EMAIL, PASSWORD)
    now[0] = TTL_S - 60
    provider.resend_signup_otp(EMAIL)
    now[0] = TTL_S + 60  # past the first deadline, not past the one after Resend
    with pytest.raises(EmailNotConfirmedError):
        provider.sign_in(EMAIL, PASSWORD)
    now[0] = 2 * TTL_S - 60
    with pytest.raises(InvalidCredentialsError):
        provider.sign_in(EMAIL, PASSWORD)


def test_confirmed_accounts_are_never_purged():
    now = [0.0]
    provider = MemoryAuthProvider(code_factory=lambda: "123456", clock=lambda: now[0])
    provider.sign_up(EMAIL, PASSWORD)
    provider.verify_signup_otp(EMAIL, "123456")
    now[0] = 10 * TTL_S
    assert provider.sign_in(EMAIL, PASSWORD).access_token


def test_after_purge_verify_is_invalid_resend_is_silent_and_signup_is_new():
    now = [0.0]
    provider = _provider(now)
    first = provider.sign_up(EMAIL, PASSWORD)
    now[0] = TTL_S
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "000100")  # the right code of the purged account
    provider.resend_signup_otp(EMAIL)  # no error, nothing sent
    again = provider.sign_up(EMAIL, PASSWORD)
    assert again.created and again.needs_verification
    assert again.user_id != first.user_id


def test_api_after_purge_keeps_existing_error_codes_and_drops_profile():
    now = [0.0]
    repos = build_memory_repos()
    provider = MemoryAuthProvider(
        code_factory=lambda: "123456", clock=lambda: now[0],
        on_purge=repos.profiles.delete_profile,
    )
    main.app.dependency_overrides[get_auth] = lambda: provider
    main.app.dependency_overrides[get_repos] = lambda: repos
    client = TestClient(main.app)
    r = client.post("/api/auth/signup", json={
        "email": EMAIL, "password": PASSWORD, "target_accent": "American",
    })
    user_id = UUID(r.json()["user_id"])
    assert repos.profiles.get_profile(user_id) is not None
    now[0] = TTL_S
    verify = client.post("/api/auth/verify-otp", json={"email": EMAIL, "token": "123456"})
    assert verify.status_code == 422 and verify.json()["error_code"] == "otp_invalid"
    assert repos.profiles.get_profile(user_id) is None
    reset_auth_limiters()  # sign up started the resend cooldown (real clock)
    resend = client.post("/api/auth/resend-otp", json={"email": EMAIL})
    assert resend.status_code == 200 and resend.json() == {"sent": True}  # hides existence
    again = client.post("/api/auth/signup", json={
        "email": EMAIL, "password": PASSWORD, "target_accent": "British",
    })
    assert again.status_code == 201 and UUID(again.json()["user_id"]) != user_id
