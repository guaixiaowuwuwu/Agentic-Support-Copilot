from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateTicketRequest(BaseModel):
    tenant_id: str = Field(default="acme")
    customer_name: str = Field(default="Acme Customer")
    channel: str = Field(default="email")
    subject: str
    description: str


class CreateDocumentRequest(BaseModel):
    tenant_id: str = Field(default="acme")
    title: str
    source_type: str = Field(default="knowledge_base")
    uri: str
    content: str


class IngestEmbeddingsRequest(BaseModel):
    tenant_id: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    decided_by: str = Field(default="support.lead")
    note: Optional[str] = ""
