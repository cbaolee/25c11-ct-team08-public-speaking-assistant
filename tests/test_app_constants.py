"""app_constants.toml: Settings defaults come from it, .env overrides it, /api/config serves [web]."""

from pathlib import Path

from fastapi.testclient import TestClient

from src.app import config, constants, main
from src.app.config import Settings

UI_FILE = Path(__file__).resolve().parents[1] / "src" / "web" / "templates" / "demo_ui.html"


def _use_toml(monkeypatch, tmp_path, retention: int, ttl: int) -> None:
    """Point CONSTANTS at a small TOML file written for the test."""
    toml = tmp_path / "app_constants.toml"
    toml.write_text(
        f"[storage]\nretention_full_sessions = {retention}\nsigned_url_ttl_s = {ttl}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(constants, "CONSTANTS", constants.load_constants(toml))
    monkeypatch.setattr(config, "CONSTANTS", constants.CONSTANTS)
    monkeypatch.delenv("RETENTION_FULL_SESSIONS", raising=False)
    monkeypatch.delenv("SIGNED_URL_TTL_S", raising=False)


def test_settings_default_follows_toml(monkeypatch, tmp_path):
    _use_toml(monkeypatch, tmp_path, retention=5, ttl=900)
    s = Settings(_env_file=None)
    assert s.retention_full_sessions == 5
    assert s.signed_url_ttl_s == 900


def test_env_overrides_toml(monkeypatch, tmp_path):
    _use_toml(monkeypatch, tmp_path, retention=5, ttl=900)
    monkeypatch.setenv("RETENTION_FULL_SESSIONS", "20")
    s = Settings(_env_file=None)
    assert s.retention_full_sessions == 20  # .env wins
    assert s.signed_url_ttl_s == 900        # not overridden: still from TOML


def test_module_constants_match_repo_toml():
    data = constants.load_constants()
    assert config.max_audio_seconds == data["audio"]["max_audio_seconds"]
    assert config.MIN_PAUSE_S == data["audio"]["min_pause_s"]
    assert config.max_script_words == data["script"]["max_script_words"]
    assert config.max_saved_scripts == data["storage"]["max_saved_scripts"]


def test_api_config_returns_web_section():
    response = TestClient(main.app).get("/api/config")
    assert response.status_code == 200
    assert response.json() == constants.load_constants()["web"]


def test_ui_reads_every_web_key():
    ui = UI_FILE.read_text(encoding="utf-8")
    missing = [key for key in constants.CONSTANTS["web"] if "c." + key not in ui]
    assert missing == []
