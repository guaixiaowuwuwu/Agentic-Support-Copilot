from __future__ import annotations

import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.agents import SupportAgentWorkflow
from app.knowledge import KeywordRetriever
from app.models import Document, Ticket
from app.store import InMemoryStore
from app.tools import ToolPermissionError, ToolRegistry


class SupportWorkflowTest(unittest.TestCase):
    def test_api_401_ticket_reaches_approval_and_reply(self) -> None:
        store = InMemoryStore(seed=True)
        workflow = SupportAgentWorkflow(store)
        ticket = store.create_ticket(
            Ticket(
                tenant_id="acme",
                customer_name="Alice",
                channel="email",
                subject="API 报 401",
                description="客户说 API 报 401，帮我排查并回复。request_id=req_123",
            )
        )

        run = workflow.start_run(ticket.id)

        self.assertEqual(run.status, "awaiting_approval")
        self.assertEqual(run.triage["issue_type"], "api_auth")
        self.assertEqual(run.triage["priority"], "P2")
        self.assertTrue(run.evidence)
        self.assertTrue(run.verifier_report["passed"])
        self.assertIsNotNone(run.approval_id)

        step_names = [step.name for step in store.get_steps_for_run(run.id)]
        self.assertEqual(
            step_names,
            ["triage", "retrieval", "tool_call_optional", "verifier", "human_approval"],
        )

        tool_calls = store.get_tool_calls_for_run(run.id)
        self.assertEqual([call.tool_name for call in tool_calls], ["log_search", "db_read"])
        self.assertTrue(all(call.status == "success" for call in tool_calls))

        approval = store.get_approval(run.approval_id or "")
        self.assertEqual(approval.status, "pending")
        self.assertIn("引用来源", approval.proposed_reply)

        completed = workflow.approve(approval.id, decided_by="lead@example.com", note="Looks good")
        updated_ticket = store.get_ticket(ticket.id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(updated_ticket.status, "replied")
        self.assertIn("API 401", updated_ticket.final_reply or "")

    def test_missing_evidence_is_routed_to_manual_review(self) -> None:
        store = InMemoryStore(seed=False)
        workflow = SupportAgentWorkflow(store)
        ticket = store.create_ticket(
            Ticket(
                tenant_id="acme",
                customer_name="Bob",
                channel="portal",
                subject="Unknown integration behavior",
                description="A customer asks about an undocumented integration path.",
            )
        )

        run = workflow.start_run(ticket.id)
        approval = store.get_approval(run.approval_id or "")

        self.assertEqual(run.status, "awaiting_approval")
        self.assertFalse(run.verifier_report["passed"])
        self.assertEqual(approval.action_type, "manual_review")
        self.assertIn("missing_citations", run.verifier_report["findings"])

    def test_retrieval_is_tenant_scoped(self) -> None:
        store = InMemoryStore(seed=True)
        store.add_document(
            Document(
                tenant_id="globex",
                title="Globex Secret API 401 Runbook",
                source_type="policy",
                uri="kb://globex/secret-401",
                content="Globex private 401 remediation procedure.",
            )
        )

        evidence = KeywordRetriever().search("acme", "Globex Secret API 401 Runbook", store.list_chunks())

        self.assertTrue(all("globex" not in item.uri for item in evidence))

    def test_tool_whitelist_denies_unapproved_tools(self) -> None:
        registry = ToolRegistry(allowed_tools=["log_search"])
        store = InMemoryStore(seed=True)
        workflow = SupportAgentWorkflow(store, tools=registry)
        ticket = store.create_ticket(
            Ticket(
                tenant_id="acme",
                customer_name="Casey",
                channel="email",
                subject="API 401 in production",
                description="Customer sees 401 responses from the API.",
            )
        )

        with self.assertRaises(ToolPermissionError):
            registry.execute("run-id", "db_read", ticket)

        run = workflow.start_run(ticket.id)
        calls = store.get_tool_calls_for_run(run.id)

        self.assertEqual(calls[0].status, "success")
        self.assertEqual(calls[1].status, "denied")
        self.assertEqual(calls[1].tool_name, "db_read")


if __name__ == "__main__":
    unittest.main()

