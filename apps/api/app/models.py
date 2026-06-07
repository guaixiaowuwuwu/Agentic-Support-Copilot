from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .time_utils import utc_now


def new_id() -> str:
    return str(uuid4())


@dataclass
class Ticket:
    tenant_id: str
    customer_name: str
    channel: str
    subject: str
    description: str
    id: str = field(default_factory=new_id)
    status: str = "open"
    priority: Optional[str] = None
    issue_type: Optional[str] = None
    final_reply: Optional[str] = None
    run_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class Document:
    tenant_id: str
    title: str
    source_type: str
    uri: str
    content: str
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)


@dataclass
class DocumentChunk:
    document_id: str
    tenant_id: str
    title: str
    source_type: str
    uri: str
    content: str
    chunk_index: int
    embedding: Optional[List[float]] = None
    id: str = field(default_factory=new_id)


@dataclass
class Evidence:
    chunk_id: str
    document_id: str
    title: str
    uri: str
    excerpt: str
    score: float


@dataclass
class ToolCall:
    run_id: str
    tool_name: str
    status: str
    input_summary: str
    output_summary: str
    id: str = field(default_factory=new_id)
    started_at: str = field(default_factory=utc_now)
    ended_at: str = field(default_factory=utc_now)


@dataclass
class AgentStep:
    run_id: str
    name: str
    status: str
    summary: str
    latency_ms: int
    token_count: int = 0
    evidence_ids: List[str] = field(default_factory=list)
    tool_call_ids: List[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    started_at: str = field(default_factory=utc_now)
    ended_at: str = field(default_factory=utc_now)


@dataclass
class Approval:
    run_id: str
    ticket_id: str
    action_type: str
    proposed_reply: str
    risk_level: str
    reason: str
    id: str = field(default_factory=new_id)
    status: str = "pending"
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    created_at: str = field(default_factory=utc_now)
    decided_at: Optional[str] = None


@dataclass
class AgentRun:
    ticket_id: str
    tenant_id: str
    id: str = field(default_factory=new_id)
    status: str = "queued"
    current_node: str = "created"
    triage: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)
    tool_call_ids: List[str] = field(default_factory=list)
    step_ids: List[str] = field(default_factory=list)
    approval_id: Optional[str] = None
    final_reply: Optional[str] = None
    verifier_report: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class AuditLog:
    tenant_id: str
    actor: str
    action: str
    target_type: str
    target_id: str
    metadata: Dict[str, Any]
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value
