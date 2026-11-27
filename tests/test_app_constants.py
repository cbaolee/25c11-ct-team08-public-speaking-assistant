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
    from src import text_processing
    from src.text_processing import (
        chat_session,
        contracts,
        generator,
        parser,
        pipeline,
        template_engine,
        template_store,
    )

    data = constants.load_constants()
    s = data["script"]
    assert config.max_audio_seconds == data["audio"]["max_audio_seconds"]
    assert config.MIN_PAUSE_S == data["audio"]["min_pause_s"]
    assert config.max_script_words == s["max_script_words"]
    assert config.max_script_chars == s["max_script_chars"]
    assert config.max_turn_text_chars == s["max_turn_text_chars"]
    assert config.composer_max_words == data["web"]["composer_max_words"]
    assert config.min_pdf_size_bytes == s["min_pdf_size_bytes"]
    assert config.max_pdf_size_bytes == s["max_pdf_size_bytes"]
    assert config.max_pdf_pages == s["max_pdf_pages"]
    assert config.max_text_file_bytes == s["max_text_file_bytes"]
    assert config.max_text_file_words == s["max_text_file_words"]
    assert config.slot_fill_min_words == s["slot_fill_min_words"]
    assert config.slot_fill_max_words == s["slot_fill_max_words"]
    assert config.topic_suggest_top_k == s["topic_suggest_top_k"]
    assert config.topic_suggest_min_score == s["topic_suggest_min_score"]
    assert config.retrieval_min_score == s["retrieval_min_score"]
    assert config.citation_min_support_score == s["citation_min_support_score"]
    assert config.default_compaction_model == s["groq_compaction_model"]
    assert config.eta_buffer_s == s["eta_buffer_s"]
    assert config.max_saved_scripts == data["storage"]["max_saved_scripts"]

    # PR 1 centralized [script] constants
    assert config.compaction_max_tokens == s["compaction_max_tokens"] == 300
    assert config.turn1_max_tokens == s["turn1_max_tokens"] == 160
    assert config.followup_max_tokens == s["followup_max_tokens"] == 220
    assert config.compaction_temperature == s["compaction_temperature"]
    assert config.turn1_temperature == s["turn1_temperature"]
    assert config.followup_temperature == s["followup_temperature"]
    assert config.followup_legacy_temperature == s["followup_legacy_temperature"]
    assert config.qa_limiter_max_wait_s == s["qa_limiter_max_wait_s"]
    assert config.chat_session_store_capacity == s["chat_session_store_capacity"]
    assert config.chat_session_ttl_s == s["chat_session_ttl_s"]
    assert config.slot_coverage_min_score == s["slot_coverage_min_score"]
    assert config.slot_coverage_ready_threshold == s["slot_coverage_ready_threshold"]
    assert config.free_topic_min_words == s["free_topic_min_words"]
    assert config.free_topic_thesis_min_words == s["free_topic_thesis_min_words"]
    assert config.qa_max_missing_items_display == s["qa_max_missing_items_display"]
    assert config.context_entry_reserve_chars == s["context_entry_reserve_chars"]
    assert config.context_entry_min_cap_chars == s["context_entry_min_cap_chars"]
    assert config.context_compaction_min_summary_chars == s["context_compaction_min_summary_chars"]
    assert config.compaction_low_signal_max_words == s["compaction_low_signal_max_words"]
    assert config.citable_note_min_words == s["citable_note_min_words"]
    assert config.pipeline_cache_max_size == s["pipeline_cache_max_size"]
    assert config.script_jobs_max_capacity == s["script_jobs_max_capacity"]
    assert config.chat_turn_jobs_max_capacity == s["chat_turn_jobs_max_capacity"]
    assert config.upload_read_chunk_bytes == s["upload_read_chunk_bytes"]
    assert config.moderation_max_chunks == s["moderation_max_chunks"]
    assert config.suggest_query_max_chunks == s["suggest_query_max_chunks"]
    assert config.generate_stage_base_s == s["generate_stage_base_s"]
    assert config.generate_stage_per_min_s == s["generate_stage_per_min_s"]
    assert config.chat_turn_step_durations == s["chat_turn_step_durations"]
    assert config.generate_stage_durations == s["generate_stage_durations"]

    # Consumer module wiring checks
    assert chat_session.COMPACTION_MAX_TOKENS == s["compaction_max_tokens"]
    assert chat_session.TURN1_MAX_TOKENS == s["turn1_max_tokens"]
    assert chat_session.FOLLOWUP_MAX_TOKENS == s["followup_max_tokens"]
    assert chat_session.COMPACTION_TEMPERATURE == s["compaction_temperature"]
    assert chat_session.TURN1_TEMPERATURE == s["turn1_temperature"]
    assert chat_session.FOLLOWUP_TEMPERATURE == s["followup_temperature"]
    assert chat_session.FOLLOWUP_LEGACY_TEMPERATURE == s["followup_legacy_temperature"]
    assert chat_session.QA_LIMITER_MAX_WAIT_S == s["qa_limiter_max_wait_s"]
    assert chat_session.DEFAULT_STORE_CAPACITY == s["chat_session_store_capacity"]
    assert chat_session.DEFAULT_STORE_TTL_SECONDS == s["chat_session_ttl_s"]
    assert chat_session.COSINE_SIMILARITY_THRESHOLD == s["slot_coverage_min_score"]
    assert chat_session.SLOT_COVERAGE_READY_THRESHOLD == s["slot_coverage_ready_threshold"]
    assert chat_session.FREE_TOPIC_MIN_WORDS == s["free_topic_min_words"]
    assert chat_session.FREE_TOPIC_THESIS_MIN_WORDS == s["free_topic_thesis_min_words"]
    assert chat_session.QA_MAX_MISSING_ITEMS_DISPLAY == s["qa_max_missing_items_display"]
    assert chat_session.CONTEXT_ENTRY_RESERVE_CHARS == s["context_entry_reserve_chars"]
    assert chat_session.CONTEXT_ENTRY_MIN_CAP_CHARS == s["context_entry_min_cap_chars"]
    assert (
        chat_session.CONTEXT_COMPACTION_MIN_SUMMARY_CHARS
        == s["context_compaction_min_summary_chars"]
    )
    assert chat_session.COMPACTION_LOW_SIGNAL_MAX_WORDS == s["compaction_low_signal_max_words"]
    assert chat_session.CHAT_TURN_STEP_DURATIONS == s["chat_turn_step_durations"]
    assert text_processing.COMPACTION_MAX_TOKENS == s["compaction_max_tokens"]
    assert text_processing.TURN1_MAX_TOKENS == s["turn1_max_tokens"]
    assert text_processing.FOLLOWUP_MAX_TOKENS == s["followup_max_tokens"]
    assert parser.MIN_PDF_SIZE_BYTES == s["min_pdf_size_bytes"]
    assert parser.MAX_PDF_SIZE_BYTES == s["max_pdf_size_bytes"]
    assert parser.MAX_POC_PAGES == s["max_pdf_pages"]
    assert parser.MAX_TEXT_FILE_BYTES == s["max_text_file_bytes"]
    assert parser.MAX_TEXT_FILE_WORDS == s["max_text_file_words"]
    assert parser.MAX_TURN_TEXT_CHARS == s["max_turn_text_chars"]
    assert parser.MAX_TURN_TEXT_WORDS == data["web"]["composer_max_words"]
    assert contracts.ETA_BUFFER_S == s["eta_buffer_s"]
    assert contracts.GENERATE_STAGE_BASE_S == s["generate_stage_base_s"]
    assert contracts.GENERATE_STAGE_PER_MIN_S == s["generate_stage_per_min_s"]
    assert {k: d for k, _, d in contracts.SCRIPT_JOB_STAGES} == s["generate_stage_durations"]
    assert contracts.script_stage_durations(5)["generating"] == round(
        s["generate_stage_base_s"] + 5 * s["generate_stage_per_min_s"], 1
    )
    assert pipeline._CITATION_MIN_SUPPORT_SCORE == s["citation_min_support_score"]
    assert pipeline._CITABLE_NOTE_MIN_WORDS == s["citable_note_min_words"]
    assert pipeline._FREE_TOPIC_THESIS_MIN_WORDS == s["free_topic_thesis_min_words"]
    assert pipeline.DEFAULT_PIPELINE_CACHE_MAX_SIZE == s["pipeline_cache_max_size"]
    assert pipeline.DEFAULT_SCRIPT_JOBS_CAPACITY == s["script_jobs_max_capacity"]
    assert pipeline._MODERATION_MAX_CHUNKS == s["moderation_max_chunks"]
    assert generator._RETRIEVAL_MIN_SCORE == s["retrieval_min_score"]
    assert generator._CITATION_MIN_SUPPORT_SCORE == s["citation_min_support_score"]
    assert template_engine._SLOT_FILL_MIN_WORDS == s["slot_fill_min_words"]
    assert template_engine._SLOT_FILL_MAX_WORDS == s["slot_fill_max_words"]
    assert template_engine._RETRIEVAL_MIN_SCORE == s["retrieval_min_score"]
    assert template_engine._CITATION_MIN_SUPPORT_SCORE == s["citation_min_support_score"]
    assert template_store.DEFAULT_SUGGEST_TOP_K == s["topic_suggest_top_k"]
    assert template_store.DEFAULT_SUGGEST_MIN_SCORE == s["topic_suggest_min_score"]
    assert main._CHAT_TURN_JOBS_CAP == s["chat_turn_jobs_max_capacity"]


def test_new_script_constants_have_no_env_overrides(monkeypatch):
    monkeypatch.setenv("COMPACTION_MAX_TOKENS", "999")
    monkeypatch.setenv("TURN1_MAX_TOKENS", "999")
    monkeypatch.setenv("FOLLOWUP_MAX_TOKENS", "999")
    monkeypatch.setenv("PIPELINE_CACHE_MAX_SIZE", "999")
    s = Settings(_env_file=None)
    assert not hasattr(s, "compaction_max_tokens")
    assert not hasattr(s, "turn1_max_tokens")
    assert not hasattr(s, "followup_max_tokens")
    assert not hasattr(s, "pipeline_cache_max_size")
    assert config.compaction_max_tokens == 300
    assert config.turn1_max_tokens == 160
    assert config.followup_max_tokens == 220
    assert config.pipeline_cache_max_size == 64


def test_groq_compaction_model_follows_toml_and_env(monkeypatch):
    monkeypatch.delenv("GROQ_COMPACTION_MODEL", raising=False)
    s = Settings(_env_file=None)
    assert s.groq_compaction_model == constants.load_constants()["script"]["groq_compaction_model"]
    monkeypatch.setenv("GROQ_COMPACTION_MODEL", "llama-3.1-8b-instant")
    assert Settings(_env_file=None).groq_compaction_model == "llama-3.1-8b-instant"


def test_api_config_returns_web_section():
    response = TestClient(main.app).get("/api/config")
    assert response.status_code == 200
    body = response.json()
    data = constants.load_constants()
    assert all(body[key] == value for key, value in data["web"].items())
    assert body["max_saved_scripts"] == config.max_saved_scripts
    assert body["max_audio_seconds"] == config.max_audio_seconds
    assert body["script_title_max_chars"] == config.script_title_max_chars
    assert body["max_turn_text_chars"] == data["script"]["max_turn_text_chars"]
    assert body["max_pdf_size_bytes"] == data["script"]["max_pdf_size_bytes"]
    assert body["max_pdf_pages"] == data["script"]["max_pdf_pages"]
    assert body["max_text_file_bytes"] == data["script"]["max_text_file_bytes"]
    assert body["max_text_file_words"] == data["script"]["max_text_file_words"]
    assert body["file_size_limits_bytes"] == {
        ".pdf": data["script"]["max_pdf_size_bytes"],
        ".md": data["script"]["max_text_file_bytes"],
        ".txt": data["script"]["max_text_file_bytes"],
    }
    assert body["eta_buffer_s"] == data["script"]["eta_buffer_s"] == 10
    assert body["script_telemetry"]["eta_buffer_s"] == data["script"]["eta_buffer_s"] == 10
    assert (
        body["script_telemetry"]["chat_turn_step_durations_s"]
        == data["script"]["chat_turn_step_durations"]
    )
    assert (
        body["script_telemetry"]["generate_stage_durations_s"]
        == data["script"]["generate_stage_durations"]
    )
    assert body["auth"] == {
        key: data["auth"][key] for key in ("otp_length", "resend_cooldown_s", "unconfirmed_ttl_min")
    }
    assert data["auth"]["unconfirmed_ttl_min"] == 60
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
