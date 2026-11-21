from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from supabase_auth.errors import AuthApiError, AuthRetryableError, AuthWeakPasswordError
from supabase_auth.types import User

from src.app.auth import (
    AuthRateLimitedError,
    AuthUnavailableError,
    EmailNotConfirmedError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidEmailError,
    MemoryAuthProvider,
    OtpExpiredError,
    OtpInvalidError,
    SupabaseAuthProvider,
    WeakPasswordError,
    _created_by_this_call,
    _mask_email,
)

EMAIL = "alice@example.com"
PASSWORD = "password-1"
USER_ID = "6f1c8a4e-3f0b-4c69-9d27-2a8f1b2c3d4e"


def test_memory_signup_verify_and_credentials():
    provider = MemoryAuthProvider(code_factory=lambda: "123456")
    result = provider.sign_up(" Alice@Example.com ", PASSWORD)
    assert result.needs_verification and result.created
    with pytest.raises(EmailNotConfirmedError):
        provider.sign_in(EMAIL, PASSWORD)
    with pytest.raises(InvalidCredentialsError):
        provider.sign_in(EMAIL, "incorrect")
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "000000")
    assert "123456" not in repr(provider._accounts)
    provider.verify_signup_otp(EMAIL, "123456")
    assert str(provider.sign_in(EMAIL, PASSWORD).user_id) == result.user_id
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "123456")
    with pytest.raises(EmailTakenError):
        provider.sign_up(EMAIL, PASSWORD)


def test_memory_expiry_attempts_and_resend():
    now = [0.0]
    codes = iter(["123456", "234567", "345678"])
    provider = MemoryAuthProvider(
        code_factory=lambda: next(codes), clock=lambda: now[0], otp_ttl_s=10, max_attempts=2
    )
    provider.sign_up(EMAIL, PASSWORD)
    now[0] = 11
    with pytest.raises(OtpExpiredError):
        provider.verify_signup_otp(EMAIL, "123456")
    provider.resend_signup_otp(EMAIL)
    for _ in range(2):
        with pytest.raises(OtpInvalidError):
            provider.verify_signup_otp(EMAIL, "wrong")
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "234567")
    provider.resend_signup_otp(EMAIL)
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "234567")
    provider.verify_signup_otp(EMAIL, "345678")
    provider.resend_signup_otp(EMAIL)
    provider.resend_signup_otp("unknown@example.com")


def test_memory_repeat_signup_preserves_password_and_replaces_code():
    codes = iter(["123456", "654321"])
    provider = MemoryAuthProvider(code_factory=lambda: next(codes))
    first = provider.sign_up(EMAIL, PASSWORD)
    again = provider.sign_up(EMAIL, "other-password")
    assert again.user_id == first.user_id and not again.created and again.needs_verification
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "123456")
    provider.verify_signup_otp(EMAIL, "654321")
    provider.sign_in(EMAIL, PASSWORD)
    with pytest.raises(InvalidCredentialsError):
        provider.sign_in(EMAIL, "other-password")


def test_memory_legacy_and_otp_disabled():
    provider = MemoryAuthProvider(require_email_otp=False)
    result = provider.sign_up(EMAIL, PASSWORD)
    assert result.created and not result.needs_verification
    provider.sign_in(EMAIL, PASSWORD)
    provider.create_user("other@example.com", PASSWORD)
    provider.sign_in("other@example.com", PASSWORD)
    with pytest.raises(WeakPasswordError):
        provider.sign_up("weak@example.com", "short")
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp("unknown@example.com", "123456")


def test_memory_code_logging(caplog):
    assert _mask_email(EMAIL) == "a***@example.com"
    caplog.set_level("INFO")
    MemoryAuthProvider(code_factory=lambda: "123456").sign_up(EMAIL, PASSWORD)
    assert "123456" not in caplog.text
    MemoryAuthProvider(code_factory=lambda: "123456", log_codes=True).sign_up(EMAIL, PASSWORD)
    assert "dev OTP for a***@example.com : 123456" in caplog.text
    assert EMAIL not in caplog.text


@pytest.fixture
def supabase(monkeypatch):
    provider = SupabaseAuthProvider("https://example.test", "test-key")
    provider._admin_client = MagicMock()
    client = MagicMock()
    monkeypatch.setattr(provider, "_new_client", lambda: client)
    return provider, client


def user(**kwargs):
    now = datetime.now(UTC)
    values = dict(id=USER_ID, app_metadata={}, user_metadata={}, aud="authenticated",
                  created_at=now, confirmation_sent_at=now)
    values.update(kwargs)
    return User(**values)


def test_supabase_signup_and_session_revocation(supabase):
    provider, client = supabase
    account = user()
    client.sign_up.return_value = SimpleNamespace(user=account, session=None)
    result = provider.sign_up(EMAIL, PASSWORD)
    assert (result.user_id, result.needs_verification, result.created) == (USER_ID, True, True)
    account.email_confirmed_at = account.created_at
    session = SimpleNamespace(access_token="access")
    client.sign_up.return_value = SimpleNamespace(user=account, session=session)
    assert not provider.sign_up(EMAIL, PASSWORD).needs_verification
    provider._admin_client.admin.sign_out.assert_called_with("access", scope="local")
    account.identities = []
    with pytest.raises(EmailTakenError):
        provider.sign_up(EMAIL, PASSWORD)
    client.sign_up.return_value = SimpleNamespace(user=None, session=None)
    with pytest.raises(AuthUnavailableError):
        provider.sign_up(EMAIL, PASSWORD)


def test_creation_timestamps(supabase):
    provider, client = supabase
    account = user(confirmation_sent_at=datetime.now(UTC) + timedelta(days=1))
    client.sign_up.return_value = SimpleNamespace(user=account, session=None)
    assert not provider.sign_up(EMAIL, PASSWORD).created
    assert not _created_by_this_call(user(confirmation_sent_at=None))
    assert not _created_by_this_call(SimpleNamespace(created_at=None, confirmation_sent_at=None,
                                                     email_confirmed_at=None))


@pytest.mark.parametrize(("error", "expected"), [
    (AuthWeakPasswordError("weak", 422, ["length"]), WeakPasswordError),
    (AuthApiError("exists", 422, "user_already_exists"), EmailTakenError),
    (AuthApiError("rate", 429, "over_email_send_rate_limit"), AuthRateLimitedError),
    (AuthRetryableError("timeout", 0), AuthUnavailableError),
    (AuthApiError("bad", 400, "email_address_invalid"), InvalidEmailError),
])
def test_supabase_signup_errors(supabase, error, expected):
    provider, client = supabase
    client.sign_up.side_effect = error
    with pytest.raises(expected):
        provider.sign_up(EMAIL, PASSWORD)


def test_supabase_otp_disabled(supabase):
    provider, client = supabase
    provider._require_email_otp = False
    provider._admin_client.admin.create_user.return_value = SimpleNamespace(user=user())
    result = provider.sign_up(EMAIL, PASSWORD)
    assert result.created and not result.needs_verification and result.user_id == USER_ID
    client.sign_up.assert_not_called()
    provider._admin_client.admin.create_user.assert_called_once()


def test_supabase_verify_and_resend(supabase):
    provider, client = supabase
    client.verify_otp.side_effect = AuthApiError("invalid", 403, "otp_expired")
    with pytest.raises(OtpInvalidError):
        provider.verify_signup_otp(EMAIL, "123456")
    client.verify_otp.side_effect = None
    client.verify_otp.return_value = SimpleNamespace(session=SimpleNamespace(access_token="token"))
    assert provider.verify_signup_otp(EMAIL, "123456") is None
    user_id = "11111111-1111-4111-8111-111111111111"
    client.verify_otp.return_value = SimpleNamespace(
        session=SimpleNamespace(access_token="token"), user=SimpleNamespace(id=user_id)
    )
    assert str(provider.verify_signup_otp(EMAIL, "123456")) == user_id
    provider._admin_client.admin.sign_out.assert_called_with("token", scope="local")
    client.resend.side_effect = AuthApiError("bad", 400, "validation_failed")
    assert provider.resend_signup_otp(EMAIL) is None
    client.resend.side_effect = AuthApiError("rate", 429, "over_request_rate_limit")
    with pytest.raises(AuthRateLimitedError):
        provider.resend_signup_otp(EMAIL)


@pytest.mark.parametrize(("code", "expected"), [
    ("email_not_confirmed", EmailNotConfirmedError),
    ("invalid_credentials", InvalidCredentialsError),
])
def test_supabase_sign_in_errors(supabase, code, expected):
    provider, client = supabase
    client.sign_in_with_password.side_effect = AuthApiError("error", 400, code)
    with pytest.raises(expected):
        provider.sign_in(EMAIL, PASSWORD)


@pytest.mark.parametrize("error", [
    AuthRetryableError("timeout", 0), AuthApiError("down", 500, "internal")
])
def test_verify_outage(supabase, error):
    provider, client = supabase
    client.verify_otp.side_effect = error
    with pytest.raises(AuthUnavailableError):
        provider.verify_signup_otp(EMAIL, "123456")


def test_resend_outage(supabase):
    provider, client = supabase
    client.resend.side_effect = AuthRetryableError("timeout", 0)
    with pytest.raises(AuthUnavailableError):
        provider.resend_signup_otp(EMAIL)


def test_signup_session_unconfirmed(supabase):
    provider, client = supabase
    client.sign_up.return_value = SimpleNamespace(
        user=user(email_confirmed_at=None), session=SimpleNamespace(access_token="token")
    )
    assert provider.sign_up(EMAIL, PASSWORD).needs_verification
