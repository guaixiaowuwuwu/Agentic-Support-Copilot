from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol, Sequence

from .security import redact_secrets


PLACEHOLDER_API_KEYS = {"", "replace-me", "changeme", "none", "null"}


def load_project_env() -> None:
    here = Path(__file__).resolve()
    candidates = [Path.cwd() / ".env"]
    for parent_index in (3, 1):
        if len(here.parents) > parent_index:
            candidates.append(here.parents[parent_index] / ".env")
    env_path = next((candidate for candidate in candidates if candidate.exists()), None)
    if env_path is None:
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


def _env_int(name: str, fallback: int) -> int:
    value = os.getenv(name)
    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback


def _env_float(name: str, fallback: float) -> float:
    value = os.getenv(name)
    if value is None:
        return fallback
    try:
        return float(value)
    except ValueError:
        return fallback


def _usable_api_key(api_key: str) -> bool:
    return api_key.strip().lower() not in PLACEHOLDER_API_KEYS


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float
    enabled: bool
    retry_count: int = 1
    retry_backoff_seconds: float = 0.2
    rate_limit_per_minute: int = 60

    @classmethod
    def from_env(cls) -> "LLMSettings":
        base_url = (
            _env("SUPPORT_COPILOT_LLM_BASE_URL")
            or _env("LLM_BASE_URL")
            or "http://localhost:11434/v1"
        )
        model = _env("SUPPORT_COPILOT_LLM_MODEL") or _env("LLM_MODEL")
        api_key = _env("SUPPORT_COPILOT_LLM_API_KEY") or _env("LLM_API_KEY")
        timeout_seconds = _env_float(
            "SUPPORT_COPILOT_LLM_TIMEOUT_SECONDS",
            _env_float("LLM_TIMEOUT_SECONDS", 20.0),
        )
        retry_count = max(0, _env_int("SUPPORT_COPILOT_LLM_RETRY_COUNT", _env_int("LLM_RETRY_COUNT", 1)))
        retry_backoff_seconds = max(
            0.0,
            _env_float(
                "SUPPORT_COPILOT_LLM_RETRY_BACKOFF_SECONDS",
                _env_float("LLM_RETRY_BACKOFF_SECONDS", 0.2),
            ),
        )
        rate_limit_per_minute = max(
            0,
            _env_int(
                "SUPPORT_COPILOT_LLM_RATE_LIMIT_PER_MINUTE",
                _env_int("LLM_RATE_LIMIT_PER_MINUTE", 60),
            ),
        )

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
            retry_count=retry_count,
            retry_backoff_seconds=retry_backoff_seconds,
            rate_limit_per_minute=rate_limit_per_minute,
        )

    def chat_completions_url(self) -> str:
        if self.base_url.rstrip("/").endswith("/chat/completions"):
            return self.base_url.rstrip("/")
        return f"{self.base_url.rstrip('/')}/chat/completions"


class OpenAICompatibleChatClient:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self.last_call_metadata: Dict[str, object] = {}
        self._request_timestamps: list[float] = []

    def complete(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> str:
        self._reserve_rate_limit()
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
        started = time.perf_counter()
        attempts = 0
        retryable_status_codes = {408, 409, 425, 429, 500, 502, 503, 504}
        last_error = ""

        for attempt in range(self.settings.retry_count + 1):
            attempts = attempt + 1
            try:
                with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                text = self._extract_text(data)
                self._record_metadata("success", attempts, started)
                return text
            except urllib.error.HTTPError as exc:
                if exc.code in retryable_status_codes and attempt < self.settings.retry_count:
                    last_error = f"HTTP {exc.code}"
                    self._sleep_before_retry(attempt)
                    continue
                detail = redact_secrets(exc.read().decode("utf-8", errors="replace"))[:300]
                self._record_metadata("failed", attempts, started, f"HTTP {exc.code}")
                raise LLMError(f"LLM API returned HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_error = redact_secrets(exc)
                if attempt < self.settings.retry_count:
                    self._sleep_before_retry(attempt)
                    continue
                self._record_metadata("failed", attempts, started, str(last_error))
                raise LLMError(f"LLM API request failed: {last_error}") from exc
            except LLMError as exc:
                last_error = str(exc)
                if attempt < self.settings.retry_count:
                    self._sleep_before_retry(attempt)
                    continue
                self._record_metadata("failed", attempts, started, last_error)
                raise

        self._record_metadata("failed", attempts, started, last_error)
        raise LLMError(f"LLM API request failed: {last_error}")

    def _extract_text(self, data: Dict[str, object]) -> str:
        try:
            choices = data["choices"]
            choice = choices[0] if isinstance(choices, list) else None
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM API response did not include choices") from exc

        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
        if isinstance(choice, dict) and isinstance(choice.get("text"), str):
            return choice["text"]
        raise LLMError("LLM API response did not include text content")

    def _reserve_rate_limit(self) -> None:
        limit = self.settings.rate_limit_per_minute
        if limit <= 0:
            return
        now = time.monotonic()
        self._request_timestamps = [item for item in self._request_timestamps if now - item < 60]
        if len(self._request_timestamps) >= limit:
            self.last_call_metadata = {
                "status": "rate_limited",
                "model": self.settings.model,
                "attempts": 0,
                "rate_limit_per_minute": limit,
            }
            raise LLMError("LLM client rate limit exceeded")
        self._request_timestamps.append(now)

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.settings.retry_backoff_seconds <= 0:
            return
        time.sleep(self.settings.retry_backoff_seconds * (2**attempt))

    def _record_metadata(
        self,
        status: str,
        attempts: int,
        started: float,
        error_summary: str = "",
    ) -> None:
        self.last_call_metadata = {
            "status": status,
            "model": self.settings.model,
            "attempts": attempts,
            "timeout_seconds": self.settings.timeout_seconds,
            "retry_count": self.settings.retry_count,
            "rate_limit_per_minute": self.settings.rate_limit_per_minute,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error_summary": redact_secrets(error_summary)[:300] if error_summary else "",
        }


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
        "timeout_seconds": settings.timeout_seconds,
        "retry_count": settings.retry_count,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
    }
