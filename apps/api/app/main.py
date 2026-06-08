from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .agents import SupportAgentWorkflow
from .auth import (
    ADMIN_ROLES,
    APPROVAL_DECISION_ROLES,
    APPROVAL_READ_ROLES,
    KNOWLEDGE_READ_ROLES,
    KNOWLEDGE_WRITE_ROLES,
    RUN_ROLES,
    TICKET_READ_ROLES,
    TRACE_READ_ROLES,
    Principal,
    auth_status_from_env,
    get_current_principal,
    require_role,
    require_tenant_access,
    resolve_tenant,
)
from .config import env_bool, load_file_backed_environment
from .graph import WORKFLOW_NODES, graph_engine_name
from .knowledge import embedding_provider_status_from_env
from .llm import create_chat_client_from_env, llm_status_from_env
from .models import AuditLog, Document, Ticket, to_dict
from .observability import configure_logging, configure_tracing, log_event, set_span_attributes, telemetry_span
from .schemas import ApprovalDecisionRequest, CreateDocumentRequest, CreateTicketRequest, IngestEmbeddingsRequest
from .security import clip_text, redact_secrets
from .store import NotFoundError, create_store
from .tasks import RunTaskQueue
from .tools import create_tool_registry_from_env
from .time_utils import utc_now

KNOWLEDGE_DOCUMENT_MAINTENANCE_POLICY = {
    "first_version": (
        "Documents imported through the API are immutable after creation; edits, retirement, deletion, "
        "versioning, review, batch import, and hit analytics are deferred."
    ),
    "update_strategy": (
        "Future document updates should create a new auditable version, regenerate chunks with pending "
        "embeddings, and keep the previous version available for trace history."
    ),
    "retirement_strategy": (
        "Future retirement should mark a document non-active, exclude its chunks from retrieval, and "
        "preserve historical audit and run trace references."
    ),
    "delete_strategy": (
        "Future deletion should be soft-delete by default, require an admin-level retention decision "
        "for hard deletion, and always leave an audit entry."
    ),
    "audited_actions": [
        "document_created",
        "document_updated",
        "document_retired",
        "document_deleted",
        "embeddings_ingested",
    ],
}

load_file_backed_environment()
store = create_store(seed=True)
workflow = SupportAgentWorkflow(store, tools=create_tool_registry_from_env(), chat_client=create_chat_client_from_env())
run_queue = RunTaskQueue(workflow)
configure_logging()
configure_tracing()

app = FastAPI(title="Agentic Support Copilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_correlation_id = request.headers.get("X-Correlation-Id") or str(uuid4())
    start = time.perf_counter()
    attributes = {
        "http.request.method": request.method,
        "url.path": request.url.path,
        "request.correlation_id": request_correlation_id,
    }
    with telemetry_span("api.request", attributes) as span:
        try:
            response = await call_next(request)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            set_span_attributes(
                span,
                {
                    "http.response.status_code": 500,
                    "http.server.duration_ms": latency_ms,
                    "error.type": exc.__class__.__name__,
                },
            )
            log_event(
                "ERROR",
                "api_request_failed",
                method=request.method,
                path=request.url.path,
                status_code=500,
                latency_ms=latency_ms,
                correlation_id=request_correlation_id,
                error_type=exc.__class__.__name__,
            )
            raise

        latency_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Correlation-Id"] = request_correlation_id
        set_span_attributes(
            span,
            {
                "http.response.status_code": response.status_code,
                "http.server.duration_ms": latency_ms,
            },
        )
        log_event(
            "INFO",
            "api_request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            correlation_id=request_correlation_id,
        )
        return response


def not_found(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Resource not found: {exc.args[0]}")


def hidden_not_found(exc: HTTPException) -> HTTPException:
    if exc.status_code == 404:
        return not_found(NotFoundError("restricted"))
    return exc


def active_run_queue() -> RunTaskQueue:
    global run_queue
    if run_queue.workflow is not workflow:
        run_queue = RunTaskQueue(workflow)
    return run_queue


def audit(
    principal: Principal,
    action: str,
    target_type: str,
    target_id: str,
    metadata: Optional[dict] = None,
    tenant_id: Optional[str] = None,
) -> None:
    store.add_audit(
        AuditLog(
            tenant_id=tenant_id or principal.tenant_id,
            actor=principal.email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )
    )
    log_event(
        "INFO",
        "audit_recorded",
        tenant_id=tenant_id or principal.tenant_id,
        actor=principal.email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
    )


def assert_ticket_access(ticket_id: str, principal: Principal) -> Ticket:
    ticket = store.get_ticket(ticket_id)
    require_tenant_access(principal, ticket.tenant_id, hide=True)
    return ticket


def _embedding_status(chunk_count: int, embedded_chunk_count: int) -> str:
    if chunk_count == 0:
        return "empty"
    if embedded_chunk_count == 0:
        return "pending"
    if embedded_chunk_count == chunk_count:
        return "embedded"
    return "partial"


def _chunks_for_document(document_id: str) -> list:
    return [chunk for chunk in store.list_chunks() if chunk.document_id == document_id]


def _chunks_for_tenant(tenant_id: str) -> list:
    return [chunk for chunk in store.list_chunks() if chunk.tenant_id == tenant_id]


def knowledge_document_response(document: Document, *, include_chunks: bool = False) -> dict[str, Any]:
    chunks = _chunks_for_document(document.id)
    embedded_chunk_count = sum(1 for chunk in chunks if chunk.embedding)
    payload = to_dict(document)
    payload.update(
        {
            "chunk_count": len(chunks),
            "embedded_chunk_count": embedded_chunk_count,
            "embedding_status": _embedding_status(len(chunks), embedded_chunk_count),
        }
    )
    if include_chunks:
        payload["chunks"] = [
            {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "tenant_id": chunk.tenant_id,
                "title": chunk.title,
                "source_type": chunk.source_type,
                "uri": chunk.uri,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "product_line": chunk.product_line,
                "version": chunk.version,
                "required_permissions": chunk.required_permissions,
                "valid_from": chunk.valid_from,
                "valid_until": chunk.valid_until,
                "source_system": chunk.source_system,
                "embedding_status": "embedded" if chunk.embedding else "pending",
            }
            for chunk in chunks
        ]
        payload["maintenance_policy"] = KNOWLEDGE_DOCUMENT_MAINTENANCE_POLICY
    return payload


def tenant_embedding_summary(tenant_id: str) -> dict[str, Any]:
    chunks = _chunks_for_tenant(tenant_id)
    embedded_chunk_count = sum(1 for chunk in chunks if chunk.embedding)
    return {
        "tenant_id": tenant_id,
        "chunk_count": len(chunks),
        "embedded_chunk_count": embedded_chunk_count,
        "embedding_status": _embedding_status(len(chunks), embedded_chunk_count),
    }


def _safe_dependency_check(name: str, checker) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        status = checker()
        status.setdefault("status", "ok")
    except Exception as exc:
        status = {
            "status": "error",
            "error_type": exc.__class__.__name__,
        }
    status["latency_ms"] = int((time.perf_counter() - started) * 1000)
    status["name"] = name
    return status


def _redis_health() -> dict[str, Any]:
    redis_url = os.getenv("REDIS_URL") or os.getenv("SUPPORT_COPILOT_REDIS_URL")
    required = env_bool("SUPPORT_COPILOT_READINESS_CHECK_REDIS", default=False)
    if not redis_url:
        return {"status": "not_configured", "required": required}

    import redis

    client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.ping()
    finally:
        client.close()
    return {"status": "ok", "required": required}


def _object_storage_health() -> dict[str, Any]:
    endpoint = os.getenv("OBJECT_STORAGE_ENDPOINT") or os.getenv("SUPPORT_COPILOT_OBJECT_STORAGE_ENDPOINT")
    required = env_bool("SUPPORT_COPILOT_READINESS_CHECK_OBJECT_STORAGE", default=False)
    if not endpoint:
        return {"status": "not_configured", "required": required}

    health_url = os.getenv("SUPPORT_COPILOT_OBJECT_STORAGE_HEALTH_URL") or f"{endpoint.rstrip('/')}/minio/health/ready"
    request = urllib.request.Request(health_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status >= 400:
                raise RuntimeError(f"object storage health returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"object storage health returned HTTP {exc.code}") from exc
    return {"status": "ok", "required": required}


def readiness_payload() -> dict[str, Any]:
    store_status = _safe_dependency_check("store", store.healthcheck)
    migrations = _safe_dependency_check("migrations", store.migration_status)
    redis_status = _safe_dependency_check("redis", _redis_health)
    object_storage_status = _safe_dependency_check("object_storage", _object_storage_health)
    redis_status["required"] = bool(
        redis_status.get("required") or env_bool("SUPPORT_COPILOT_READINESS_CHECK_REDIS", default=False)
    )
    object_storage_status["required"] = bool(
        object_storage_status.get("required")
        or env_bool("SUPPORT_COPILOT_READINESS_CHECK_OBJECT_STORAGE", default=False)
    )
    migration_ready = migrations["status"] in {"up_to_date", "not_applicable"}
    required_dependencies = [store_status, migrations]
    for dependency in (redis_status, object_storage_status):
        if dependency.get("required"):
            required_dependencies.append(dependency)

    ready = all(dependency["status"] == "ok" for dependency in required_dependencies if dependency["name"] != "migrations")
    ready = ready and migration_ready
    return {
        "status": "ready" if ready else "not_ready",
        "checked_at": utc_now(),
        "dependencies": {
            "store": store_status,
            "migrations": migrations,
            "redis": redis_status,
            "object_storage": object_storage_status,
        },
    }


@app.get("/api/health/live")
def liveness() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "agentic-support-copilot-api",
        "checked_at": utc_now(),
    }


@app.get("/api/health/ready")
def readiness(response: Response) -> dict[str, Any]:
    payload = readiness_payload()
    if payload["status"] != "ready":
        response.status_code = 503
    return payload


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "graph_engine": graph_engine_name(),
        "workflow_nodes": WORKFLOW_NODES,
        "llm": llm_status_from_env(),
        "embeddings": embedding_provider_status_from_env(),
        "tools": {
            "allowed": sorted(workflow.tools.allowed_tools),
            "configured_backends": workflow.tools.configured_backends(),
            "status": workflow.tools.config_status(),
        },
        "run_queue": active_run_queue().status(),
        "readiness": readiness_payload(),
    }


@app.get("/api/auth/me")
def get_me(principal: Principal = Depends(get_current_principal)) -> dict:
    return principal.as_response()


@app.post("/api/tickets")
def create_ticket(payload: CreateTicketRequest, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, RUN_ROLES, "Creating tickets requires support_agent, approver, or admin role")
    require_tenant_access(principal, payload.tenant_id)
    ticket = store.create_ticket(
        Ticket(
            tenant_id=payload.tenant_id,
            customer_name=payload.customer_name,
            channel=payload.channel,
            subject=payload.subject,
            description=payload.description,
        )
    )
    audit(principal, "ticket_created", "ticket", ticket.id, {"tenant_id": ticket.tenant_id}, tenant_id=ticket.tenant_id)
    return to_dict(ticket)


@app.get("/api/tickets")
def list_tickets(tenant_id: Optional[str] = None, principal: Principal = Depends(get_current_principal)) -> list:
    require_role(principal, TICKET_READ_ROLES, "Reading tickets requires support_agent or admin role")
    requested_tenant_id = resolve_tenant(principal, tenant_id)
    return to_dict(store.list_tickets(tenant_id=requested_tenant_id))


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, TICKET_READ_ROLES, "Reading tickets requires support_agent or admin role")
    try:
        return to_dict(assert_ticket_access(ticket_id, principal))
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.post("/api/runs/{ticket_id}/start")
def start_run(ticket_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, RUN_ROLES, "Starting runs requires support_agent or admin role")
    try:
        ticket = assert_ticket_access(ticket_id, principal)
        run = workflow.create_queued_run(ticket.id, record_queue_step=True)
        response = to_dict(run)
        audit(
            principal,
            "agent_run_requested",
            "agent_run",
            run.id,
            {
                "ticket_id": ticket.id,
                "trace_id": run.trace_id,
                "correlation_id": run.correlation_id,
                "status": run.status,
            },
            tenant_id=ticket.tenant_id,
        )
        active_run_queue().enqueue(run.id)
        return response
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, TRACE_READ_ROLES, "Reading runs requires support_agent, approver, or admin role")
    try:
        run = store.get_run(run_id)
        require_tenant_access(principal, run.tenant_id, hide=True)
        return to_dict(run)
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.get("/api/runs/{run_id}/trace")
def get_trace(run_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, TRACE_READ_ROLES, "Reading traces requires support_agent, approver, or admin role")
    try:
        run = store.get_run(run_id)
        require_tenant_access(principal, run.tenant_id, hide=True)
        return {
            "run": to_dict(run),
            "steps": to_dict(store.get_steps_for_run(run_id)),
            "evidence": to_dict(run.evidence),
            "tool_calls": to_dict(store.get_tool_calls_for_run(run_id)),
            "approval": to_dict(store.get_approval(run.approval_id)) if run.approval_id else None,
        }
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.post("/api/runs/{run_id}/retry")
def retry_run(run_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, RUN_ROLES, "Retrying runs requires support_agent or admin role")
    try:
        failed_run = store.get_run(run_id)
        require_tenant_access(principal, failed_run.tenant_id, hide=True)
        if failed_run.status != "failed":
            raise HTTPException(status_code=409, detail="Only failed runs can be retried")
        ticket = store.get_ticket(failed_run.ticket_id)
        retry = workflow.create_queued_run(ticket.id, record_queue_step=True)
        response = to_dict(retry)
        audit(
            principal,
            "agent_run_retry_requested",
            "agent_run",
            retry.id,
            {
                "ticket_id": ticket.id,
                "retry_of_run_id": failed_run.id,
                "retry_of_trace_id": failed_run.trace_id,
                "trace_id": retry.trace_id,
                "correlation_id": retry.correlation_id,
                "status": retry.status,
            },
            tenant_id=ticket.tenant_id,
        )
        active_run_queue().enqueue(retry.id)
        return response
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, RUN_ROLES, "Cancelling runs requires support_agent or admin role")
    try:
        run = store.get_run(run_id)
        require_tenant_access(principal, run.tenant_id, hide=True)
        if run.status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="Only queued or running runs can be cancelled")
        active_run_queue().request_cancel(run.id)
        cancelled = workflow.cancel_run(run.id, actor=principal.email, reason="Cancelled from API request.")
        audit(
            principal,
            "agent_run_cancel_requested",
            "agent_run",
            run.id,
            {
                "ticket_id": run.ticket_id,
                "trace_id": run.trace_id,
                "correlation_id": run.correlation_id,
                "status": cancelled.status,
            },
            tenant_id=run.tenant_id,
        )
        return to_dict(cancelled)
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/approvals")
def list_approvals(
    status: str = "pending",
    tenant_id: Optional[str] = None,
    principal: Principal = Depends(get_current_principal),
) -> list:
    require_role(principal, APPROVAL_READ_ROLES, "Reading approvals requires approver or admin role")
    requested_tenant_id = resolve_tenant(principal, tenant_id)
    approvals = []
    for approval in store.list_approvals(status=status):
        try:
            ticket = store.get_ticket(approval.ticket_id)
        except NotFoundError:
            continue
        if ticket.tenant_id == requested_tenant_id:
            approvals.append(approval)
    return to_dict(approvals)


@app.post("/api/approvals/{approval_id}/approve")
def approve(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    try:
        approval = store.get_approval(approval_id)
        ticket = assert_ticket_access(approval.ticket_id, principal)
        require_role(principal, APPROVAL_DECISION_ROLES, "Approving replies requires approver or admin role")
        run = workflow.approve(approval_id, decided_by=principal.email, note=payload.note or "")
        decided_approval = store.get_approval(approval_id)
        audit(
            principal,
            "approval_approved_via_api",
            "approval",
            approval_id,
            {
                "ticket_id": ticket.id,
                "run_id": run.id,
                "trace_id": run.trace_id,
                "correlation_id": run.correlation_id,
                "approval_reason": decided_approval.reason,
                "decision_note_summary": clip_text(redact_secrets(decided_approval.decision_note or ""), 400),
                "decided_at": decided_approval.decided_at,
            },
            tenant_id=ticket.tenant_id,
        )
        return to_dict(run)
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/approvals/{approval_id}/reject")
def reject(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    try:
        approval = store.get_approval(approval_id)
        ticket = assert_ticket_access(approval.ticket_id, principal)
        require_role(principal, APPROVAL_DECISION_ROLES, "Rejecting replies requires approver or admin role")
        run = workflow.reject(approval_id, decided_by=principal.email, note=payload.note or "")
        decided_approval = store.get_approval(approval_id)
        audit(
            principal,
            "approval_rejected_via_api",
            "approval",
            approval_id,
            {
                "ticket_id": ticket.id,
                "run_id": run.id,
                "trace_id": run.trace_id,
                "correlation_id": run.correlation_id,
                "approval_reason": decided_approval.reason,
                "decision_note_summary": clip_text(redact_secrets(decided_approval.decision_note or ""), 400),
                "decided_at": decided_approval.decided_at,
            },
            tenant_id=ticket.tenant_id,
        )
        return to_dict(run)
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/knowledge/documents")
def create_document(payload: CreateDocumentRequest, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, KNOWLEDGE_WRITE_ROLES, "Writing knowledge requires knowledge_admin or admin role")
    require_tenant_access(principal, payload.tenant_id)
    document = store.add_document(
        Document(
            tenant_id=payload.tenant_id,
            title=payload.title,
            source_type=payload.source_type,
            uri=payload.uri,
            content=payload.content,
            product_line=payload.product_line or None,
            version=payload.version or None,
            required_permissions=[
                permission.strip().lower()
                for permission in payload.required_permissions
                if permission.strip()
            ],
            valid_from=payload.valid_from or None,
            valid_until=payload.valid_until or None,
            source_system=payload.source_system or None,
        ),
        embed=False,
    )
    response = knowledge_document_response(document)
    audit(
        principal,
        "document_created",
        "document",
        document.id,
        {
            "tenant_id": document.tenant_id,
            "source_type": document.source_type,
            "uri": document.uri,
            "product_line": document.product_line,
            "version": document.version,
            "required_permissions": document.required_permissions,
            "valid_from": document.valid_from,
            "valid_until": document.valid_until,
            "source_system": document.source_system,
            "chunk_count": response["chunk_count"],
            "embedding_status": response["embedding_status"],
        },
        tenant_id=document.tenant_id,
    )
    return response


@app.post("/api/knowledge/embeddings/ingest")
def ingest_embeddings(payload: IngestEmbeddingsRequest, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, KNOWLEDGE_WRITE_ROLES, "Ingesting embeddings requires knowledge_admin or admin role")
    tenant_id = resolve_tenant(principal, payload.tenant_id)
    updated = store.ingest_missing_embeddings(tenant_id=tenant_id)
    summary = tenant_embedding_summary(tenant_id)
    audit(
        principal,
        "embeddings_ingested",
        "tenant",
        tenant_id,
        {"updated_chunks": updated, **summary},
        tenant_id=tenant_id,
    )
    return {"updated_chunks": updated, **summary}


@app.get("/api/knowledge/documents")
def list_documents(tenant_id: Optional[str] = None, principal: Principal = Depends(get_current_principal)) -> list:
    require_role(principal, KNOWLEDGE_READ_ROLES, "Reading knowledge requires knowledge_admin or admin role")
    requested_tenant_id = resolve_tenant(principal, tenant_id)
    return [
        knowledge_document_response(document)
        for document in store.list_documents(tenant_id=requested_tenant_id)
    ]


@app.get("/api/knowledge/documents/{document_id}")
def get_document(document_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, KNOWLEDGE_READ_ROLES, "Reading knowledge requires knowledge_admin or admin role")
    try:
        document = store.get_document(document_id)
        require_tenant_access(principal, document.tenant_id, hide=True)
        return knowledge_document_response(document, include_chunks=True)
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.get("/api/knowledge/policy")
def get_knowledge_policy(principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, KNOWLEDGE_READ_ROLES, "Reading knowledge requires knowledge_admin or admin role")
    return KNOWLEDGE_DOCUMENT_MAINTENANCE_POLICY


def audit_logs_response(
    *,
    tenant_id: Optional[str],
    actor: Optional[str],
    action: Optional[str],
    target: Optional[str],
    start_time: Optional[str],
    end_time: Optional[str],
    limit: int,
    principal: Principal,
) -> list:
    require_role(principal, ADMIN_ROLES, "Reading audit logs requires admin role")
    requested_tenant_id = resolve_tenant(principal, tenant_id)
    return to_dict(
        store.list_audit_logs(
            tenant_id=requested_tenant_id,
            actor=actor,
            action=action,
            target=target,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    )


@app.get("/api/audit-logs")
def list_audit_logs(
    tenant_id: Optional[str] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    target: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 200,
    principal: Principal = Depends(get_current_principal),
) -> list:
    return audit_logs_response(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target=target,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        principal=principal,
    )


@app.get("/api/audit/logs")
def list_audit_logs_legacy(
    tenant_id: Optional[str] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    target: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 200,
    principal: Principal = Depends(get_current_principal),
) -> list:
    return audit_logs_response(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target=target,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        principal=principal,
    )


@app.get("/api/admin/config")
def get_admin_config(principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, ADMIN_ROLES, "Reading system configuration requires admin role")
    return {
        "environment": os.getenv("APP_ENV", "development"),
        "store": os.getenv("SUPPORT_COPILOT_STORE", "postgres"),
        "auth": auth_status_from_env(),
        "llm": llm_status_from_env(),
        "embeddings": embedding_provider_status_from_env(),
        "tools": {
            "allowed": sorted(workflow.tools.allowed_tools),
            "configured_backends": workflow.tools.configured_backends(),
            "status": workflow.tools.config_status(),
        },
    }
