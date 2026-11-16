from pydantic_settings import BaseSettings, SettingsConfigDict

max_audio_seconds = 1320
# Baseline recording: the UI records 30 s; refuse anything outside [10 s, 60 s].
baseline_min_seconds = 10
baseline_max_seconds = 60
# Practice script limit. 1320 s of audio at 175 WPM (the "too fast" warning) is 3850 words, so
# a longer script cannot be read inside the audio limit. 4000 leaves a small margin above that and
# above the 20-minute target (2340-3260 words). The character cap stops a few huge "words".
max_script_words = 4000
max_script_chars = 40_000
max_upload_bytes = 100 * 1024 * 1024
# Whole request body (file + form fields). Larger bodies get 413 before they are read.
max_request_bytes = max_upload_bytes + 1024 * 1024
allowed_formats = ["wav", "mp3", "ogg", "flac", "matroska", "webm", "m4a"]

decode_timeout_s = 60
duration_cap_margin_s = 10

MIN_PAUSE_S = 0.35

# STT HTTP timeouts (seconds): time to connect, and longest wait between two reads of the
# response. Starting values, not measured; tune after timing long (20 min) recordings.
stt_connect_timeout_s = 5
stt_read_timeout_s = 120


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_llm_model: str = ""
    groq_llm_fallback_model_1: str = ""
    groq_llm_fallback_model_2: str = ""
    app_env: str = "dev"

    # THÊM 2 DÒNG NÀY CHO MODULE STT MỚI:
    deepgram_api_key: str = ""
    gladia_api_key: str = ""

    # Supabase: database and storage
    supabase_url: str = ""
    supabase_service_key: str = ""
    audio_bucket: str = "audio"
    series_bucket: str = "series"
    baselines_bucket: str = "baselines"
    retention_full_sessions: int = 10
    signed_url_ttl_s: int = 600
    baseline_required: bool = True  # no current baseline -> /api/evaluate returns 409

    dev_user_id: str = ""  # TODO(auth): remove when real auth is merged

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()


def missing_required_settings(s: Settings) -> list[str]:
    """Names of the required environment variables that are empty.

    STT (Deepgram primary, Gladia fallback) and Groq (script generation) are always required.
    Supabase is required outside dev; in dev, no SUPABASE_URL means the in-memory repositories,
    but a URL without its service key is a mistake.
    """
    required = {
        "DEEPGRAM_API_KEY": s.deepgram_api_key,
        "GLADIA_API_KEY": s.gladia_api_key,
        "GROQ_API_KEY": s.groq_api_key,
    }
    if s.app_env != "dev" or s.supabase_url:
        required["SUPABASE_URL"] = s.supabase_url
        required["SUPABASE_SERVICE_KEY"] = s.supabase_service_key
    return [name for name, value in required.items() if not value.strip()]
