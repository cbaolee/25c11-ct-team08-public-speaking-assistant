"""The server must refuse to start when a required key is missing."""

import pytest
from fastapi.testclient import TestClient

from src.app import main
from src.app.config import Settings, missing_required_settings


def _settings(**overrides) -> Settings:
    base = dict(
        deepgram_api_key="dg", gladia_api_key="gl", groq_api_key="gq",
        app_env="dev", supabase_url="", supabase_service_key="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_dev_with_all_keys_and_memory_storage_is_complete():
    assert missing_required_settings(_settings()) == []


@pytest.mark.parametrize(
    ("field", "env_name"),
    [("deepgram_api_key", "DEEPGRAM_API_KEY"),
     ("gladia_api_key", "GLADIA_API_KEY"),
     ("groq_api_key", "GROQ_API_KEY")],
)
def test_missing_api_key_is_reported(field, env_name):
    assert missing_required_settings(_settings(**{field: "  "})) == [env_name]


def test_supabase_required_outside_dev():
    assert missing_required_settings(_settings(app_env="prod")) == [
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
    ]


def test_supabase_url_without_service_key_is_reported_in_dev():
    assert missing_required_settings(_settings(supabase_url="https://x.supabase.co")) == [
        "SUPABASE_SERVICE_KEY",
    ]


def test_app_does_not_start_when_a_key_is_missing(monkeypatch):
    monkeypatch.setattr(main.settings, "deepgram_api_key", "")
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        with TestClient(main.app):
            pass


def test_app_starts_when_keys_are_present(monkeypatch):
    for field in ("deepgram_api_key", "gladia_api_key", "groq_api_key"):
        monkeypatch.setattr(main.settings, field, "set")
    monkeypatch.setattr(main.settings, "app_env", "dev")
    monkeypatch.setattr(main.settings, "supabase_url", "")
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
