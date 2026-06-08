from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

from .security import sanitize_for_log

try:  # pragma: no cover - import availability depends on runtime packaging.
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
except ImportError:  # pragma: no cover
    trace = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    ConsoleSpanExporter = None  # type: ignore[assignment]
    SimpleSpanProcessor = None  # type: ignore[assignment]


SERVICE_NAME = "agentic-support-copilot-api"
logger = logging.getLogger("support_copilot")
_configured_logging = False
_configured_tracing = False


def configure_logging() -> None:
    global _configured_logging
    if _configured_logging:
        return

    level_name = os.getenv("SUPPORT_COPILOT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")
    logger.setLevel(level)
    _configured_logging = True


def configure_tracing() -> None:
    global _configured_tracing
    if _configured_tracing or trace is None or TracerProvider is None or Resource is None:
        return

    try:
        provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
        if os.getenv("SUPPORT_COPILOT_OTEL_CONSOLE_EXPORTER", "").lower() in {"1", "true", "yes", "on"}:
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
    except Exception:
        pass
    finally:
        _configured_tracing = True


def tracer() -> Any:
    configure_tracing()
    if trace is None:
        return None
    return trace.get_tracer(SERVICE_NAME)


def _coerce_attribute(value: Any) -> Optional[str | bool | int | float]:
    sanitized = sanitize_for_log(value, string_limit=500)
    if sanitized is None or isinstance(sanitized, (bool, int, float, str)):
        return sanitized
    return json.dumps(sanitized, ensure_ascii=False, sort_keys=True)


def set_span_attributes(span: Any, attributes: Optional[Mapping[str, Any]]) -> None:
    if span is None or not attributes:
        return
    for key, value in attributes.items():
        coerced = _coerce_attribute(value)
        if coerced is not None:
            span.set_attribute(key, coerced)


@contextmanager
def telemetry_span(name: str, attributes: Optional[Mapping[str, Any]] = None) -> Iterator[Any]:
    active_tracer = tracer()
    if active_tracer is None:
        yield None
        return

    with active_tracer.start_as_current_span(name) as span:
        set_span_attributes(span, attributes)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_attribute("error.type", exc.__class__.__name__)
            raise


def log_event(level: str, event: str, **fields: Any) -> None:
    configure_logging()
    payload = {
        "event": event,
        **sanitize_for_log(fields, string_limit=1000),
    }
    message = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    logger.log(getattr(logging, level.upper(), logging.INFO), message)
