from pydantic_settings import BaseSettings, SettingsConfigDict

max_audio_seconds = 1320
max_upload_bytes = 100 * 1024 * 1024
allowed_formats = ["wav", "mp3", "ogg", "flac", "matroska", "webm", "m4a"]

decode_timeout_s = 60
duration_cap_margin_s = 10

MIN_PAUSE_S = 0.35


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_stt_model: str = ""
    groq_llm_model: str = ""
    groq_llm_fallback_model_1: str = ""
    groq_llm_fallback_model_2: str = ""
    app_env: str = "dev"
    
    # THÊM 2 DÒNG NÀY CHO MODULE STT MỚI:
    deepgram_api_key: str = ""
    gladia_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
