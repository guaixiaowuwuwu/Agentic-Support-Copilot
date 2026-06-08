from __future__ import annotations

from typing import List, Optional

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
    product_line: Optional[str] = None
    version: Optional[str] = None
    required_permissions: List[str] = Field(default_factory=list)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    source_system: Optional[str] = None


class IngestEmbeddingsRequest(BaseModel):
    tenant_id: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    decided_by: str = Field(default="support.lead")
    note: Optional[str] = ""
