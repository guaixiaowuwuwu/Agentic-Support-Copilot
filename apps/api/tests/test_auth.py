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
from app.models import AuditLog, Ticket
from app.store import InMemoryStore


AUTH_ENV_KEYS = ("APP_ENV", "SUPPORT_COPILOT_AUTH_MODE", "SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET")


def auth_headers(
    *,
    email: str = "lead@acme.test",
    tenant_id: str = "acme",
    roles: str = "support_agent,approver",
    tenant_ids: str | None = None,
    trusted_secret: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-User-Email": email,
        "X-Tenant-Id": tenant_id,
        "X-User-Roles": roles,
    }
    if tenant_ids:
        headers["X-Tenant-Ids"] = tenant_ids
    if trusted_secret:
        headers["X-Support-Copilot-Trusted-Identity"] = trusted_secret
    return headers


class ApiAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {key: os.environ.get(key) for key in AUTH_ENV_KEYS}
        os.environ["APP_ENV"] = "development"
        os.environ.pop("SUPPORT_COPILOT_AUTH_MODE", None)
        os.environ.pop("SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET", None)
        self.addCleanup(self._restore_auth_env)
        self.store = InMemoryStore(seed=True)
        api_main.store = self.store
        api_main.workflow = SupportAgentWorkflow(self.store)
        self.client = TestClient(api_main.app)

    def _restore_auth_env(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

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

    def test_production_like_environment_requires_trusted_identity_context(self) -> None:
        os.environ["APP_ENV"] = "production"

        untrusted_response = self.client.get("/api/auth/me", headers=auth_headers())

        self.assertEqual(untrusted_response.status_code, 401)
        self.assertEqual(untrusted_response.json()["detail"], "Trusted identity context is not configured")

        os.environ["SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET"] = "gateway-secret"
        trusted_response = self.client.get(
            "/api/auth/me",
            headers=auth_headers(roles="support_agent", tenant_ids="acme", trusted_secret="gateway-secret"),
        )

        self.assertEqual(trusted_response.status_code, 200)
        self.assertEqual(trusted_response.json()["auth_source"], "trusted_headers")

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

    def test_approver_cannot_create_tickets_or_start_runs(self) -> None:
        ticket = self.create_ticket("acme")
        headers = auth_headers(roles="approver", tenant_ids="acme")

        create_response = self.client.post(
            "/api/tickets",
            headers=headers,
            json={
                "tenant_id": "acme",
                "customer_name": "Acme Customer",
                "channel": "email",
                "subject": "API 401",
                "description": "Customer reports API 401 errors.",
            },
        )
        start_response = self.client.post(f"/api/runs/{ticket.id}/start", headers=headers)

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(start_response.status_code, 403)

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
        list_response = self.client.get(
            "/api/knowledge/documents",
            headers=auth_headers(roles="support_agent", tenant_ids="acme"),
        )
        self.assertEqual(list_response.status_code, 403)

        support_agent_response = self.client.post(
            "/api/knowledge/documents",
            headers=auth_headers(roles="support_agent"),
            json={
                "tenant_id": "acme",
                "title": "SAML Connector Drift Runbook",
                "uri": "kb://acme/internal-auth",
                "content": "SAML connector drift requires checking entity ID and certificate thumbprint.",
            },
        )
        self.assertEqual(support_agent_response.status_code, 403)

        support_agent_ingest_response = self.client.post(
            "/api/knowledge/embeddings/ingest",
            headers=auth_headers(roles="support_agent"),
            json={"tenant_id": "acme"},
        )
        self.assertEqual(support_agent_ingest_response.status_code, 403)

        admin_response = self.client.post(
            "/api/knowledge/documents",
            headers=auth_headers(roles="knowledge_admin", tenant_ids="acme"),
            json={
                "tenant_id": "acme",
                "title": "SAML Connector Drift Runbook",
                "source_type": "runbook",
                "uri": "kb://acme/saml-connector-drift",
                "content": (
                    "SAML connector drift requires checking entity ID, assertion consumer service URL, "
                    "and certificate thumbprint before asking the customer to retry login."
                ),
            },
        )

        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.json()["tenant_id"], "acme")
        self.assertEqual(admin_response.json()["embedding_status"], "pending")
        self.assertGreater(admin_response.json()["chunk_count"], 0)

        knowledge_list_response = self.client.get(
            "/api/knowledge/documents",
            headers=auth_headers(roles="knowledge_admin", tenant_ids="acme"),
        )
        self.assertEqual(knowledge_list_response.status_code, 200)
        imported_document = next(
            document for document in knowledge_list_response.json() if document["id"] == admin_response.json()["id"]
        )
        self.assertEqual(imported_document["embedded_chunk_count"], 0)
        self.assertEqual(imported_document["source_type"], "runbook")

        detail_response = self.client.get(
            f"/api/knowledge/documents/{admin_response.json()['id']}",
            headers=auth_headers(roles="knowledge_admin", tenant_ids="acme"),
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["chunks"][0]["embedding_status"], "pending")

        ingest_response = self.client.post(
            "/api/knowledge/embeddings/ingest",
            headers=auth_headers(roles="knowledge_admin", tenant_ids="acme"),
            json={"tenant_id": "acme"},
        )
        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(ingest_response.json()["embedding_status"], "embedded")
        self.assertGreaterEqual(ingest_response.json()["updated_chunks"], imported_document["chunk_count"])

        ticket = self.create_ticket("acme", subject="SAML connector drift")
        ticket.description = "Customer login fails after SAML connector drift. Please check entity ID and thumbprint."
        self.store.update_ticket(ticket)
        run = api_main.workflow.start_run(ticket.id)
        self.assertTrue(any(evidence.title == "SAML Connector Drift Runbook" for evidence in run.evidence))

        audit_actions = [audit.action for audit in self.store.list_audit_logs("acme")]
        self.assertIn("document_created", audit_actions)
        self.assertIn("embeddings_ingested", audit_actions)

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

    def test_admin_can_access_audit_logs_and_system_config(self) -> None:
        self.store.add_audit(
            AuditLog(
                tenant_id="acme",
                actor="system",
                action="test_audit",
                target_type="ticket",
                target_id="ticket-test",
                metadata={},
            )
        )
        self.store.add_audit(
            AuditLog(
                tenant_id="acme",
                actor="tool-agent",
                action="tool_call_failed",
                target_type="tool_call",
                target_id="tool-failed",
                metadata={"run_id": "run-filter-me", "api_key": "clear-secret", "output_summary": "token=raw-token"},
                created_at="2026-06-08T01:00:00+00:00",
            )
        )
        self.store.add_audit(
            AuditLog(
                tenant_id="acme",
                actor="system",
                action="old_audit",
                target_type="ticket",
                target_id="old-ticket",
                metadata={},
                created_at="2020-01-01T00:00:00+00:00",
            )
        )

        support_agent_audit = self.client.get(
            "/api/audit-logs",
            headers=auth_headers(roles="support_agent", tenant_ids="acme"),
        )
        support_agent_config = self.client.get(
            "/api/admin/config",
            headers=auth_headers(roles="support_agent", tenant_ids="acme"),
        )
        admin_audit = self.client.get("/api/audit-logs", headers=auth_headers(roles="admin", tenant_ids="acme"))
        filtered_audit = self.client.get(
            "/api/audit-logs?action=tool_call_failed&actor=tool-agent&target=run-filter-me"
            "&start_time=2026-01-01T00:00:00%2B00:00&end_time=2026-12-31T23:59:59%2B00:00",
            headers=auth_headers(roles="admin", tenant_ids="acme"),
        )
        legacy_audit = self.client.get(
            "/api/audit/logs?action=test_audit",
            headers=auth_headers(roles="admin", tenant_ids="acme"),
        )
        admin_config = self.client.get("/api/admin/config", headers=auth_headers(roles="admin", tenant_ids="acme"))

        self.assertEqual(support_agent_audit.status_code, 403)
        self.assertEqual(support_agent_config.status_code, 403)
        self.assertEqual(admin_audit.status_code, 200)
        self.assertEqual(admin_audit.json()[0]["action"], "test_audit")
        self.assertEqual(filtered_audit.status_code, 200)
        self.assertEqual(len(filtered_audit.json()), 1)
        self.assertEqual(filtered_audit.json()[0]["action"], "tool_call_failed")
        self.assertEqual(filtered_audit.json()[0]["metadata"]["api_key"], "[REDACTED]")
        self.assertNotIn("raw-token", str(filtered_audit.json()[0]["metadata"]))
        self.assertEqual(legacy_audit.status_code, 200)
        self.assertEqual(legacy_audit.json()[0]["action"], "test_audit")
        self.assertEqual(admin_config.status_code, 200)
        self.assertEqual(admin_config.json()["auth"]["mode"], "local_headers")


if __name__ == "__main__":
    unittest.main()
