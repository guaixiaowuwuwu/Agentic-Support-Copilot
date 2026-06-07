from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ["SUPPORT_COPILOT_STORE"] = "memory"

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from fastapi.testclient import TestClient

from app import main as api_main
from app.agents import SupportAgentWorkflow
from app.models import Ticket
from app.store import InMemoryStore


def auth_headers(
    *,
    email: str = "lead@acme.test",
    tenant_id: str = "acme",
    roles: str = "support_agent,approver",
    tenant_ids: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-User-Email": email,
        "X-Tenant-Id": tenant_id,
        "X-User-Roles": roles,
    }
    if tenant_ids:
        headers["X-Tenant-Ids"] = tenant_ids
    return headers


class ApiAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore(seed=True)
        api_main.store = self.store
        api_main.workflow = SupportAgentWorkflow(self.store)
        self.client = TestClient(api_main.app)

    def create_ticket(self, tenant_id: str, subject: str = "API 401") -> Ticket:
        return self.store.create_ticket(
            Ticket(
                tenant_id=tenant_id,
                customer_name=f"{tenant_id.title()} Customer",
                channel="email",
                subject=subject,
                description="Customer reports API 401 errors. request_id=req_123",
            )
        )

    def test_business_api_requires_authenticated_user_context(self) -> None:
        self.assertEqual(self.client.get("/api/health").status_code, 200)

        response = self.client.get("/api/tickets")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Authentication headers are required")

    def test_ticket_routes_are_scoped_to_request_tenant(self) -> None:
        acme_ticket = self.create_ticket("acme", "Acme API 401")
        globex_ticket = self.create_ticket("globex", "Globex API 401")

        list_response = self.client.get("/api/tickets", headers=auth_headers())
        listed_ids = {ticket["id"] for ticket in list_response.json()}

        self.assertEqual(list_response.status_code, 200)
        self.assertIn(acme_ticket.id, listed_ids)
        self.assertNotIn(globex_ticket.id, listed_ids)

        cross_tenant_detail = self.client.get(f"/api/tickets/{globex_ticket.id}", headers=auth_headers())
        self.assertEqual(cross_tenant_detail.status_code, 404)

        disallowed_tenant_query = self.client.get(
            "/api/tickets?tenant_id=globex",
            headers=auth_headers(tenant_ids="acme"),
        )
        self.assertEqual(disallowed_tenant_query.status_code, 403)

    def test_create_ticket_cannot_spoof_payload_tenant(self) -> None:
        response = self.client.post(
            "/api/tickets",
            headers=auth_headers(tenant_id="acme", tenant_ids="acme"),
            json={
                "tenant_id": "globex",
                "customer_name": "Globex Customer",
                "channel": "email",
                "subject": "API 401",
                "description": "Customer reports API 401 errors.",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_run_trace_is_scoped_to_run_tenant(self) -> None:
        globex_ticket = self.create_ticket("globex")
        globex_run = api_main.workflow.start_run(globex_ticket.id)

        response = self.client.get(f"/api/runs/{globex_run.id}/trace", headers=auth_headers())

        self.assertEqual(response.status_code, 404)

    def test_approval_queue_and_decisions_are_tenant_scoped_and_role_checked(self) -> None:
        acme_run = api_main.workflow.start_run(self.create_ticket("acme").id)
        globex_run = api_main.workflow.start_run(self.create_ticket("globex").id)

        queue_response = self.client.get("/api/approvals?status=pending", headers=auth_headers())
        approval_ids = {approval["id"] for approval in queue_response.json()}

        self.assertEqual(queue_response.status_code, 200)
        self.assertIn(acme_run.approval_id, approval_ids)
        self.assertNotIn(globex_run.approval_id, approval_ids)

        support_agent_response = self.client.post(
            f"/api/approvals/{acme_run.approval_id}/approve",
            headers=auth_headers(roles="support_agent"),
            json={"decided_by": "spoof@example.test", "note": "Looks good"},
        )
        self.assertEqual(support_agent_response.status_code, 403)

        cross_tenant_response = self.client.post(
            f"/api/approvals/{globex_run.approval_id}/approve",
            headers=auth_headers(),
            json={"decided_by": "spoof@example.test", "note": "Looks good"},
        )
        self.assertEqual(cross_tenant_response.status_code, 404)

        approve_response = self.client.post(
            f"/api/approvals/{acme_run.approval_id}/approve",
            headers=auth_headers(email="lead@acme.test"),
            json={"decided_by": "spoof@example.test", "note": "Looks good"},
        )

        self.assertEqual(approve_response.status_code, 200)
        approval = self.store.get_approval(acme_run.approval_id or "")
        self.assertEqual(approval.status, "approved")
        self.assertEqual(approval.decided_by, "lead@acme.test")

    def test_knowledge_writes_require_admin_role_and_tenant_scope(self) -> None:
        support_agent_response = self.client.post(
            "/api/knowledge/documents",
            headers=auth_headers(roles="support_agent"),
            json={
                "tenant_id": "acme",
                "title": "Internal Auth Runbook",
                "uri": "kb://acme/internal-auth",
                "content": "Internal authentication troubleshooting.",
            },
        )
        self.assertEqual(support_agent_response.status_code, 403)

        admin_response = self.client.post(
            "/api/knowledge/documents",
            headers=auth_headers(roles="knowledge_admin", tenant_ids="acme"),
            json={
                "tenant_id": "acme",
                "title": "Internal Auth Runbook",
                "uri": "kb://acme/internal-auth",
                "content": "Internal authentication troubleshooting.",
            },
        )

        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.json()["tenant_id"], "acme")

        spoof_response = self.client.post(
            "/api/knowledge/documents",
            headers=auth_headers(roles="knowledge_admin", tenant_ids="acme"),
            json={
                "tenant_id": "globex",
                "title": "Globex Internal Runbook",
                "uri": "kb://globex/internal-auth",
                "content": "Globex private content.",
            },
        )
        self.assertEqual(spoof_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
