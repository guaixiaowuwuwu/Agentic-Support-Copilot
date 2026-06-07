from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Sequence

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.agents import SupportAgentWorkflow
from app.knowledge import EMBEDDING_DIMENSIONS, KeywordRetriever, VectorRetriever
from app.llm import LLMError
from app.models import Document, Evidence, Ticket
from app.store import InMemoryStore
from app.tools import LogSearchTool, ReadOnlyDatabaseTool, ToolPermissionError, ToolRegistry


class FakeChatClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: Sequence[Dict[str, str]] = []

    def complete(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> str:
        del temperature, max_tokens
        self.messages = messages
        return self.reply


class FailingChatClient:
    def complete(
        self,
        messages: Sequence[Dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
    ) -> str:
        del messages, temperature, max_tokens
        raise LLMError("simulated outage")


class FakeToolBackend:
    def __init__(self, output: str) -> None:
        self.output = output

    def execute(self, context) -> str:
        return self.output


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
        audit_actions = [audit.action for audit in store.list_audit_logs("acme")]
        self.assertEqual(audit_actions.count("tool_call_succeeded"), 2)

        approval = store.get_approval(run.approval_id or "")
        self.assertEqual(approval.status, "pending")
        self.assertIn("引用来源", approval.proposed_reply)

        completed = workflow.approve(approval.id, decided_by="lead@example.com", note="Looks good")
        updated_ticket = store.get_ticket(ticket.id)

        self.assertEqual(completed.status, "completed")
        self.assertEqual(updated_ticket.status, "replied")
        self.assertIn("API 401", updated_ticket.final_reply or "")

    def test_configured_llm_generates_approval_draft(self) -> None:
        store = InMemoryStore(seed=True)
        chat_client = FakeChatClient(
            "您好 Alice，模型生成的草稿会先建议检查 Bearer token、过期时间和 OAuth scope。"
            "请不要通过工单发送原始密钥。\n\n"
            "引用来源：\n[1] API Authentication Runbook - kb://api/authentication-runbook"
        )
        workflow = SupportAgentWorkflow(store, chat_client=chat_client)
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
        approval = store.get_approval(run.approval_id or "")

        self.assertTrue(run.verifier_report["passed"])
        self.assertIn("模型生成的草稿", approval.proposed_reply)
        self.assertEqual(chat_client.messages[0]["role"], "system")

    def test_llm_reply_is_normalized_for_required_guardrails(self) -> None:
        store = InMemoryStore(seed=True)
        workflow = SupportAgentWorkflow(store, chat_client=FakeChatClient("您好 Alice，模型草稿建议先检查认证配置。"))
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
        approval = store.get_approval(run.approval_id or "")

        self.assertTrue(run.verifier_report["passed"])
        self.assertIn("请不要通过工单发送原始密钥", approval.proposed_reply)
        self.assertIn("引用来源", approval.proposed_reply)

    def test_llm_failure_falls_back_to_template_reply(self) -> None:
        store = InMemoryStore(seed=True)
        workflow = SupportAgentWorkflow(store, chat_client=FailingChatClient())
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
        approval = store.get_approval(run.approval_id or "")

        self.assertTrue(run.verifier_report["passed"])
        self.assertIn("最可能的原因", approval.proposed_reply)

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

    def test_vector_ingestion_and_retrieval_are_tenant_scoped(self) -> None:
        store = InMemoryStore(seed=False)
        store.add_document(
            Document(
                tenant_id="acme",
                title="Acme API 401 Runbook",
                source_type="api_doc",
                uri="kb://acme/api-401",
                content="API 401 errors require checking Bearer token syntax, expiry, and OAuth scopes.",
            )
        )
        store.add_document(
            Document(
                tenant_id="globex",
                title="Globex Secret API 401 Runbook",
                source_type="api_doc",
                uri="kb://globex/secret-401",
                content="Globex private 401 remediation procedure. This must stay tenant-scoped.",
            )
        )

        chunks = store.list_chunks()
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.embedding for chunk in chunks))
        self.assertTrue(all(len(chunk.embedding or []) == EMBEDDING_DIMENSIONS for chunk in chunks))

        evidence = VectorRetriever().search(
            "acme",
            "Globex Secret API 401 Runbook",
            chunks,
        )

        self.assertTrue(evidence)
        self.assertTrue(all("globex" not in item.uri for item in evidence))

    def test_verifier_still_blocks_unauthorized_write_risk(self) -> None:
        workflow = SupportAgentWorkflow(InMemoryStore(seed=False))
        report = workflow._verify(
            "引用来源：\n[1] Runbook - kb://safe\n请修改客户数据。请不要发送原始密钥。",
            [
                Evidence(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    title="Runbook",
                    uri="kb://safe",
                    excerpt="Safe policy.",
                    score=0.9,
                )
            ],
            {"risk_level": "high"},
        )

        self.assertFalse(report["passed"])
        self.assertIn("unauthorized_write_risk", report["findings"])

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
        audit_actions = [audit.action for audit in store.list_audit_logs("acme")]
        self.assertIn("tool_call_denied", audit_actions)

    def test_log_search_backend_reads_configured_files_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "auth.log"
            log_path.write_text(
                "\n".join(
                    [
                        "tenant_id=globex request_id=req_123 status=401 bearer globex-token",
                        "tenant_id=acme request_id=req_123 status=401 bearer acme-secret-token scope=read",
                    ]
                ),
                encoding="utf-8",
            )
            registry = ToolRegistry(
                allowed_tools=["log_search"],
                backends={"log_search": LogSearchTool([str(log_path)])},
            )
            ticket = Ticket(
                tenant_id="acme",
                customer_name="Alice",
                channel="email",
                subject="API 401",
                description="request_id=req_123 bearer leaked-token",
            )

            call = registry.execute("run-id", "log_search", ticket)

        self.assertEqual(call.status, "success")
        self.assertIn("found 1 tenant-scoped matches", call.output_summary)
        self.assertIn("[REDACTED]", call.output_summary)
        self.assertNotIn("globex-token", call.output_summary)
        self.assertNotIn("acme-secret-token", call.output_summary)

    def test_readonly_database_backend_executes_select_and_blocks_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "support.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE request_metadata (tenant_id TEXT, request_id TEXT, status TEXT, reason TEXT)")
            conn.execute(
                "INSERT INTO request_metadata VALUES (?, ?, ?, ?)",
                ("acme", "req_123", "401", "expired token"),
            )
            conn.commit()
            conn.close()

            ticket = Ticket(
                tenant_id="acme",
                customer_name="Alice",
                channel="email",
                subject="API 401",
                description="request_id=req_123",
            )
            db_url = f"sqlite:///{db_path}"
            readonly_registry = ToolRegistry(
                allowed_tools=["db_read"],
                backends={
                    "db_read": ReadOnlyDatabaseTool(
                        database_url=db_url,
                        query=(
                            "SELECT status, reason FROM request_metadata "
                            "WHERE tenant_id = :tenant_id AND request_id = :request_id"
                        ),
                    )
                },
            )
            write_registry = ToolRegistry(
                allowed_tools=["db_read"],
                backends={
                    "db_read": ReadOnlyDatabaseTool(
                        database_url=db_url,
                        query="UPDATE request_metadata SET status = '200'",
                    )
                },
            )

            read_call = readonly_registry.execute("run-id", "db_read", ticket)
            write_call = write_registry.execute("run-id", "db_read", ticket)

        self.assertEqual(read_call.status, "success")
        self.assertIn("expired token", read_call.output_summary)
        self.assertEqual(write_call.status, "failed")
        self.assertIn("Only SELECT or WITH", write_call.output_summary)

    def test_bug_reports_plan_readonly_jira_and_github_searches(self) -> None:
        registry = ToolRegistry(
            allowed_tools=["jira_search", "github_search"],
            backends={
                "jira_search": FakeToolBackend("Jira read-only result"),
                "github_search": FakeToolBackend("GitHub read-only result"),
            },
        )
        ticket = Ticket(
            tenant_id="acme",
            customer_name="Dana",
            channel="email",
            subject="Checkout bug",
            description="Customer sees an outage-level checkout bug.",
        )

        planned = registry.plan(ticket, {"issue_type": "bug", "priority": "P1"})
        jira_call = registry.execute("run-id", "jira_search", ticket)
        github_call = registry.execute("run-id", "github_search", ticket)

        self.assertEqual(planned, ["jira_search", "github_search"])
        self.assertEqual(jira_call.output_summary, "Jira read-only result")
        self.assertEqual(github_call.output_summary, "GitHub read-only result")


if __name__ == "__main__":
    unittest.main()
