"""The server must refuse to start when a required key is missing."""

import pytest
from fastapi.testclient import TestClient

from src.app import main
from src.app.config import Settings, missing_required_settings


def _settings(**overrides) -> Settings:
    base = dict(
        deepgram_api_keys="dg", gladia_api_keys="gl", groq_api_keys="gq",
        app_env="dev", supabase_url="", supabase_service_key="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_dev_with_all_keys_and_memory_storage_is_complete():
    assert missing_required_settings(_settings()) == []


@pytest.mark.parametrize(
    ("field", "env_name"),
    [("deepgram_api_keys", "DEEPGRAM_API_KEYS"),
     ("gladia_api_keys", "GLADIA_API_KEYS"),
     ("groq_api_keys", "GROQ_API_KEYS")],
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
    monkeypatch.setattr(main.settings, "deepgram_api_keys", [])
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEYS"):
        with TestClient(main.app):
            pass


def test_app_starts_when_keys_are_present(monkeypatch):
    for field in ("deepgram_api_keys", "gladia_api_keys", "groq_api_keys"):
        monkeypatch.setattr(main.settings, field, ["set"])
    monkeypatch.setattr(main.settings, "app_env", "dev")
    monkeypatch.setattr(main.settings, "supabase_url", "")
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200


# ---------- T1: SUPABASE_URL must be the project URL ----------


def test_supabase_url_trailing_slash_is_removed():
    assert _settings(supabase_url=" https://x.supabase.co/ ").supabase_url == "https://x.supabase.co"


@pytest.mark.parametrize("suffix", ["/rest/v1", "/rest/v1/", "/auth/v1", "/storage/v1/"])
def test_supabase_url_with_api_path_is_refused(suffix):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="project URL"):
        _settings(supabase_url="https://x.supabase.co" + suffix)


def test_env_file_is_the_repo_root_env():
    from src.app.config import ENV_FILE, REPO_ROOT

    assert (REPO_ROOT / "pyproject.toml").is_file()  # parents[2] of config.py is the repo root
    assert ENV_FILE == REPO_ROOT / ".env"
