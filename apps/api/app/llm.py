from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol, Sequence


PLACEHOLDER_API_KEYS = {"", "replace-me", "changeme", "none", "null"}


def load_project_env() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


load_project_env()


class ChatClient(Protocol):
    def complete(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> str:
        ...


class LLMError(RuntimeError):
    pass


def _env(name: str, fallback: Optional[str] = None) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return fallback or ""


def _env_bool(name: str) -> Optional[bool]:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _usable_api_key(api_key: str) -> bool:
    return api_key.strip().lower() not in PLACEHOLDER_API_KEYS


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    enabled: bool

    @classmethod
    def from_env(cls) -> "LLMSettings":
        base_url = (
            _env("SUPPORT_COPILOT_LLM_BASE_URL")
            or _env("LLM_BASE_URL")
            or "http://localhost:11434/v1"
        )
        model = _env("SUPPORT_COPILOT_LLM_MODEL") or _env("LLM_MODEL")
        api_key = _env("SUPPORT_COPILOT_LLM_API_KEY") or _env("LLM_API_KEY")
        timeout_raw = _env("SUPPORT_COPILOT_LLM_TIMEOUT_SECONDS") or _env("LLM_TIMEOUT_SECONDS") or "20"
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 20.0

        explicit_enabled = _env_bool("SUPPORT_COPILOT_LLM_ENABLED")
        if explicit_enabled is None:
            explicit_enabled = _env_bool("LLM_ENABLED")

        if explicit_enabled is None:
            enabled = bool(base_url and model and _usable_api_key(api_key))
        else:
            enabled = explicit_enabled and bool(base_url and model)

        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
        )

    def chat_completions_url(self) -> str:
        if self.base_url.rstrip("/").endswith("/chat/completions"):
            return self.base_url.rstrip("/")
        return f"{self.base_url.rstrip('/')}/chat/completions"


class OpenAICompatibleChatClient:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def complete(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> str:
        payload = {
            "model": self.settings.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        request = urllib.request.Request(
            self.settings.chat_completions_url(),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise LLMError(f"LLM API returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM API request failed: {exc}") from exc

        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM API response did not include choices") from exc

        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        if isinstance(choice, dict) and isinstance(choice.get("text"), str):
            return choice["text"]
        raise LLMError("LLM API response did not include text content")


def create_chat_client_from_env() -> Optional[ChatClient]:
    settings = LLMSettings.from_env()
    if not settings.enabled:
        return None
    return OpenAICompatibleChatClient(settings)


def llm_status_from_env() -> Dict[str, object]:
    settings = LLMSettings.from_env()
    return {
        "enabled": settings.enabled,
        "mode": "openai_compatible" if settings.enabled else "deterministic_fallback",
        "base_url_configured": bool(settings.base_url),
        "model": settings.model or None,
    }
