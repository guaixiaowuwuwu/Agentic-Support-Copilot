from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agents import SupportAgentWorkflow
from .auth import (
    APPROVAL_DECISION_ROLES,
    KNOWLEDGE_WRITE_ROLES,
    READ_ROLES,
    RUN_ROLES,
    Principal,
    get_current_principal,
    require_role,
    require_tenant_access,
    resolve_tenant,
)
from .graph import WORKFLOW_NODES, graph_engine_name
from .llm import create_chat_client_from_env, llm_status_from_env
from .models import AuditLog, Document, Ticket, to_dict
from .schemas import ApprovalDecisionRequest, CreateDocumentRequest, CreateTicketRequest, IngestEmbeddingsRequest
from .store import NotFoundError, create_store

store = create_store(seed=True)
workflow = SupportAgentWorkflow(store, chat_client=create_chat_client_from_env())

app = FastAPI(title="Agentic Support Copilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def not_found(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Resource not found: {exc.args[0]}")


def hidden_not_found(exc: HTTPException) -> HTTPException:
    if exc.status_code == 404:
        return not_found(NotFoundError("restricted"))
    return exc


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


def assert_ticket_access(ticket_id: str, principal: Principal) -> Ticket:
    ticket = store.get_ticket(ticket_id)
    require_tenant_access(principal, ticket.tenant_id, hide=True)
    return ticket


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "graph_engine": graph_engine_name(),
        "workflow_nodes": WORKFLOW_NODES,
        "llm": llm_status_from_env(),
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
    require_role(principal, READ_ROLES, "Reading tickets requires a support role")
    requested_tenant_id = resolve_tenant(principal, tenant_id)
    return to_dict(store.list_tickets(tenant_id=requested_tenant_id))


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, READ_ROLES, "Reading tickets requires a support role")
    try:
        return to_dict(assert_ticket_access(ticket_id, principal))
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.post("/api/runs/{ticket_id}/start")
def start_run(ticket_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, RUN_ROLES, "Starting runs requires support_agent, approver, or admin role")
    try:
        ticket = assert_ticket_access(ticket_id, principal)
        run = workflow.start_run(ticket.id)
        audit(principal, "agent_run_requested", "agent_run", run.id, {"ticket_id": ticket.id}, tenant_id=ticket.tenant_id)
        return to_dict(run)
    except NotFoundError as exc:
        raise not_found(exc)
    except HTTPException as exc:
        raise hidden_not_found(exc)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, READ_ROLES, "Reading runs requires a support role")
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
    require_role(principal, READ_ROLES, "Reading traces requires a support role")
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


@app.get("/api/approvals")
def list_approvals(
    status: str = "pending",
    tenant_id: Optional[str] = None,
    principal: Principal = Depends(get_current_principal),
) -> list:
    require_role(principal, APPROVAL_DECISION_ROLES, "Reading approvals requires approver or admin role")
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
        audit(principal, "approval_approved_via_api", "approval", approval_id, {"ticket_id": ticket.id}, tenant_id=ticket.tenant_id)
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
        audit(principal, "approval_rejected_via_api", "approval", approval_id, {"ticket_id": ticket.id}, tenant_id=ticket.tenant_id)
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
        )
    )
    audit(
        principal,
        "document_created",
        "document",
        document.id,
        {"tenant_id": document.tenant_id},
        tenant_id=document.tenant_id,
    )
    return to_dict(document)


@app.post("/api/knowledge/embeddings/ingest")
def ingest_embeddings(payload: IngestEmbeddingsRequest, principal: Principal = Depends(get_current_principal)) -> dict:
    require_role(principal, KNOWLEDGE_WRITE_ROLES, "Ingesting embeddings requires knowledge_admin or admin role")
    tenant_id = resolve_tenant(principal, payload.tenant_id)
    updated = store.ingest_missing_embeddings(tenant_id=tenant_id)
    audit(principal, "embeddings_ingested", "tenant", tenant_id, {"updated_chunks": updated}, tenant_id=tenant_id)
    return {"updated_chunks": updated, "tenant_id": tenant_id}


@app.get("/api/knowledge/documents")
def list_documents(tenant_id: Optional[str] = None, principal: Principal = Depends(get_current_principal)) -> list:
    require_role(principal, READ_ROLES, "Reading knowledge requires a support role")
    requested_tenant_id = resolve_tenant(principal, tenant_id)
    return to_dict(store.list_documents(tenant_id=requested_tenant_id))
