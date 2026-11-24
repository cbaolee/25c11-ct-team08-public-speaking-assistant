import json
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from src.app.constants import CONSTANTS

# The one .env of the project, at the repo root. A fixed path, so the server and the tests
# read the same file whatever folder the command is started from.
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
# Supabase shows these API URLs too; SUPABASE_URL must be the project URL without them.
_SUPABASE_API_SUFFIXES = ("/rest/v1", "/auth/v1", "/storage/v1")

# Tunable values come from app_constants.toml (see that file for what each one means).
_storage = CONSTANTS["storage"]
_audio = CONSTANTS["audio"]
_script = CONSTANTS["script"]

max_audio_seconds = _audio["max_audio_seconds"]
baseline_min_seconds = _audio["baseline_min_seconds"]
baseline_max_seconds = _audio["baseline_max_seconds"]
max_script_words = _script["max_script_words"]
max_script_chars = _script["max_script_chars"]
max_upload_bytes = _storage["max_upload_bytes"]
max_saved_scripts = _storage["max_saved_scripts"]
script_title_max_chars = _storage["script_title_max_chars"]
max_list_page_size = _storage["max_list_page_size"]
avatar_max_bytes = _storage["avatar_max_bytes"]
avatar_size_px = _storage["avatar_size_px"]
avatar_max_side_px = _storage["avatar_max_side_px"]
# Whole request body (file + form fields). Larger bodies get 413 before they are read.
max_request_bytes = max_upload_bytes + 1024 * 1024
allowed_formats = ["wav", "mp3", "ogg", "flac", "matroska", "webm", "m4a"]

decode_timeout_s = _audio["decode_timeout_s"]
duration_cap_margin_s = _audio["duration_cap_margin_s"]

MIN_PAUSE_S = _audio["min_pause_s"]

stt_connect_timeout_s = _audio["stt_connect_timeout_s"]
stt_read_timeout_s = _audio["stt_read_timeout_s"]


def validate_list_limits(page_size: int, saved_scripts: int) -> None:
    """Stop start-up when one list call could not return every saved script."""
    if page_size < saved_scripts:
        raise RuntimeError(
            f"storage.max_list_page_size ({page_size}) must be >= "
            f"storage.max_saved_scripts ({saved_scripts}) in app_constants.toml"
        )


def _from_toml(section: str, key: str):
    """Default factory: read the value when Settings is built, so .env still wins."""
    return lambda: CONSTANTS[section][key]


# A comma-separated list in .env ("key1,key2"), not JSON.
KeyList = Annotated[list[str], NoDecode]


def _clean_supabase_url(value: str) -> str:
    """Keep only the project URL (https://<ref>.supabase.co): trailing "/" is removed,
    an API path such as /rest/v1 is refused, because every request would fail later."""
    url = value.strip().rstrip("/")
    if url.lower().endswith(_SUPABASE_API_SUFFIXES):
        raise ValueError(
            "SUPABASE_URL must be the project URL https://<ref>.supabase.co, "
            f"without an API path such as /rest/v1 (got {url!r})"
        )
    return url


CORE_SHARD_REF = "core"  # accounts.shard_ref of users whose sessions stay in SUPABASE_URL
_SHARD_REF = re.compile(r"^[a-z0-9-]+$")


class ShardProject(BaseModel):
    """One shard project (ADR-012): holds the sessions table and the audio, series buckets.

    `ref` is what accounts.shard_ref stores: the first part of the URL host, which never
    changes. `number` is the 1-based position in SUPABASE_SHARDS, only a label for logs and
    project names (psc-shard01 is number 1); it is never stored.
    """

    ref: str
    number: int
    url: str
    service_key: str


def shard_ref_from_url(url: str) -> str:
    """https://hrtwwvdrueanstxjtqki.supabase.co -> "hrtwwvdrueanstxjtqki"."""
    host = urlparse(url).hostname or ""
    ref = host.split(".")[0].lower()
    if not _SHARD_REF.match(ref) or ref == CORE_SHARD_REF:
        raise ValueError(f"SUPABASE_SHARDS: cannot read a project ref from {url!r}")
    return ref


def parse_shards(value: object) -> dict[str, ShardProject]:
    """SUPABASE_SHARDS='{"https://a.supabase.co": "key-a", "https://b.supabase.co": "key-b"}'.

    A JSON object, project URL -> service key. Order does not matter for the data: users are
    stored by project ref, so entries can be added, moved or (when empty) removed freely.
    """
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            value = json.loads(value)
        except json.JSONDecodeError as err:
            raise ValueError(
                'SUPABASE_SHARDS must be a JSON object {"<project url>": "<service key>", ...}'
            ) from err
    if not isinstance(value, dict):
        raise ValueError(
            'SUPABASE_SHARDS must be a JSON object {"<project url>": "<service key>", ...}'
        )
    shards: dict[str, ShardProject] = {}
    for number, (raw_url, raw_key) in enumerate(value.items(), start=1):
        if not isinstance(raw_url, str) or not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError("SUPABASE_SHARDS: every project URL needs a service key")
        url = _clean_supabase_url(raw_url)
        ref = shard_ref_from_url(url)
        if ref in shards:
            raise ValueError(f"SUPABASE_SHARDS lists project {ref} twice")
        shards[ref] = ShardProject(ref=ref, number=number, url=url, service_key=raw_key.strip())
    return shards


class Settings(BaseSettings):
    # Several keys per service: when one runs out of quota the next is used (src/app/key_pool.py)
    cerebras_api_keys: KeyList = []
    cerebras_model: str = ""
    cerebras_fallback_model_1: str = ""
    groq_api_keys: KeyList = []
    groq_llm_model: str = ""
    groq_llm_fallback_model_1: str = ""
    groq_llm_fallback_model_2: str = ""
    app_env: str = "dev"

    # Moderation Layer 2 (Ollama / OpenAI-compatible Llama-Guard endpoint)
    ollama_host: str = ""
    ollama_api_key: str = ""
    guard_model: str = "llama-guard3:8b"

    # Speech-to-text providers (Deepgram primary, Gladia fallback)
    deepgram_api_keys: KeyList = []
    gladia_api_keys: KeyList = []

    # Supabase: database and storage
    supabase_url: str = ""
    supabase_service_key: str = ""
    # Extra projects for sessions and their files; empty means everything stays in SUPABASE_URL
    supabase_shards: Annotated[dict[str, ShardProject], NoDecode] = {}
    audio_bucket: str = "audio"
    series_bucket: str = "series"
    baselines_bucket: str = "baselines"
    avatars_bucket: str = "avatars"
    retention_full_sessions: int = Field(
        default_factory=_from_toml("storage", "retention_full_sessions")
    )
    max_compact_sessions: int = Field(default_factory=_from_toml("storage", "max_compact_sessions"))
    signed_url_ttl_s: int = Field(default_factory=_from_toml("storage", "signed_url_ttl_s"))
    baseline_required: bool = True  # no current baseline -> /api/evaluate returns 409
    # `Secure` flag of the refresh-token cookie. Browsers accept Secure cookies on
    # http://localhost, so it stays on in dev; turn off only for plain-http hosts in tests.
    auth_cookie_secure: bool = True

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    @field_validator(
        "cerebras_api_keys", "groq_api_keys", "deepgram_api_keys", "gladia_api_keys", mode="before"
    )
    @classmethod
    def _split_keys(cls, value: object) -> object:
        """ "k1, k2,,k3" -> ["k1", "k2", "k3"]: split on commas, drop spaces and empty items."""
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, (list, tuple)):
            return [str(k).strip() for k in value if str(k).strip()]
        return value

    @field_validator("supabase_url")
    @classmethod
    def _check_supabase_url(cls, value: str) -> str:
        return _clean_supabase_url(value)

    @field_validator("supabase_shards", mode="before")
    @classmethod
    def _parse_shards(cls, value: object) -> object:
        if isinstance(value, dict) and all(isinstance(v, ShardProject) for v in value.values()):
            return value
        return parse_shards(value)


settings = Settings()


def missing_required_settings(s: Settings) -> list[str]:
    """Names of the required environment variables that are empty.

    STT (Deepgram primary, Gladia fallback) and Groq (script generation) are always required.
    Supabase is required outside dev; in dev, no SUPABASE_URL means the in-memory repositories,
    but a URL without its service key is a mistake.
    """
    required = {
        "DEEPGRAM_API_KEYS": ",".join(s.deepgram_api_keys),
        "GLADIA_API_KEYS": ",".join(s.gladia_api_keys),
        "GROQ_API_KEYS": ",".join(s.groq_api_keys),
    }
    if s.app_env != "dev" or s.supabase_url or s.supabase_shards:
        required["SUPABASE_URL"] = s.supabase_url
        required["SUPABASE_SERVICE_KEY"] = s.supabase_service_key
    return [name for name, value in required.items() if not value.strip()]
