from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agents import SupportAgentWorkflow
from .graph import WORKFLOW_NODES, graph_engine_name
from .models import Document, Ticket, to_dict
from .schemas import ApprovalDecisionRequest, CreateDocumentRequest, CreateTicketRequest
from .store import NotFoundError, create_store

store = create_store(seed=True)
workflow = SupportAgentWorkflow(store)

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


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "graph_engine": graph_engine_name(),
        "workflow_nodes": WORKFLOW_NODES,
    }


@app.post("/api/tickets")
def create_ticket(payload: CreateTicketRequest) -> dict:
    ticket = store.create_ticket(
        Ticket(
            tenant_id=payload.tenant_id,
            customer_name=payload.customer_name,
            channel=payload.channel,
            subject=payload.subject,
            description=payload.description,
        )
    )
    return to_dict(ticket)


@app.get("/api/tickets")
def list_tickets(tenant_id: str = "acme") -> list:
    return to_dict(store.list_tickets(tenant_id=tenant_id))


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict:
    try:
        return to_dict(store.get_ticket(ticket_id))
    except NotFoundError as exc:
        raise not_found(exc)


@app.post("/api/runs/{ticket_id}/start")
def start_run(ticket_id: str) -> dict:
    try:
        return to_dict(workflow.start_run(ticket_id))
    except NotFoundError as exc:
        raise not_found(exc)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return to_dict(store.get_run(run_id))
    except NotFoundError as exc:
        raise not_found(exc)


@app.get("/api/runs/{run_id}/trace")
def get_trace(run_id: str) -> dict:
    try:
        run = store.get_run(run_id)
        return {
            "run": to_dict(run),
            "steps": to_dict(store.get_steps_for_run(run_id)),
            "evidence": to_dict(run.evidence),
            "tool_calls": to_dict(store.get_tool_calls_for_run(run_id)),
            "approval": to_dict(store.get_approval(run.approval_id)) if run.approval_id else None,
        }
    except NotFoundError as exc:
        raise not_found(exc)


@app.get("/api/approvals")
def list_approvals(status: str = "pending") -> list:
    return to_dict(store.list_approvals(status=status))


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str, payload: ApprovalDecisionRequest) -> dict:
    try:
        return to_dict(workflow.approve(approval_id, decided_by=payload.decided_by, note=payload.note or ""))
    except NotFoundError as exc:
        raise not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str, payload: ApprovalDecisionRequest) -> dict:
    try:
        return to_dict(workflow.reject(approval_id, decided_by=payload.decided_by, note=payload.note or ""))
    except NotFoundError as exc:
        raise not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/knowledge/documents")
def create_document(payload: CreateDocumentRequest) -> dict:
    document = store.add_document(
        Document(
            tenant_id=payload.tenant_id,
            title=payload.title,
            source_type=payload.source_type,
            uri=payload.uri,
            content=payload.content,
        )
    )
    return to_dict(document)


@app.get("/api/knowledge/documents")
def list_documents(tenant_id: str = "acme") -> list:
    return to_dict(store.list_documents(tenant_id=tenant_id))
