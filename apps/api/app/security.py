from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


SECRET_RE = re.compile(
    r"(bearer\s+)[a-zA-Z0-9._-]{8,}|"
    r"(sk-[a-zA-Z0-9_-]+)|"
    r"((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+",
    re.IGNORECASE,
)
SENSITIVE_KEY_RE = re.compile(r"(authorization|api[_-]?key|password|secret|credential)", re.IGNORECASE)
TOKEN_KEY_RE = re.compile(r"(^|[_-])token($|[_-])|tokens?$", re.IGNORECASE)
NON_SECRET_TOKEN_KEYS = {"token_count", "tokens", "max_tokens", "prompt_tokens", "completion_tokens", "total_tokens"}


def clip_text(text: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 3)]}..."


def redact_secrets(text: Any) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1) or match.group(3) or ''}[REDACTED]", str(text))


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in NON_SECRET_TOKEN_KEYS:
        return False
    return bool(SENSITIVE_KEY_RE.search(key) or TOKEN_KEY_RE.search(key))


def sanitize_for_log(value: Any, *, string_limit: int = 1000) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return clip_text(redact_secrets(value), string_limit)

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            sanitized[key] = "[REDACTED]" if is_sensitive_key(key) else sanitize_for_log(
                raw_item,
                string_limit=string_limit,
            )
        return sanitized

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [sanitize_for_log(item, string_limit=string_limit) for item in value]

    return clip_text(redact_secrets(value), string_limit)
