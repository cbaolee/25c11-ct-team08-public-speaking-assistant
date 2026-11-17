"""Load app_constants.toml (repo root) once at import time."""

import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSTANTS_FILE = REPO_ROOT / "app_constants.toml"


def load_constants(path: Path = CONSTANTS_FILE) -> dict[str, Any]:
    """Read the TOML file and return its sections as nested dicts."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


CONSTANTS: dict[str, Any] = load_constants()
