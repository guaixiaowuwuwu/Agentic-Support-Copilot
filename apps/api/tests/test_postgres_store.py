from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

try:
    import psycopg
except ImportError:  # pragma: no cover - optional integration dependency.
    psycopg = None  # type: ignore[assignment]

try:
    import pgvector
except ImportError:  # pragma: no cover - optional integration dependency.
    pgvector = None  # type: ignore[assignment]

from app.agents import SupportAgentWorkflow
from app.knowledge import EMBEDDING_DIMENSIONS, PgVectorRetriever
from app.models import Document, Ticket
from app.store import PostgresStore


DATABASE_URL = os.getenv("SUPPORT_COPILOT_TEST_DATABASE_URL")
DEFAULT_SAFE_TEST_DATABASE_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _allowed_test_database_hosts() -> set[str]:
    configured = os.getenv("SUPPORT_COPILOT_TEST_DATABASE_ALLOW_HOSTS")
    if not configured:
        return DEFAULT_SAFE_TEST_DATABASE_HOSTS
    return {host.strip().lower() for host in configured.split(",") if host.strip()}


def validate_safe_test_database_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    hostname = (parsed.hostname or "").lower()
    database_name = parsed.path.lstrip("/")
    allowed_hosts = _allowed_test_database_hosts()

    if parsed.scheme not in {"postgres", "postgresql"} or not hostname or not database_name:
        raise RuntimeError(
            "SUPPORT_COPILOT_TEST_DATABASE_URL must be a full PostgreSQL URL for a disposable test database."
        )
    if hostname not in allowed_hosts:
        hosts = ", ".join(sorted(allowed_hosts))
        raise RuntimeError(
            "Refusing to run destructive PostgreSQL integration tests against "
            f"host {hostname!r}. These tests truncate tables before each case. "
            f"Allowed hosts: {hosts}. Set SUPPORT_COPILOT_TEST_DATABASE_ALLOW_HOSTS "
            "only when the target is a disposable test database."
        )


class PostgresTestDatabaseSafetyTest(unittest.TestCase):
    def test_local_postgres_test_database_url_is_allowed(self) -> None:
        validate_safe_test_database_url("postgresql://support:support@127.0.0.1:5432/support_copilot")

    def test_remote_postgres_test_database_url_is_rejected_by_default(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_safe_test_database_url("postgresql://support:support@prod-db.example.com/support_copilot")


@unittest.skipUnless(
    DATABASE_URL and psycopg is not None and pgvector is not None,
    "set SUPPORT_COPILOT_TEST_DATABASE_URL and install psycopg/pgvector to run PostgreSQL persistence tests",
)
class PostgresStorePersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        validate_safe_test_database_url(DATABASE_URL or "")

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
        self.assertEqual(len(reloaded.list_audit_logs("acme")), 3)

        completed = SupportAgentWorkflow(reloaded).approve(approval.id, decided_by="lead@example.com")
        finished_ticket = reloaded.get_ticket(ticket.id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(finished_ticket.status, "replied")
        self.assertEqual(len(reloaded.list_audit_logs("acme")), 4)

    def test_document_ingestion_writes_vectors_and_pgvector_search_is_tenant_scoped(self) -> None:
        self.store.add_document(
            Document(
                tenant_id="acme",
                title="Acme API 401 Runbook",
                source_type="api_doc",
                uri="kb://acme/api-401",
                content="API 401 errors require checking Bearer token syntax, expiry, and OAuth scopes.",
            )
        )
        self.store.add_document(
            Document(
                tenant_id="globex",
                title="Globex Secret API 401 Runbook",
                source_type="api_doc",
                uri="kb://globex/secret-401",
                content="Globex private 401 remediation procedure. This must stay tenant-scoped.",
            )
        )

        acme_chunks = [chunk for chunk in self.store.list_chunks() if chunk.tenant_id == "acme"]
        self.assertTrue(acme_chunks)
        self.assertTrue(all(chunk.embedding for chunk in acme_chunks))
        self.assertTrue(all(len(chunk.embedding or []) == EMBEDDING_DIMENSIONS for chunk in acme_chunks))

        evidence = PgVectorRetriever(self.store).search("acme", "Globex Secret API 401 Runbook")

        self.assertTrue(evidence)
        self.assertTrue(all("globex" not in item.uri for item in evidence))

    def test_missing_embeddings_can_be_backfilled(self) -> None:
        self.store.add_document(
            Document(
                tenant_id="acme",
                title="Token Rotation Guide",
                source_type="api_doc",
                uri="kb://acme/token-rotation",
                content="Rotate expired Bearer tokens and validate scopes before retrying API requests.",
            )
        )

        assert psycopg is not None
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("UPDATE document_chunks SET embedding = NULL WHERE tenant_id = %s", ("acme",))

        updated = self.store.ingest_missing_embeddings(tenant_id="acme")

        self.assertGreater(updated, 0)
        self.assertTrue(all(chunk.embedding for chunk in self.store.list_chunks() if chunk.tenant_id == "acme"))


if __name__ == "__main__":
    unittest.main()
