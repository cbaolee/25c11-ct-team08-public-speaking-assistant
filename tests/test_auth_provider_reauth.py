"""verify_password (ADR-011): re-auth without touching the user's own session."""

from types import SimpleNamespace

import httpx
import pytest
from supabase_auth.errors import AuthApiError

from src.app.auth import (
    AuthRateLimitedError,
    AuthUnavailableError,
    MemoryAuthProvider,
    SupabaseAuthProvider,
)

EMAIL = "alice@example.com"
PASSWORD = "password-1"


def test_memory_verify_password_matches_only_the_right_password():
    provider = MemoryAuthProvider(require_email_otp=False)
    provider.sign_up(EMAIL, PASSWORD)
    assert provider.verify_password(EMAIL, PASSWORD) is True
    assert provider.verify_password(" Alice@Example.com ", PASSWORD) is True
    assert provider.verify_password(EMAIL, "password-2") is False
    assert provider.verify_password("nobody@example.com", PASSWORD) is False


def test_memory_verify_password_creates_no_session():
    provider = MemoryAuthProvider(require_email_otp=False)
    provider.sign_up(EMAIL, PASSWORD)
    provider.verify_password(EMAIL, PASSWORD)
    assert provider._access == {} and provider._refresh == {}


def _supabase(monkeypatch, sign_in):
    provider = SupabaseAuthProvider("https://example.supabase.co", "service-key")
    revoked = []
    provider._admin_client = SimpleNamespace(
        admin=SimpleNamespace(sign_out=lambda token, scope: revoked.append((token, scope)))
    )
    clients = []

    def new_client():
        clients.append(SimpleNamespace(sign_in_with_password=sign_in))
        return clients[-1]

    monkeypatch.setattr(provider, "_new_client", new_client)
    return provider, revoked, clients


def test_supabase_verify_password_revokes_the_new_session(monkeypatch):
    def sign_in(credentials):
        assert credentials == {"email": EMAIL, "password": PASSWORD}
        return SimpleNamespace(session=SimpleNamespace(access_token="tmp-token"), user=None)

    provider, revoked, clients = _supabase(monkeypatch, sign_in)
    assert provider.verify_password(EMAIL, PASSWORD) is True
    assert len(clients) == 1  # a throwaway client, not the shared admin client
    assert revoked == [("tmp-token", "local")]


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        (AuthApiError("Invalid login credentials", 400, "invalid_credentials"), False),
        (AuthApiError("Too many", 429, "over_request_rate_limit"), AuthRateLimitedError),
        (AuthApiError("boom", 500, "unexpected_failure"), AuthUnavailableError),
        (httpx.ConnectError("down"), AuthUnavailableError),
    ],
)
def test_supabase_verify_password_maps_errors(monkeypatch, err, expected):
    def sign_in(credentials):
        raise err

    provider, revoked, _ = _supabase(monkeypatch, sign_in)
    if expected is False:
        assert provider.verify_password(EMAIL, "wrong") is False
    else:
        with pytest.raises(expected):
            provider.verify_password(EMAIL, "wrong")
    assert revoked == []
