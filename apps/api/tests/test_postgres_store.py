from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

try:
    import psycopg
except ImportError:  # pragma: no cover - optional integration dependency.
    psycopg = None  # type: ignore[assignment]

from app.agents import SupportAgentWorkflow
from app.models import Document, Ticket
from app.store import PostgresStore


DATABASE_URL = os.getenv("SUPPORT_COPILOT_TEST_DATABASE_URL")


@unittest.skipUnless(
    DATABASE_URL and psycopg is not None,
    "set SUPPORT_COPILOT_TEST_DATABASE_URL to run PostgreSQL persistence tests",
)
class PostgresStorePersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(database_url=DATABASE_URL or "", seed=False)
        self._reset_database()

    def _reset_database(self) -> None:
        assert psycopg is not None
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                TRUNCATE TABLE
                  audit_logs,
                  approvals,
                  tool_calls,
                  agent_steps,
                  agent_runs,
                  document_chunks,
                  documents,
                  tickets
                CASCADE
                """
            )

    def test_workflow_entities_survive_new_store_instance(self) -> None:
        self.store.add_document(
            Document(
                tenant_id="acme",
                title="API Authentication Runbook",
                source_type="api_doc",
                uri="kb://api/authentication-runbook",
                content=(
                    "401 Unauthorized responses usually mean the Authorization header is missing, "
                    "the Bearer token expired, the API key is invalid, or OAuth scope is insufficient."
                ),
            )
        )
        ticket = self.store.create_ticket(
            Ticket(
                tenant_id="acme",
                customer_name="Alice",
                channel="email",
                subject="API 报 401",
                description="客户说 API 报 401，帮我排查并回复。request_id=req_123",
            )
        )

        run = SupportAgentWorkflow(self.store).start_run(ticket.id)

        reloaded = PostgresStore(database_url=DATABASE_URL or "", seed=False, ensure_schema=False)
        persisted_run = reloaded.get_run(run.id)
        persisted_ticket = reloaded.get_ticket(ticket.id)
        approval = reloaded.get_approval(run.approval_id or "")

        self.assertEqual(persisted_run.status, "awaiting_approval")
        self.assertEqual(persisted_ticket.status, "awaiting_approval")
        self.assertEqual(persisted_ticket.run_ids, [run.id])
        self.assertTrue(persisted_run.evidence)
        self.assertEqual(len(reloaded.list_documents("acme")), 1)
        self.assertTrue(reloaded.list_chunks())
        self.assertEqual(
            [step.name for step in reloaded.get_steps_for_run(run.id)],
            ["triage", "retrieval", "tool_call_optional", "verifier", "human_approval"],
        )
        self.assertEqual(
            [call.tool_name for call in reloaded.get_tool_calls_for_run(run.id)],
            ["log_search", "db_read"],
        )
        self.assertEqual(approval.status, "pending")
        self.assertEqual(len(reloaded.list_audit_logs("acme")), 1)

        completed = SupportAgentWorkflow(reloaded).approve(approval.id, decided_by="lead@example.com")
        finished_ticket = reloaded.get_ticket(ticket.id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(finished_ticket.status, "replied")
        self.assertEqual(len(reloaded.list_audit_logs("acme")), 2)


if __name__ == "__main__":
    unittest.main()
