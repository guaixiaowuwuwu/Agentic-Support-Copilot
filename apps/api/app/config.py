from __future__ import annotations

import os
from pathlib import Path


def load_file_backed_environment() -> None:
    """Load env vars from *_FILE pointers without overwriting explicit values."""
    for key, file_path in list(os.environ.items()):
        if not key.endswith("_FILE") or not file_path:
            continue

        target_key = key[: -len("_FILE")]
        if os.environ.get(target_key):
            continue

        path = Path(file_path)
        if not path.exists():
            raise RuntimeError(f"Secret file for {target_key} does not exist: {path}")

        os.environ[target_key] = path.read_text(encoding="utf-8").strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
