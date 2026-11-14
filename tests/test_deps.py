from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from src.app.config import settings
from src.app.deps import DEV_FALLBACK_USER_ID, get_current_user


def test_get_current_user_dev_returns_dev_user(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", str(user_id))

    assert get_current_user().id == user_id


def test_get_current_user_non_dev_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "dev_user_id", str(uuid4()))

    with pytest.raises(HTTPException) as exc:
        get_current_user()
    assert exc.value.status_code == 401


def test_get_current_user_missing_dev_user_id_returns_fallback(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", "")

    assert get_current_user().id == UUID(DEV_FALLBACK_USER_ID)


def test_get_current_user_non_dev_without_dev_user_id_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "dev_user_id", "")

    with pytest.raises(HTTPException) as exc:
        get_current_user()
    assert exc.value.status_code == 401


def test_get_current_user_invalid_dev_user_id_raises_401(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", "not-a-uuid")

    with pytest.raises(HTTPException) as exc:
        get_current_user()
    assert exc.value.status_code == 401
