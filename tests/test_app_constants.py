"""app_constants.toml: Settings defaults come from it.

.env overrides it, /api/config serves [web].
"""

from pathlib import Path

from fastapi.testclient import TestClient

from src.app import config, constants, main
from src.app.config import Settings

UI_FILE = Path(__file__).resolve().parents[1] / "src" / "web" / "static" / "js" / "main.js"


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
    assert s.signed_url_ttl_s == 900  # not overridden: still from TOML


def test_module_constants_match_repo_toml():
    data = constants.load_constants()
    assert config.max_audio_seconds == data["audio"]["max_audio_seconds"]
    assert config.MIN_PAUSE_S == data["audio"]["min_pause_s"]
    assert config.max_script_words == data["script"]["max_script_words"]
    assert config.max_saved_scripts == data["storage"]["max_saved_scripts"]


def test_api_config_returns_web_section():
    response = TestClient(main.app).get("/api/config")
    assert response.status_code == 200
    assert all(
        response.json()[key] == value for key, value in constants.load_constants()["web"].items()
    )
    assert response.json()["retry"]["sentence_min_error_ratio"] == 0.30
    job = response.json()["evaluate_job"]
    for key in ("stt_estimate_tau_s", "done_close_delay_ms", "announce_step_pct"):
        assert job[key] == constants.load_constants()["evaluate_job"][key]
    assert response.json()["coach"]["max_focus_items"] == (
        constants.load_constants()["coach"]["max_focus_items"]
    )


def test_ui_reads_every_web_key():
    ui = UI_FILE.read_text(encoding="utf-8")
    missing = [key for key in constants.CONSTANTS["web"] if "c." + key not in ui]
    assert missing == []
