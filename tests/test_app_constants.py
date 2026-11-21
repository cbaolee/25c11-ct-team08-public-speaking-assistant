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
        f"[storage]\nretention_full_sessions = {retention}\nsigned_url_ttl_s = {ttl}\n"
        "max_compact_sessions = 30\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(constants, "CONSTANTS", constants.load_constants(toml))
    monkeypatch.setattr(config, "CONSTANTS", constants.CONSTANTS)
    monkeypatch.delenv("RETENTION_FULL_SESSIONS", raising=False)
    monkeypatch.delenv("SIGNED_URL_TTL_S", raising=False)
    monkeypatch.delenv("MAX_COMPACT_SESSIONS", raising=False)


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


def test_max_compact_sessions_follows_toml_and_env(monkeypatch, tmp_path):
    _use_toml(monkeypatch, tmp_path, retention=5, ttl=900)
    assert Settings(_env_file=None).max_compact_sessions == 30
    monkeypatch.setenv("MAX_COMPACT_SESSIONS", "12")
    assert Settings(_env_file=None).max_compact_sessions == 12


def test_module_constants_match_repo_toml():
    data = constants.load_constants()
    assert config.max_audio_seconds == data["audio"]["max_audio_seconds"]
    assert config.MIN_PAUSE_S == data["audio"]["min_pause_s"]
    assert config.max_script_words == data["script"]["max_script_words"]
    assert config.max_saved_scripts == data["storage"]["max_saved_scripts"]


def test_api_config_returns_web_section():
    response = TestClient(main.app).get("/api/config")
    assert response.status_code == 200
    body = response.json()
    data = constants.load_constants()
    assert all(body[key] == value for key, value in data["web"].items())
    assert body["max_saved_scripts"] == config.max_saved_scripts
    assert body["script_title_max_chars"] == config.script_title_max_chars
    assert body["max_pdf_size_bytes"] == data["script"]["max_pdf_size_bytes"]
    assert body["max_pdf_pages"] == data["script"]["max_pdf_pages"]
    assert body["auth"] == {
        key: data["auth"][key] for key in ("otp_length", "resend_cooldown_s")
    }
    assert body["retention"]["insufficient_days"] == data["retention"]["insufficient_days"] == 7
    assert body["retry"]["sentence_min_error_ratio"] == 0.30
    for key in ("stt_estimate_tau_s", "done_close_delay_ms", "announce_step_pct"):
        assert body["evaluate_job"][key] == data["evaluate_job"][key]
    assert body["coach"]["max_focus_items"] == data["coach"]["max_focus_items"]


def test_ui_reads_every_web_key():
    ui = UI_FILE.read_text(encoding="utf-8")
    missing = [key for key in constants.CONSTANTS["web"] if "c." + key not in ui]
    assert missing == []


def test_static_files_are_revalidated():
    response = TestClient(main.app).get("/static/css/base.css")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
