"""The server must refuse to start when a required key is missing."""

import json

import pytest
from fastapi.testclient import TestClient

from src.app import main
from src.app.config import Settings, missing_required_settings


def _settings(**overrides) -> Settings:
    base = dict(
        deepgram_api_keys="dg",
        gladia_api_keys="gl",
        groq_api_keys="gq",
        app_env="dev",
        supabase_url="",
        supabase_service_key="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_dev_with_all_keys_and_memory_storage_is_complete():
    assert missing_required_settings(_settings()) == []


@pytest.mark.parametrize(
    ("field", "env_name"),
    [
        ("deepgram_api_keys", "DEEPGRAM_API_KEYS"),
        ("gladia_api_keys", "GLADIA_API_KEYS"),
        ("groq_api_keys", "GROQ_API_KEYS"),
    ],
)
def test_missing_api_key_is_reported(field, env_name):
    assert missing_required_settings(_settings(**{field: "  "})) == [env_name]


def test_supabase_required_outside_dev():
    assert missing_required_settings(_settings(app_env="prod")) == [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
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


def test_app_does_not_start_when_list_page_is_smaller_than_script_cap(monkeypatch):
    for field in ("deepgram_api_keys", "gladia_api_keys", "groq_api_keys"):
        monkeypatch.setattr(main.settings, field, ["set"])
    monkeypatch.setattr(main.settings, "app_env", "dev")
    monkeypatch.setattr(main.settings, "supabase_url", "")
    monkeypatch.setattr(main, "max_list_page_size", 4)
    monkeypatch.setattr(main, "max_saved_scripts", 5)
    with pytest.raises(RuntimeError, match="max_list_page_size"):
        with TestClient(main.app):
            pass


# ---------- T1: SUPABASE_URL must be the project URL ----------


def test_supabase_url_trailing_slash_is_removed():
    assert (
        _settings(supabase_url=" https://x.supabase.co/ ").supabase_url == "https://x.supabase.co"
    )


@pytest.mark.parametrize("suffix", ["/rest/v1", "/rest/v1/", "/auth/v1", "/storage/v1/"])
def test_supabase_url_with_api_path_is_refused(suffix):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="project URL"):
        _settings(supabase_url="https://x.supabase.co" + suffix)


def test_env_file_is_the_repo_root_env():
    from src.app.config import ENV_FILE, REPO_ROOT

    assert (REPO_ROOT / "pyproject.toml").is_file()  # parents[2] of config.py is the repo root
    assert ENV_FILE == REPO_ROOT / ".env"


# ---------- SUPABASE_SHARDS: extra projects for sessions (ADR-012) ----------

A_URL, B_URL = "https://aaaaaaaa.supabase.co", "https://bbbbbbbb.supabase.co"


def _with_shards(value):
    return _settings(
        supabase_url="https://core.supabase.co",
        supabase_service_key="core-key",
        supabase_shards=value,
    )


def test_shards_are_keyed_by_project_ref_in_env_order():
    s = _with_shards(json.dumps({B_URL + "/": " kb ", A_URL: "ka"}))
    assert list(s.supabase_shards) == ["bbbbbbbb", "aaaaaaaa"]
    b = s.supabase_shards["bbbbbbbb"]
    assert (b.number, b.url, b.service_key) == (1, B_URL, "kb")
    assert s.supabase_shards["aaaaaaaa"].number == 2  # label only: index + 1


@pytest.mark.parametrize("value", ["", "  ", "{}"])
def test_no_shards(value):
    assert _with_shards(value).supabase_shards == {}


def test_no_shards_by_default():
    assert _settings().supabase_shards == {}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("2=https://a.supabase.co|k", "JSON object"),
        ('["https://a.supabase.co", "k"]', "JSON object"),
        (json.dumps({A_URL: ""}), "needs a service key"),
        (json.dumps({A_URL: "k", A_URL + "/": "k2"}), "twice"),
        (json.dumps({A_URL + "/rest/v1": "k"}), "project URL"),
        ('{"https://core.supabase.co": "k"}', "project ref"),
        ('{"not a url": "k"}', "project ref"),
    ],
)
def test_bad_shards_are_refused(value, message):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=message):
        _settings(supabase_shards=value)


def test_shards_need_the_core_project():
    s = _settings(supabase_shards=json.dumps({A_URL: "k"}))
    assert missing_required_settings(s) == ["SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
