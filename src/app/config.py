from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_stt_model: str = ""
    groq_llm_model: str = ""
    groq_llm_fallback_model_1: str = ""
    groq_llm_fallback_model_2: str = ""
    app_env: str = "dev"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
