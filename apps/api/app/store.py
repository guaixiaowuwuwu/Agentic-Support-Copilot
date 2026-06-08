from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Protocol, Sequence
from uuid import UUID

from .knowledge import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingModel,
    RetrievalFilters,
    chunk_document,
    chunk_matches_filters,
    create_embedding_model_from_env,
    embed_chunk,
    embedding_text_for_chunk,
    keyword_score_for_chunk,
)
from .models import (
    AgentRun,
    AgentStep,
    Approval,
    AuditLog,
    Document,
    DocumentChunk,
    Evidence,
    Ticket,
    ToolCall,
)
from .security import sanitize_for_log
from .time_utils import utc_now

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - exercised only when optional deps are missing.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment]

try:
    from pgvector import Vector
    from pgvector.psycopg import register_vector
except ImportError:  # pragma: no cover - exercised only when optional deps are missing.
    Vector = None  # type: ignore[assignment]
    register_vector = None  # type: ignore[assignment]


class NotFoundError(KeyError):
    pass


class Store(Protocol):
    def seed(self) -> None:
        ...

    def add_audit(self, audit: AuditLog) -> AuditLog:
        ...

    def list_audit_logs(
        self,
        tenant_id: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        target: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200,
    ) -> List[AuditLog]:
        ...

    def create_ticket(self, ticket: Ticket) -> Ticket:
        ...

    def list_tickets(self, tenant_id: Optional[str] = None) -> List[Ticket]:
        ...

    def get_ticket(self, ticket_id: str) -> Ticket:
        ...

    def update_ticket(self, ticket: Ticket) -> Ticket:
        ...

    def add_document(self, document: Document, *, embed: bool = True) -> Document:
        ...

    def list_documents(self, tenant_id: Optional[str] = None) -> List[Document]:
        ...

    def get_document(self, document_id: str) -> Document:
        ...

    def list_chunks(self) -> List[DocumentChunk]:
        ...

    def ingest_missing_embeddings(self, tenant_id: Optional[str] = None) -> int:
        ...

    def create_run(self, run: AgentRun) -> AgentRun:
        ...

    def get_run(self, run_id: str) -> AgentRun:
        ...

    def update_run(self, run: AgentRun) -> AgentRun:
        ...

    def add_step(self, step: AgentStep) -> AgentStep:
        ...

    def update_step(self, step: AgentStep) -> AgentStep:
        ...

    def get_steps_for_run(self, run_id: str) -> List[AgentStep]:
        ...

    def add_tool_call(self, tool_call: ToolCall) -> ToolCall:
        ...

    def get_tool_calls_for_run(self, run_id: str) -> List[ToolCall]:
        ...

    def create_approval(self, approval: Approval) -> Approval:
        ...

    def get_approval(self, approval_id: str) -> Approval:
        ...

    def list_approvals(self, status: Optional[str] = None) -> List[Approval]:
        ...

    def update_approval(self, approval: Approval) -> Approval:
        ...


class InMemoryStore:
    def __init__(
        self,
        seed: bool = True,
        embedding_model: EmbeddingModel = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._lock = RLock()
        self.embedding_model = embedding_model
        self.tickets: Dict[str, Ticket] = {}
        self.documents: Dict[str, Document] = {}
        self.chunks: Dict[str, DocumentChunk] = {}
        self.runs: Dict[str, AgentRun] = {}
        self.steps: Dict[str, AgentStep] = {}
        self.tool_calls: Dict[str, ToolCall] = {}
        self.approvals: Dict[str, Approval] = {}
        self.audit_logs: Dict[str, AuditLog] = {}

        if seed:
            self.seed()

    def seed(self) -> None:
        if self.documents:
            return

        self.add_document(
            Document(
                tenant_id="acme",
                title="API Authentication Runbook",
                source_type="api_doc",
                uri="kb://api/authentication-runbook",
                product_line="api",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "401 Unauthorized responses are usually caused by a missing Authorization header, "
                    "an expired access token, invalid API key, or insufficient OAuth scope.\n\n"
                    "Support should ask for request_id and timestamp, check auth service logs, verify "
                    "the token expiration time, and confirm that the customer is using Bearer token syntax.\n\n"
                    "Do not request raw secrets. Ask the customer to rotate credentials if an API key may be exposed."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Historical Ticket: Expired API Token",
                source_type="historical_ticket",
                uri="ticket://hist-1042",
                product_line="api",
                version="v1",
                required_permissions=["support_agent"],
                source_system="zendesk",
                content=(
                    "A customer reported API calls returning 401 after a deployment. The root cause was an "
                    "expired service account token. The support reply included steps to create a new token, "
                    "validate scopes, and retry the request with the same request_id."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Support Escalation Policy",
                source_type="policy",
                uri="kb://policy/escalation",
                product_line="platform",
                required_permissions=["support_agent"],
                source_system="policy",
                content=(
                    "Any customer-facing reply generated by an agent requires human approval before sending. "
                    "Actions that write to Jira are allowed for support engineers. Actions that modify customer "
                    "data require manual escalation and are not available to the MVP tool agent."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Billing Invoice Runbook",
                source_type="runbook",
                uri="kb://billing/invoice-runbook",
                product_line="billing",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "Billing and invoice questions should be checked against the account billing period, "
                    "invoice number, payment status, tax settings, subscription plan, and proration events.\n\n"
                    "Support should explain visible invoice line items and route refund, credit memo, or contract "
                    "changes to billing specialists. Do not promise a refund without approval."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Bug Report Triage Runbook",
                source_type="runbook",
                uri="kb://platform/bug-triage",
                product_line="platform",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "Bug reports require a reproducible scenario, affected version, environment, expected behavior, "
                    "actual behavior, screenshots or logs, and recent deployment context.\n\n"
                    "Support should search existing Jira and GitHub issues before escalating, then summarize impact "
                    "and workaround status for the customer."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Outage Communications Runbook",
                source_type="runbook",
                uri="kb://platform/outage-communications",
                product_line="platform",
                version="v1",
                required_permissions=["support_agent"],
                source_system="statuspage",
                content=(
                    "Outage, production down, all customers impacted, or SEV1 reports are P1 incidents. "
                    "Support should check status page signals, incident commander notes, and recent deploys.\n\n"
                    "Customer replies should acknowledge impact, avoid unsupported ETAs, and ask for affected region, "
                    "tenant, timestamps, request ids, and business impact."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="General Support Intake Guide",
                source_type="runbook",
                uri="kb://support/general-intake",
                product_line="support",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "General support questions should be clarified before diagnosis. Ask for the product area, "
                    "tenant, user role, expected outcome, actual outcome, timestamps, and screenshots if available.\n\n"
                    "If the request has no matching knowledge evidence, route it to manual review instead of "
                    "inventing product behavior."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="globex",
                title="Globex Private Incident",
                source_type="historical_ticket",
                uri="ticket://globex-secret",
                product_line="api",
                version="v1",
                required_permissions=["support_agent"],
                source_system="zendesk",
                content="Globex-only private API outage details. This document must never appear in Acme searches.",
            )
        )

    def add_audit(self, audit: AuditLog) -> AuditLog:
        audit.metadata = sanitize_for_log(audit.metadata)
        with self._lock:
            self.audit_logs[audit.id] = audit
        return audit

    def list_audit_logs(
        self,
        tenant_id: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        target: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200,
    ) -> List[AuditLog]:
        audit_logs = list(self.audit_logs.values())
        if tenant_id:
            audit_logs = [audit for audit in audit_logs if audit.tenant_id == tenant_id]
        if actor:
            actor_query = actor.lower()
            audit_logs = [audit for audit in audit_logs if actor_query in audit.actor.lower()]
        if action:
            action_query = action.lower()
            audit_logs = [audit for audit in audit_logs if action_query in audit.action.lower()]
        if target:
            target_query = target.lower()
            audit_logs = [
                audit
                for audit in audit_logs
                if target_query in audit.target_type.lower()
                or target_query in audit.target_id.lower()
                or target_query in str(audit.metadata).lower()
            ]
        start_at = _parse_time_filter(start_time)
        end_at = _parse_time_filter(end_time)
        if start_at:
            audit_logs = [
                audit
                for audit in audit_logs
                if (created_at := _parse_time_filter(audit.created_at)) is not None and created_at >= start_at
            ]
        if end_at:
            audit_logs = [
                audit
                for audit in audit_logs
                if (created_at := _parse_time_filter(audit.created_at)) is not None and created_at <= end_at
            ]
        bounded_limit = min(max(int(limit or 200), 1), 500)
        return sorted(audit_logs, key=lambda item: item.created_at, reverse=True)[:bounded_limit]

    def create_ticket(self, ticket: Ticket) -> Ticket:
        with self._lock:
            self.tickets[ticket.id] = ticket
        return ticket

    def list_tickets(self, tenant_id: Optional[str] = None) -> List[Ticket]:
        tickets = list(self.tickets.values())
        if tenant_id:
            tickets = [ticket for ticket in tickets if ticket.tenant_id == tenant_id]
        return sorted(tickets, key=lambda item: item.created_at, reverse=True)

    def get_ticket(self, ticket_id: str) -> Ticket:
        try:
            return self.tickets[ticket_id]
        except KeyError as exc:
            raise NotFoundError(ticket_id) from exc

    def update_ticket(self, ticket: Ticket) -> Ticket:
        ticket.updated_at = utc_now()
        with self._lock:
            self.tickets[ticket.id] = ticket
        return ticket

    def add_document(self, document: Document, *, embed: bool = True) -> Document:
        with self._lock:
            self.documents[document.id] = document
            for chunk in chunk_document(document):
                if embed:
                    embed_chunk(chunk, self.embedding_model)
                self.chunks[chunk.id] = chunk
        return document

    def list_documents(self, tenant_id: Optional[str] = None) -> List[Document]:
        documents = list(self.documents.values())
        if tenant_id:
            documents = [document for document in documents if document.tenant_id == tenant_id]
        return sorted(documents, key=lambda item: item.created_at, reverse=True)

    def get_document(self, document_id: str) -> Document:
        try:
            return self.documents[document_id]
        except KeyError as exc:
            raise NotFoundError(document_id) from exc

    def list_chunks(self) -> List[DocumentChunk]:
        return list(self.chunks.values())

    def ingest_missing_embeddings(self, tenant_id: Optional[str] = None) -> int:
        updated = 0
        with self._lock:
            for chunk in self.chunks.values():
                if tenant_id and chunk.tenant_id != tenant_id:
                    continue
                if chunk.embedding:
                    continue
                embed_chunk(chunk, self.embedding_model)
                updated += 1
        return updated

    def create_run(self, run: AgentRun) -> AgentRun:
        with self._lock:
            self.runs[run.id] = run
            ticket = self.get_ticket(run.ticket_id)
            ticket.run_ids.append(run.id)
            ticket.status = "queued" if run.status == "queued" else "running"
            self.update_ticket(ticket)
        return run

    def get_run(self, run_id: str) -> AgentRun:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise NotFoundError(run_id) from exc

    def update_run(self, run: AgentRun) -> AgentRun:
        run.updated_at = utc_now()
        with self._lock:
            self.runs[run.id] = run
        return run

    def add_step(self, step: AgentStep) -> AgentStep:
        with self._lock:
            self.steps[step.id] = step
            run = self.get_run(step.run_id)
            run.step_ids.append(step.id)
            run.current_node = step.name
            self.update_run(run)
        return step

    def update_step(self, step: AgentStep) -> AgentStep:
        with self._lock:
            if step.id not in self.steps:
                raise NotFoundError(step.id)
            self.steps[step.id] = step
            run = self.get_run(step.run_id)
            run.current_node = step.name
            self.update_run(run)
        return step

    def get_steps_for_run(self, run_id: str) -> List[AgentStep]:
        run = self.get_run(run_id)
        return [self.steps[step_id] for step_id in run.step_ids]

    def add_tool_call(self, tool_call: ToolCall) -> ToolCall:
        with self._lock:
            self.tool_calls[tool_call.id] = tool_call
            run = self.get_run(tool_call.run_id)
            run.tool_call_ids.append(tool_call.id)
            self.update_run(run)
        return tool_call

    def get_tool_calls_for_run(self, run_id: str) -> List[ToolCall]:
        run = self.get_run(run_id)
        return [self.tool_calls[call_id] for call_id in run.tool_call_ids]

    def create_approval(self, approval: Approval) -> Approval:
        with self._lock:
            self.approvals[approval.id] = approval
            run = self.get_run(approval.run_id)
            run.approval_id = approval.id
            self.update_run(run)
        return approval

    def get_approval(self, approval_id: str) -> Approval:
        try:
            return self.approvals[approval_id]
        except KeyError as exc:
            raise NotFoundError(approval_id) from exc

    def list_approvals(self, status: Optional[str] = None) -> List[Approval]:
        approvals = list(self.approvals.values())
        if status:
            approvals = [approval for approval in approvals if approval.status == status]
        return sorted(approvals, key=lambda item: item.created_at, reverse=True)

    def update_approval(self, approval: Approval) -> Approval:
        with self._lock:
            self.approvals[approval.id] = approval
        return approval


DEFAULT_DATABASE_URL = "postgresql://support:support@127.0.0.1:5432/support_copilot"
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "infra" / "schema.sql"


def _uuid(value: str) -> UUID:
    return UUID(str(value))


def _uuid_list(values: List[str]) -> List[UUID]:
    return [_uuid(value) for value in values]


def _jsonb(value: Dict[str, Any] | List[Any]) -> Any:
    if Jsonb is None:
        raise RuntimeError("psycopg is required for PostgreSQL storage")
    return Jsonb(value)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _str_id(value: Any) -> str:
    return str(value)


def _str_id_list(values: Optional[List[Any]]) -> List[str]:
    return [str(value) for value in values or []]


def _float_list(value: Any) -> Optional[List[float]]:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _pg_vector(value: Sequence[float]) -> Any:
    if Vector is None:
        return list(value)
    return Vector(value)


def _parse_time_filter(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PostgresStore:
    def __init__(
        self,
        database_url: str = DEFAULT_DATABASE_URL,
        seed: bool = True,
        schema_path: Path = DEFAULT_SCHEMA_PATH,
        ensure_schema: bool = True,
        embedding_model: EmbeddingModel = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg is required for PostgreSQL storage")
        if register_vector is None or Vector is None:
            raise RuntimeError("pgvector is required for PostgreSQL vector storage")

        self.database_url = database_url
        self.schema_path = schema_path
        self._lock = RLock()
        self.embedding_model = embedding_model

        if ensure_schema:
            self.ensure_schema()
        if seed:
            self.seed()
        if ensure_schema:
            self.ensure_document_chunks()
            self.ingest_missing_embeddings()

    def _connect(self, register_vectors: bool = True) -> Any:
        conn = psycopg.connect(self.database_url, row_factory=dict_row)
        if register_vectors:
            register_vector(conn)
        return conn

    def ensure_schema(self) -> None:
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with self._lock, self._connect(register_vectors=False) as conn:
            conn.execute(schema_sql)

    def seed(self) -> None:
        if self.list_documents():
            return

        self.add_document(
            Document(
                tenant_id="acme",
                title="API Authentication Runbook",
                source_type="api_doc",
                uri="kb://api/authentication-runbook",
                product_line="api",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "401 Unauthorized responses are usually caused by a missing Authorization header, "
                    "an expired access token, invalid API key, or insufficient OAuth scope.\n\n"
                    "Support should ask for request_id and timestamp, check auth service logs, verify "
                    "the token expiration time, and confirm that the customer is using Bearer token syntax.\n\n"
                    "Do not request raw secrets. Ask the customer to rotate credentials if an API key may be exposed."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Historical Ticket: Expired API Token",
                source_type="historical_ticket",
                uri="ticket://hist-1042",
                product_line="api",
                version="v1",
                required_permissions=["support_agent"],
                source_system="zendesk",
                content=(
                    "A customer reported API calls returning 401 after a deployment. The root cause was an "
                    "expired service account token. The support reply included steps to create a new token, "
                    "validate scopes, and retry the request with the same request_id."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Support Escalation Policy",
                source_type="policy",
                uri="kb://policy/escalation",
                product_line="platform",
                required_permissions=["support_agent"],
                source_system="policy",
                content=(
                    "Any customer-facing reply generated by an agent requires human approval before sending. "
                    "Actions that write to Jira are allowed for support engineers. Actions that modify customer "
                    "data require manual escalation and are not available to the MVP tool agent."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Billing Invoice Runbook",
                source_type="runbook",
                uri="kb://billing/invoice-runbook",
                product_line="billing",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "Billing and invoice questions should be checked against the account billing period, "
                    "invoice number, payment status, tax settings, subscription plan, and proration events.\n\n"
                    "Support should explain visible invoice line items and route refund, credit memo, or contract "
                    "changes to billing specialists. Do not promise a refund without approval."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Bug Report Triage Runbook",
                source_type="runbook",
                uri="kb://platform/bug-triage",
                product_line="platform",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "Bug reports require a reproducible scenario, affected version, environment, expected behavior, "
                    "actual behavior, screenshots or logs, and recent deployment context.\n\n"
                    "Support should search existing Jira and GitHub issues before escalating, then summarize impact "
                    "and workaround status for the customer."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="Outage Communications Runbook",
                source_type="runbook",
                uri="kb://platform/outage-communications",
                product_line="platform",
                version="v1",
                required_permissions=["support_agent"],
                source_system="statuspage",
                content=(
                    "Outage, production down, all customers impacted, or SEV1 reports are P1 incidents. "
                    "Support should check status page signals, incident commander notes, and recent deploys.\n\n"
                    "Customer replies should acknowledge impact, avoid unsupported ETAs, and ask for affected region, "
                    "tenant, timestamps, request ids, and business impact."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="acme",
                title="General Support Intake Guide",
                source_type="runbook",
                uri="kb://support/general-intake",
                product_line="support",
                version="v1",
                required_permissions=["support_agent"],
                source_system="confluence",
                content=(
                    "General support questions should be clarified before diagnosis. Ask for the product area, "
                    "tenant, user role, expected outcome, actual outcome, timestamps, and screenshots if available.\n\n"
                    "If the request has no matching knowledge evidence, route it to manual review instead of "
                    "inventing product behavior."
                ),
            )
        )
        self.add_document(
            Document(
                tenant_id="globex",
                title="Globex Private Incident",
                source_type="historical_ticket",
                uri="ticket://globex-secret",
                product_line="api",
                version="v1",
                required_permissions=["support_agent"],
                source_system="zendesk",
                content="Globex-only private API outage details. This document must never appear in Acme searches.",
            )
        )

    def ensure_document_chunks(self) -> int:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*
                FROM documents d
                WHERE NOT EXISTS (
                    SELECT 1 FROM document_chunks c WHERE c.document_id = d.id
                )
                ORDER BY d.created_at ASC
                """
            ).fetchall()

            for row in rows:
                document = self._document_from_row(row)
                for chunk in chunk_document(document):
                    embed_chunk(chunk, self.embedding_model)
                    conn.execute(
                        """
                        INSERT INTO document_chunks (
                            id, document_id, tenant_id, title, source_type, uri, content, chunk_index,
                            product_line, version, required_permissions, valid_from, valid_until, source_system,
                            embedding
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            _uuid(chunk.id),
                            _uuid(chunk.document_id),
                            chunk.tenant_id,
                            chunk.title,
                            chunk.source_type,
                            chunk.uri,
                            chunk.content,
                            chunk.chunk_index,
                            chunk.product_line,
                            chunk.version,
                            chunk.required_permissions,
                            chunk.valid_from,
                            chunk.valid_until,
                            chunk.source_system,
                            _pg_vector(chunk.embedding or []),
                        ),
                    )
        return len(rows)

    def add_audit(self, audit: AuditLog) -> AuditLog:
        audit.metadata = sanitize_for_log(audit.metadata)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO audit_logs (
                    id, tenant_id, actor, action, target_type, target_id, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(audit.id),
                    audit.tenant_id,
                    audit.actor,
                    audit.action,
                    audit.target_type,
                    audit.target_id,
                    _jsonb(audit.metadata),
                    audit.created_at,
                ),
            ).fetchone()
            return self._audit_from_row(row)

    def list_audit_logs(
        self,
        tenant_id: Optional[str] = None,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        target: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200,
    ) -> List[AuditLog]:
        where: List[str] = []
        params: List[Any] = []
        bounded_limit = min(max(int(limit or 200), 1), 500)
        if tenant_id:
            where.append("tenant_id = %s")
            params.append(tenant_id)
        if actor:
            where.append("actor ILIKE %s")
            params.append(f"%{actor}%")
        if action:
            where.append("action ILIKE %s")
            params.append(f"%{action}%")
        if target:
            where.append("(target_type ILIKE %s OR target_id ILIKE %s OR metadata::text ILIKE %s)")
            target_query = f"%{target}%"
            params.extend([target_query, target_query, target_query])
        if start_time:
            where.append("created_at >= %s")
            params.append(start_time)
        if end_time:
            where.append("created_at <= %s")
            params.append(end_time)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_logs {where_sql} ORDER BY created_at DESC LIMIT %s",
                (*params, bounded_limit),
            ).fetchall()
            return [self._audit_from_row(row) for row in rows]

    def create_ticket(self, ticket: Ticket) -> Ticket:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO tickets (
                    id, tenant_id, customer_name, channel, subject, description, status,
                    priority, issue_type, final_reply, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(ticket.id),
                    ticket.tenant_id,
                    ticket.customer_name,
                    ticket.channel,
                    ticket.subject,
                    ticket.description,
                    ticket.status,
                    ticket.priority,
                    ticket.issue_type,
                    ticket.final_reply,
                    ticket.created_at,
                    ticket.updated_at,
                ),
            ).fetchone()
            return self._ticket_from_row(conn, row)

    def list_tickets(self, tenant_id: Optional[str] = None) -> List[Ticket]:
        with self._connect() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM tickets WHERE tenant_id = %s ORDER BY created_at DESC",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
            return [self._ticket_from_row(conn, row) for row in rows]

    def get_ticket(self, ticket_id: str) -> Ticket:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE id = %s", (_uuid(ticket_id),)).fetchone()
            if row is None:
                raise NotFoundError(ticket_id)
            return self._ticket_from_row(conn, row)

    def update_ticket(self, ticket: Ticket) -> Ticket:
        ticket.updated_at = utc_now()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                UPDATE tickets
                SET tenant_id = %s,
                    customer_name = %s,
                    channel = %s,
                    subject = %s,
                    description = %s,
                    status = %s,
                    priority = %s,
                    issue_type = %s,
                    final_reply = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    ticket.tenant_id,
                    ticket.customer_name,
                    ticket.channel,
                    ticket.subject,
                    ticket.description,
                    ticket.status,
                    ticket.priority,
                    ticket.issue_type,
                    ticket.final_reply,
                    ticket.updated_at,
                    _uuid(ticket.id),
                ),
            ).fetchone()
            if row is None:
                raise NotFoundError(ticket.id)
            return self._ticket_from_row(conn, row)

    def add_document(self, document: Document, *, embed: bool = True) -> Document:
        chunks = chunk_document(document)
        if embed:
            for chunk in chunks:
                embed_chunk(chunk, self.embedding_model)

        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO documents (
                    id, tenant_id, title, source_type, uri, content, product_line, version,
                    required_permissions, valid_from, valid_until, source_system, status, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(document.id),
                    document.tenant_id,
                    document.title,
                    document.source_type,
                    document.uri,
                    document.content,
                    document.product_line,
                    document.version,
                    document.required_permissions,
                    document.valid_from,
                    document.valid_until,
                    document.source_system,
                    document.status,
                    document.created_at,
                    document.updated_at,
                ),
            ).fetchone()
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO document_chunks (
                        id, document_id, tenant_id, title, source_type, uri, content, chunk_index,
                        product_line, version, required_permissions, valid_from, valid_until, source_system,
                        embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        _uuid(chunk.id),
                        _uuid(chunk.document_id),
                        chunk.tenant_id,
                        chunk.title,
                        chunk.source_type,
                        chunk.uri,
                        chunk.content,
                        chunk.chunk_index,
                        chunk.product_line,
                        chunk.version,
                        chunk.required_permissions,
                        chunk.valid_from,
                        chunk.valid_until,
                        chunk.source_system,
                        _pg_vector(chunk.embedding) if chunk.embedding else None,
                    ),
                )
            return self._document_from_row(row)

    def list_documents(self, tenant_id: Optional[str] = None) -> List[Document]:
        with self._connect() as conn:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE tenant_id = %s ORDER BY created_at DESC",
                    (tenant_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
            return [self._document_from_row(row) for row in rows]

    def get_document(self, document_id: str) -> Document:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = %s", (_uuid(document_id),)).fetchone()
            if row is None:
                raise NotFoundError(document_id)
            return self._document_from_row(row)

    def list_chunks(self) -> List[DocumentChunk]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM document_chunks ORDER BY document_id, chunk_index").fetchall()
            return [self._chunk_from_row(row) for row in rows]

    def ingest_missing_embeddings(self, tenant_id: Optional[str] = None) -> int:
        where_clause = "WHERE embedding IS NULL"
        params: tuple[Any, ...] = ()
        if tenant_id:
            where_clause += " AND tenant_id = %s"
            params = (tenant_id,)

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM document_chunks
                {where_clause}
                ORDER BY document_id, chunk_index
                """,
                params,
            ).fetchall()

            for row in rows:
                chunk = self._chunk_from_row(row)
                embedding = self.embedding_model.embed(embedding_text_for_chunk(chunk))
                conn.execute(
                    "UPDATE document_chunks SET embedding = %s WHERE id = %s",
                    (_pg_vector(embedding), row["id"]),
                )

        return len(rows)

    def search_chunks_by_embedding(
        self,
        tenant_id: str,
        embedding: Sequence[float],
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        where, filter_params = self._retrieval_filter_where(filters)
        where_sql = " AND ".join(["tenant_id = %s", "embedding IS NOT NULL", *where])
        candidate_limit = max(limit * 8, 40)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    document_id,
                    tenant_id,
                    title,
                    source_type,
                    uri,
                    content,
                    chunk_index,
                    product_line,
                    version,
                    required_permissions,
                    valid_from,
                    valid_until,
                    source_system,
                    embedding,
                    1 - (embedding <=> %s) AS score
                FROM document_chunks
                WHERE {where_sql}
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (
                    _pg_vector(embedding),
                    tenant_id,
                    *filter_params,
                    _pg_vector(embedding),
                    candidate_limit,
                ),
            ).fetchall()

        evidence: List[Evidence] = []
        for row in rows:
            chunk = self._chunk_from_row(row)
            if not chunk_matches_filters(chunk, filters):
                continue
            score = float(row["score"] or 0)
            evidence.append(self._evidence_from_chunk(chunk, score, vector_score=score, retrieval_mode="vector"))
            if len(evidence) >= limit:
                break
        return evidence

    def search_chunks_by_keyword(
        self,
        tenant_id: str,
        query: str,
        limit: int = 4,
        filters: Optional[RetrievalFilters] = None,
    ) -> List[Evidence]:
        where, filter_params = self._retrieval_filter_where(filters)
        where_sql = " AND ".join(["tenant_id = %s", *where])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM document_chunks
                WHERE {where_sql}
                ORDER BY document_id, chunk_index
                LIMIT %s
                """,
                (tenant_id, *filter_params, 500),
            ).fetchall()

        scored: List[tuple[float, DocumentChunk]] = []
        for row in rows:
            chunk = self._chunk_from_row(row)
            if not chunk_matches_filters(chunk, filters):
                continue
            score = keyword_score_for_chunk(query, chunk)
            if score <= 0:
                continue
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            self._evidence_from_chunk(chunk, score, keyword_score=score, retrieval_mode="keyword")
            for score, chunk in scored[:limit]
        ]

    def create_run(self, run: AgentRun) -> AgentRun:
        with self._lock, self._connect() as conn:
            ticket = conn.execute("SELECT * FROM tickets WHERE id = %s", (_uuid(run.ticket_id),)).fetchone()
            if ticket is None:
                raise NotFoundError(run.ticket_id)

            row = conn.execute(
                """
                INSERT INTO agent_runs (
                    id, ticket_id, tenant_id, trace_id, correlation_id, status, current_node, triage, evidence,
                    verifier_report, final_reply, approval_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(run.id),
                    _uuid(run.ticket_id),
                    run.tenant_id,
                    run.trace_id,
                    run.correlation_id,
                    run.status,
                    run.current_node,
                    _jsonb(run.triage),
                    _jsonb([self._evidence_to_json(item) for item in run.evidence]),
                    _jsonb(run.verifier_report),
                    run.final_reply,
                    _uuid(run.approval_id) if run.approval_id else None,
                    run.created_at,
                    run.updated_at,
                ),
            ).fetchone()
            ticket_status = "queued" if run.status == "queued" else "running"
            conn.execute(
                "UPDATE tickets SET status = %s, updated_at = %s WHERE id = %s",
                (ticket_status, utc_now(), _uuid(run.ticket_id)),
            )
            return self._run_from_row(conn, row)

    def get_run(self, run_id: str) -> AgentRun:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id = %s", (_uuid(run_id),)).fetchone()
            if row is None:
                raise NotFoundError(run_id)
            return self._run_from_row(conn, row)

    def update_run(self, run: AgentRun) -> AgentRun:
        run.updated_at = utc_now()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                UPDATE agent_runs
                SET ticket_id = %s,
                    tenant_id = %s,
                    trace_id = %s,
                    correlation_id = %s,
                    status = %s,
                    current_node = %s,
                    triage = %s,
                    evidence = %s,
                    verifier_report = %s,
                    final_reply = %s,
                    approval_id = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    _uuid(run.ticket_id),
                    run.tenant_id,
                    run.trace_id,
                    run.correlation_id,
                    run.status,
                    run.current_node,
                    _jsonb(run.triage),
                    _jsonb([self._evidence_to_json(item) for item in run.evidence]),
                    _jsonb(run.verifier_report),
                    run.final_reply,
                    _uuid(run.approval_id) if run.approval_id else None,
                    run.updated_at,
                    _uuid(run.id),
                ),
            ).fetchone()
            if row is None:
                raise NotFoundError(run.id)
            return self._run_from_row(conn, row)

    def add_step(self, step: AgentStep) -> AgentStep:
        with self._lock, self._connect() as conn:
            run = conn.execute("SELECT * FROM agent_runs WHERE id = %s", (_uuid(step.run_id),)).fetchone()
            if run is None:
                raise NotFoundError(step.run_id)

            row = conn.execute(
                """
                INSERT INTO agent_steps (
                    id, run_id, name, status, summary, latency_ms, token_count,
                    evidence_ids, tool_call_ids, started_at, ended_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(step.id),
                    _uuid(step.run_id),
                    step.name,
                    step.status,
                    step.summary,
                    step.latency_ms,
                    step.token_count,
                    step.evidence_ids,
                    _uuid_list(step.tool_call_ids),
                    step.started_at,
                    step.ended_at,
                ),
            ).fetchone()
            conn.execute(
                "UPDATE agent_runs SET current_node = %s, updated_at = %s WHERE id = %s",
                (step.name, utc_now(), _uuid(step.run_id)),
            )
            return self._step_from_row(row)

    def update_step(self, step: AgentStep) -> AgentStep:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                UPDATE agent_steps
                SET run_id = %s,
                    name = %s,
                    status = %s,
                    summary = %s,
                    latency_ms = %s,
                    token_count = %s,
                    evidence_ids = %s,
                    tool_call_ids = %s,
                    started_at = %s,
                    ended_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    _uuid(step.run_id),
                    step.name,
                    step.status,
                    step.summary,
                    step.latency_ms,
                    step.token_count,
                    step.evidence_ids,
                    _uuid_list(step.tool_call_ids),
                    step.started_at,
                    step.ended_at,
                    _uuid(step.id),
                ),
            ).fetchone()
            if row is None:
                raise NotFoundError(step.id)
            conn.execute(
                "UPDATE agent_runs SET current_node = %s, updated_at = %s WHERE id = %s",
                (step.name, utc_now(), _uuid(step.run_id)),
            )
            return self._step_from_row(row)

    def get_steps_for_run(self, run_id: str) -> List[AgentStep]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM agent_runs WHERE id = %s", (_uuid(run_id),)).fetchone() is None:
                raise NotFoundError(run_id)
            rows = conn.execute(
                "SELECT * FROM agent_steps WHERE run_id = %s ORDER BY started_at ASC, id ASC",
                (_uuid(run_id),),
            ).fetchall()
            return [self._step_from_row(row) for row in rows]

    def add_tool_call(self, tool_call: ToolCall) -> ToolCall:
        with self._lock, self._connect() as conn:
            run = conn.execute("SELECT * FROM agent_runs WHERE id = %s", (_uuid(tool_call.run_id),)).fetchone()
            if run is None:
                raise NotFoundError(tool_call.run_id)

            row = conn.execute(
                """
                INSERT INTO tool_calls (
                    id, run_id, tool_name, status, input_summary, output_summary, started_at, ended_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(tool_call.id),
                    _uuid(tool_call.run_id),
                    tool_call.tool_name,
                    tool_call.status,
                    tool_call.input_summary,
                    tool_call.output_summary,
                    tool_call.started_at,
                    tool_call.ended_at,
                ),
            ).fetchone()
            conn.execute(
                "UPDATE agent_runs SET updated_at = %s WHERE id = %s",
                (utc_now(), _uuid(tool_call.run_id)),
            )
            return self._tool_call_from_row(row)

    def get_tool_calls_for_run(self, run_id: str) -> List[ToolCall]:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM agent_runs WHERE id = %s", (_uuid(run_id),)).fetchone() is None:
                raise NotFoundError(run_id)
            rows = conn.execute(
                "SELECT * FROM tool_calls WHERE run_id = %s ORDER BY started_at ASC, id ASC",
                (_uuid(run_id),),
            ).fetchall()
            return [self._tool_call_from_row(row) for row in rows]

    def create_approval(self, approval: Approval) -> Approval:
        with self._lock, self._connect() as conn:
            run = conn.execute("SELECT * FROM agent_runs WHERE id = %s", (_uuid(approval.run_id),)).fetchone()
            ticket = conn.execute("SELECT * FROM tickets WHERE id = %s", (_uuid(approval.ticket_id),)).fetchone()
            if run is None:
                raise NotFoundError(approval.run_id)
            if ticket is None:
                raise NotFoundError(approval.ticket_id)

            row = conn.execute(
                """
                INSERT INTO approvals (
                    id, run_id, ticket_id, status, action_type, proposed_reply, risk_level,
                    reason, decided_by, decision_note, created_at, decided_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(approval.id),
                    _uuid(approval.run_id),
                    _uuid(approval.ticket_id),
                    approval.status,
                    approval.action_type,
                    approval.proposed_reply,
                    approval.risk_level,
                    approval.reason,
                    approval.decided_by,
                    approval.decision_note,
                    approval.created_at,
                    approval.decided_at,
                ),
            ).fetchone()
            conn.execute(
                "UPDATE agent_runs SET approval_id = %s, updated_at = %s WHERE id = %s",
                (_uuid(approval.id), utc_now(), _uuid(approval.run_id)),
            )
            return self._approval_from_row(row)

    def get_approval(self, approval_id: str) -> Approval:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = %s", (_uuid(approval_id),)).fetchone()
            if row is None:
                raise NotFoundError(approval_id)
            return self._approval_from_row(row)

    def list_approvals(self, status: Optional[str] = None) -> List[Approval]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = %s ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
            return [self._approval_from_row(row) for row in rows]

    def update_approval(self, approval: Approval) -> Approval:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                UPDATE approvals
                SET run_id = %s,
                    ticket_id = %s,
                    status = %s,
                    action_type = %s,
                    proposed_reply = %s,
                    risk_level = %s,
                    reason = %s,
                    decided_by = %s,
                    decision_note = %s,
                    decided_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    _uuid(approval.run_id),
                    _uuid(approval.ticket_id),
                    approval.status,
                    approval.action_type,
                    approval.proposed_reply,
                    approval.risk_level,
                    approval.reason,
                    approval.decided_by,
                    approval.decision_note,
                    approval.decided_at,
                    _uuid(approval.id),
                ),
            ).fetchone()
            if row is None:
                raise NotFoundError(approval.id)
            return self._approval_from_row(row)

    def _retrieval_filter_where(self, filters: Optional[RetrievalFilters]) -> tuple[List[str], List[Any]]:
        if filters is None:
            return [], []

        clauses: List[str] = []
        params: List[Any] = []
        if filters.product_line:
            clauses.append("(product_line IS NULL OR product_line = %s)")
            params.append(filters.product_line)
        if filters.version:
            clauses.append("(version IS NULL OR version = %s)")
            params.append(filters.version)

        permissions = [item.lower() for item in filters.permissions]
        clauses.append("(COALESCE(cardinality(required_permissions), 0) = 0 OR required_permissions <@ %s::text[])")
        params.append(permissions)
        return clauses, params

    def _ticket_from_row(self, conn: Any, row: Dict[str, Any]) -> Ticket:
        run_rows = conn.execute(
            "SELECT id FROM agent_runs WHERE ticket_id = %s ORDER BY created_at ASC",
            (row["id"],),
        ).fetchall()
        return Ticket(
            id=_str_id(row["id"]),
            tenant_id=row["tenant_id"],
            customer_name=row["customer_name"],
            channel=row["channel"],
            subject=row["subject"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            issue_type=row["issue_type"],
            final_reply=row["final_reply"],
            run_ids=[_str_id(run_row["id"]) for run_row in run_rows],
            created_at=_iso(row["created_at"]) or utc_now(),
            updated_at=_iso(row["updated_at"]) or utc_now(),
        )

    def _document_from_row(self, row: Dict[str, Any]) -> Document:
        return Document(
            id=_str_id(row["id"]),
            tenant_id=row["tenant_id"],
            title=row["title"],
            source_type=row["source_type"],
            uri=row["uri"],
            content=row["content"],
            product_line=row.get("product_line"),
            version=row.get("version"),
            required_permissions=list(row.get("required_permissions") or []),
            valid_from=_iso(row.get("valid_from")),
            valid_until=_iso(row.get("valid_until")),
            source_system=row.get("source_system"),
            status=row.get("status") or "active",
            created_at=_iso(row["created_at"]) or utc_now(),
            updated_at=_iso(row.get("updated_at")) or _iso(row["created_at"]) or utc_now(),
        )

    def _chunk_from_row(self, row: Dict[str, Any]) -> DocumentChunk:
        return DocumentChunk(
            id=_str_id(row["id"]),
            document_id=_str_id(row["document_id"]),
            tenant_id=row["tenant_id"],
            title=row["title"],
            source_type=row["source_type"],
            uri=row["uri"],
            content=row["content"],
            chunk_index=row["chunk_index"],
            product_line=row.get("product_line"),
            version=row.get("version"),
            required_permissions=list(row.get("required_permissions") or []),
            valid_from=_iso(row.get("valid_from")),
            valid_until=_iso(row.get("valid_until")),
            source_system=row.get("source_system"),
            embedding=_float_list(row.get("embedding")),
        )

    def _run_from_row(self, conn: Any, row: Dict[str, Any]) -> AgentRun:
        step_ids = conn.execute(
            "SELECT id FROM agent_steps WHERE run_id = %s ORDER BY started_at ASC, id ASC",
            (row["id"],),
        ).fetchall()
        tool_call_ids = conn.execute(
            "SELECT id FROM tool_calls WHERE run_id = %s ORDER BY started_at ASC, id ASC",
            (row["id"],),
        ).fetchall()
        evidence_payload = row.get("evidence") or []
        return AgentRun(
            id=_str_id(row["id"]),
            ticket_id=_str_id(row["ticket_id"]),
            tenant_id=row["tenant_id"],
            trace_id=row.get("trace_id") or _str_id(row["id"]).replace("-", ""),
            correlation_id=row.get("correlation_id") or _str_id(row["id"]),
            status=row["status"],
            current_node=row["current_node"],
            triage=row["triage"] or {},
            evidence=[self._evidence_from_json(item) for item in evidence_payload],
            tool_call_ids=[_str_id(call_row["id"]) for call_row in tool_call_ids],
            step_ids=[_str_id(step_row["id"]) for step_row in step_ids],
            approval_id=_str_id(row["approval_id"]) if row["approval_id"] else None,
            final_reply=row["final_reply"],
            verifier_report=row["verifier_report"] or {},
            created_at=_iso(row["created_at"]) or utc_now(),
            updated_at=_iso(row["updated_at"]) or utc_now(),
        )

    def _step_from_row(self, row: Dict[str, Any]) -> AgentStep:
        return AgentStep(
            id=_str_id(row["id"]),
            run_id=_str_id(row["run_id"]),
            name=row["name"],
            status=row["status"],
            summary=row["summary"],
            latency_ms=row["latency_ms"],
            token_count=row["token_count"],
            evidence_ids=_str_id_list(row["evidence_ids"]),
            tool_call_ids=_str_id_list(row["tool_call_ids"]),
            started_at=_iso(row["started_at"]) or utc_now(),
            ended_at=_iso(row["ended_at"]) or utc_now(),
        )

    def _tool_call_from_row(self, row: Dict[str, Any]) -> ToolCall:
        return ToolCall(
            id=_str_id(row["id"]),
            run_id=_str_id(row["run_id"]),
            tool_name=row["tool_name"],
            status=row["status"],
            input_summary=row["input_summary"],
            output_summary=row["output_summary"],
            started_at=_iso(row["started_at"]) or utc_now(),
            ended_at=_iso(row["ended_at"]) or utc_now(),
        )

    def _approval_from_row(self, row: Dict[str, Any]) -> Approval:
        return Approval(
            id=_str_id(row["id"]),
            run_id=_str_id(row["run_id"]),
            ticket_id=_str_id(row["ticket_id"]),
            status=row["status"],
            action_type=row["action_type"],
            proposed_reply=row["proposed_reply"],
            risk_level=row["risk_level"],
            reason=row["reason"],
            decided_by=row["decided_by"],
            decision_note=row["decision_note"],
            created_at=_iso(row["created_at"]) or utc_now(),
            decided_at=_iso(row["decided_at"]),
        )

    def _audit_from_row(self, row: Dict[str, Any]) -> AuditLog:
        return AuditLog(
            id=_str_id(row["id"]),
            tenant_id=row["tenant_id"],
            actor=row["actor"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            metadata=row["metadata"] or {},
            created_at=_iso(row["created_at"]) or utc_now(),
        )

    def _evidence_from_chunk(
        self,
        chunk: DocumentChunk,
        score: float,
        *,
        keyword_score: float = 0.0,
        vector_score: float = 0.0,
        retrieval_mode: str = "unknown",
    ) -> Evidence:
        excerpt = " ".join(chunk.content.split())[:320]
        return Evidence(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            title=chunk.title,
            uri=chunk.uri,
            excerpt=excerpt,
            score=round(score, 3),
            source_type=chunk.source_type,
            product_line=chunk.product_line,
            version=chunk.version,
            required_permissions=list(chunk.required_permissions),
            valid_from=chunk.valid_from,
            valid_until=chunk.valid_until,
            source_system=chunk.source_system,
            keyword_score=round(keyword_score, 3),
            vector_score=round(vector_score, 3),
            retrieval_mode=retrieval_mode,
        )

    def _evidence_to_json(self, evidence: Any) -> Dict[str, Any]:
        return {
            "chunk_id": evidence.chunk_id,
            "document_id": evidence.document_id,
            "title": evidence.title,
            "uri": evidence.uri,
            "excerpt": evidence.excerpt,
            "score": evidence.score,
            "source_type": evidence.source_type,
            "product_line": evidence.product_line,
            "version": evidence.version,
            "required_permissions": evidence.required_permissions,
            "valid_from": evidence.valid_from,
            "valid_until": evidence.valid_until,
            "source_system": evidence.source_system,
            "keyword_score": evidence.keyword_score,
            "vector_score": evidence.vector_score,
            "retrieval_mode": evidence.retrieval_mode,
        }

    def _evidence_from_json(self, payload: Dict[str, Any]) -> Any:
        from .models import Evidence

        return Evidence(
            chunk_id=payload["chunk_id"],
            document_id=payload["document_id"],
            title=payload["title"],
            uri=payload["uri"],
            excerpt=payload["excerpt"],
            score=payload["score"],
            source_type=payload.get("source_type"),
            product_line=payload.get("product_line"),
            version=payload.get("version"),
            required_permissions=list(payload.get("required_permissions") or []),
            valid_from=payload.get("valid_from"),
            valid_until=payload.get("valid_until"),
            source_system=payload.get("source_system"),
            keyword_score=payload.get("keyword_score", 0.0),
            vector_score=payload.get("vector_score", 0.0),
            retrieval_mode=payload.get("retrieval_mode", "unknown"),
        )


def create_store(seed: bool = True) -> Store:
    backend = os.getenv("SUPPORT_COPILOT_STORE", "postgres").lower()
    embedding_model = create_embedding_model_from_env()
    if backend in {"memory", "in_memory", "inmemory"}:
        return InMemoryStore(seed=seed, embedding_model=embedding_model)

    database_url = os.getenv("SUPPORT_COPILOT_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    return PostgresStore(database_url=database_url, seed=seed, embedding_model=embedding_model)
