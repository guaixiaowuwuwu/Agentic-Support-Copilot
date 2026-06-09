#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
PLACEHOLDER_VALUES = {"", "replace-me", "changeme", "none", "null", "your-api-key"}
REQUIRED_ENV = (
    "SUPPORT_COPILOT_LLM_ENABLED",
    "SUPPORT_COPILOT_LLM_BASE_URL",
    "SUPPORT_COPILOT_LLM_MODEL",
    "SUPPORT_COPILOT_LLM_API_KEY",
    "SUPPORT_COPILOT_EMBEDDING_PROVIDER",
    "SUPPORT_COPILOT_EMBEDDING_BASE_URL",
    "SUPPORT_COPILOT_EMBEDDING_MODEL",
    "SUPPORT_COPILOT_EMBEDDING_API_KEY",
)


class SmokeFailure(RuntimeError):
    pass


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
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


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_placeholder(value: str | None) -> bool:
    return (value or "").strip().lower() in PLACEHOLDER_VALUES


def _redact(value: Any) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    for env_name in ("SUPPORT_COPILOT_LLM_API_KEY", "SUPPORT_COPILOT_EMBEDDING_API_KEY"):
        secret = os.getenv(env_name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _skip(reasons: list[str]) -> int:
    print("OpenAI smoke skipped.")
    for reason in reasons:
        print(f"- {reason}")
    return 0


def _validate_env() -> list[str]:
    reasons: list[str] = []
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        reasons.append(f"Missing required environment variables: {', '.join(missing)}")

    if not _env_bool("SUPPORT_COPILOT_LLM_ENABLED"):
        reasons.append("SUPPORT_COPILOT_LLM_ENABLED is not true.")

    provider = os.getenv("SUPPORT_COPILOT_EMBEDDING_PROVIDER", "").strip().lower()
    if provider not in {"openai", "openai_compatible", "compatible"}:
        reasons.append(
            "SUPPORT_COPILOT_EMBEDDING_PROVIDER must be openai_compatible, openai, or compatible."
        )

    for name in ("SUPPORT_COPILOT_LLM_API_KEY", "SUPPORT_COPILOT_EMBEDDING_API_KEY"):
        value = os.getenv(name)
        if value is not None and _is_placeholder(value):
            reasons.append(f"{name} is empty or a placeholder.")

    for name in (
        "SUPPORT_COPILOT_LLM_BASE_URL",
        "SUPPORT_COPILOT_LLM_MODEL",
        "SUPPORT_COPILOT_EMBEDDING_BASE_URL",
        "SUPPORT_COPILOT_EMBEDDING_MODEL",
    ):
        value = os.getenv(name)
        if value is not None and _is_placeholder(value):
            reasons.append(f"{name} is empty or a placeholder.")

    return reasons


def _request_json(client: Any, method: str, path: str, *, headers: dict[str, str], body: Any = None) -> Any:
    kwargs: dict[str, Any] = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    response = getattr(client, method)(path, **kwargs)
    if response.status_code >= 400:
        raise SmokeFailure(f"{method.upper()} {path} returned HTTP {response.status_code}: {_redact(response.text)}")
    return response.json()


def _latest_llm_audit(audits: list[dict[str, Any]], run_id: str) -> dict[str, Any] | None:
    matching = [audit for audit in audits if audit.get("target_id") == run_id]
    matching.sort(key=lambda audit: audit.get("created_at", ""), reverse=True)
    return matching[0] if matching else None


def main() -> int:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("SUPPORT_COPILOT_AUTH_MODE", "local_headers")
    os.environ.setdefault("SUPPORT_COPILOT_STORE", "memory")
    os.environ.setdefault("SUPPORT_COPILOT_SEED_DEMO_DATA", "false")

    _load_dotenv()
    reasons = _validate_env()
    if reasons:
        return _skip(reasons)

    sys.path.insert(0, str(API_ROOT))
    from fastapi.testclient import TestClient

    from app import main as api_main

    headers = {
        "X-User-Email": "openai-smoke@acme.example",
        "X-Tenant-Id": "acme",
        "X-Tenant-Ids": "acme",
        "X-User-Roles": "admin",
    }

    timeout_seconds = float(os.getenv("SUPPORT_COPILOT_SMOKE_TIMEOUT_SECONDS", "120"))
    client = TestClient(api_main.app)

    try:
        health = _request_json(client, "get", "/api/health", headers=headers)
        print(
            "LLM status: "
            f"enabled={health['llm'].get('enabled')} "
            f"model={health['llm'].get('model')} "
            f"base_url_configured={health['llm'].get('base_url_configured')} "
            f"api_key_configured={health['llm'].get('api_key_configured')}"
        )
        print(
            "Embedding status: "
            f"provider={health['embeddings'].get('provider')} "
            f"model={health['embeddings'].get('model')} "
            f"base_url_configured={health['embeddings'].get('base_url_configured')} "
            f"api_key_configured={health['embeddings'].get('api_key_configured')}"
        )

        stamp = int(time.time())
        document = _request_json(
            client,
            "post",
            "/api/knowledge/documents",
            headers=headers,
            body={
                "tenant_id": "acme",
                "title": f"OpenAI smoke API 401 runbook {stamp}",
                "source_type": "runbook",
                "uri": f"runbook://openai-smoke/api-401/{stamp}",
                "product_line": "api",
                "version": "v1",
                "required_permissions": ["support_agent"],
                "source_system": "smoke",
                "content": (
                    "For API 401 Unauthorized responses, verify the bearer token audience, issuer, "
                    "expiry, tenant scope, and whether the integration rotated credentials recently. "
                    "Ask for request_id, endpoint path, timestamp, and client application name. "
                    "Never ask the customer to paste raw tokens or API keys into the ticket."
                ),
            },
        )
        print(f"Created knowledge document: id={document['id']} chunks={document['chunk_count']}")

        ingestion = _request_json(
            client,
            "post",
            "/api/knowledge/embeddings/ingest",
            headers=headers,
            body={"tenant_id": "acme"},
        )
        if ingestion.get("embedding_status") != "embedded":
            raise SmokeFailure(f"Embedding ingestion did not finish: {_redact(ingestion)}")
        print(
            "Embedding ingestion: "
            f"updated_chunks={ingestion.get('updated_chunks')} "
            f"status={ingestion.get('embedding_status')}"
        )

        ticket = _request_json(
            client,
            "post",
            "/api/tickets",
            headers=headers,
            body={
                "tenant_id": "acme",
                "customer_name": "Acme Smoke Customer",
                "channel": "email",
                "subject": "API returns 401 Unauthorized",
                "description": (
                    "Customer reports API 401 errors for checkout requests. "
                    "request_id=req_openai_smoke_401 endpoint=/v1/checkout/orders"
                ),
            },
        )
        run = _request_json(client, "post", f"/api/runs/{ticket['id']}/start", headers=headers)
        run_id = run["id"]
        api_main.active_run_queue().wait_for_run(run_id, timeout=timeout_seconds)

        run = _request_json(client, "get", f"/api/runs/{run_id}", headers=headers)
        if run.get("status") != "awaiting_approval":
            raise SmokeFailure(f"Run did not reach approval: {_redact(run)}")
        trace = _request_json(client, "get", f"/api/runs/{run_id}/trace", headers=headers)
        approval = trace.get("approval") or {}
        draft = approval.get("proposed_reply") or ""
        if not draft:
            raise SmokeFailure("Run reached approval without a draft reply.")
        print(f"Run reached approval: run_id={run_id} draft_chars={len(draft)}")

        audits = _request_json(
            client,
            "get",
            f"/api/audit-logs?action=llm_call_completed&target={run_id}&limit=20",
            headers=headers,
        )
        audit = _latest_llm_audit(audits, run_id)
        if audit is None:
            raise SmokeFailure("No llm_call_completed audit entry was recorded for the smoke run.")

        metadata = audit.get("metadata") or {}
        llm_status = metadata.get("status")
        fallback_used = bool(metadata.get("fallback_used"))
        if llm_status == "success" and not fallback_used:
            print(f"LLM draft verified: model={metadata.get('model')} status={llm_status}")
        elif llm_status == "policy_fallback":
            print(
                "LLM responded but policy fallback was used: "
                f"model={metadata.get('model')} status={llm_status}"
            )
        else:
            reason = metadata.get("error_summary") or llm_status or "unknown"
            raise SmokeFailure(f"LLM draft fell back before success: {_redact(reason)}")

        print("OpenAI smoke completed.")
        return 0
    except SmokeFailure as exc:
        print(f"OpenAI smoke failed: {_redact(exc)}", file=sys.stderr)
        return 1
    finally:
        api_main.active_run_queue().shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
