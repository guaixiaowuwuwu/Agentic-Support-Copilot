from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional

from .knowledge import Retriever, create_default_retriever
from .models import AgentRun, AgentStep, Approval, AuditLog, Evidence, Ticket, ToolCall
from .store import Store
from .time_utils import utc_now
from .tools import ToolPermissionError, ToolRegistry


@contextmanager
def measure_step() -> Iterable[Dict[str, int]]:
    payload = {"latency_ms": 0}
    start = time.perf_counter()
    try:
        yield payload
    finally:
        payload["latency_ms"] = int((time.perf_counter() - start) * 1000)


def estimate_tokens(*parts: str) -> int:
    return max(1, sum(len(part.split()) for part in parts))


class SupportAgentWorkflow:
    def __init__(
        self,
        store: Store,
        retriever: Optional[Retriever] = None,
        tools: Optional[ToolRegistry] = None,
    ) -> None:
        self.store = store
        self.retriever = retriever or create_default_retriever(store)
        self.tools = tools or ToolRegistry()

    def start_run(self, ticket_id: str) -> AgentRun:
        ticket = self.store.get_ticket(ticket_id)
        run = self.store.create_run(AgentRun(ticket_id=ticket.id, tenant_id=ticket.tenant_id, status="running"))
        self._audit(ticket.tenant_id, "system", "agent_run_started", "agent_run", run.id, {"ticket_id": ticket.id})

        triage = self._triage(ticket)
        run.triage = triage
        run.status = "running"
        ticket.priority = triage["priority"]
        ticket.issue_type = triage["issue_type"]
        ticket.status = "triaged"
        self.store.update_ticket(ticket)
        self.store.update_run(run)
        self._record_step(
            run,
            "triage",
            "success",
            f"{triage['issue_type']} classified as {triage['priority']} with {triage['risk_level']} risk.",
            ticket.subject,
            ticket.description,
        )

        with measure_step() as metric:
            chunks = None if self.retriever.uses_store_backend else self.store.list_chunks()
            evidence = self.retriever.search(ticket.tenant_id, f"{ticket.subject} {ticket.description}", chunks)
        run.evidence = evidence
        self.store.update_run(run)
        self._record_step(
            run,
            "retrieval",
            "success" if evidence else "blocked",
            f"Found {len(evidence)} tenant-scoped evidence chunks.",
            ticket.subject,
            latency_ms=metric["latency_ms"],
            evidence_ids=[item.chunk_id for item in evidence],
        )

        tool_calls = self._execute_optional_tools(run, ticket, triage)
        draft_reply = self._compose_reply(ticket, triage, evidence, tool_calls)

        verifier_report = self._verify(draft_reply, evidence, triage)
        run.verifier_report = verifier_report
        self.store.update_run(run)
        self._record_step(
            run,
            "verifier",
            "success" if verifier_report["passed"] else "blocked",
            verifier_report["summary"],
            draft_reply,
            evidence_ids=[item.chunk_id for item in evidence],
        )

        action_type = "send_reply" if verifier_report["passed"] else "manual_review"
        approval_reason = (
            "Customer-facing reply requires approval."
            if verifier_report["passed"]
            else "Verifier requires a human to review missing evidence or policy concerns."
        )
        approval = self.store.create_approval(
            Approval(
                run_id=run.id,
                ticket_id=ticket.id,
                action_type=action_type,
                proposed_reply=draft_reply,
                risk_level=triage["risk_level"],
                reason=approval_reason,
            )
        )
        run.approval_id = approval.id
        run.status = "awaiting_approval"
        run.current_node = "human_approval"
        ticket.status = "awaiting_approval"
        self.store.update_run(run)
        self.store.update_ticket(ticket)
        self._record_step(
            run,
            "human_approval",
            "blocked",
            f"Created {action_type} approval {approval.id}.",
            draft_reply,
        )
        return self.store.get_run(run.id)

    def approve(self, approval_id: str, decided_by: str = "support.lead", note: str = "") -> AgentRun:
        approval = self.store.get_approval(approval_id)
        if approval.status != "pending":
            raise ValueError("Approval has already been decided")

        approval.status = "approved"
        approval.decided_by = decided_by
        approval.decision_note = note
        approval.decided_at = utc_now()
        self.store.update_approval(approval)

        run = self.store.get_run(approval.run_id)
        ticket = self.store.get_ticket(approval.ticket_id)
        run.status = "completed"
        run.current_node = "reply_executor"
        run.final_reply = approval.proposed_reply
        ticket.status = "replied"
        ticket.final_reply = approval.proposed_reply
        self.store.update_run(run)
        self.store.update_ticket(ticket)
        self._record_step(
            run,
            "reply_executor",
            "success",
            "Approved reply recorded and ticket marked as replied.",
            approval.proposed_reply,
        )
        self._audit(ticket.tenant_id, decided_by, "approval_approved", "approval", approval.id, {"run_id": run.id})
        return self.store.get_run(run.id)

    def reject(self, approval_id: str, decided_by: str = "support.lead", note: str = "") -> AgentRun:
        approval = self.store.get_approval(approval_id)
        if approval.status != "pending":
            raise ValueError("Approval has already been decided")

        approval.status = "rejected"
        approval.decided_by = decided_by
        approval.decision_note = note
        approval.decided_at = utc_now()
        self.store.update_approval(approval)

        run = self.store.get_run(approval.run_id)
        ticket = self.store.get_ticket(approval.ticket_id)
        run.status = "rejected"
        run.current_node = "human_approval"
        ticket.status = "rejected"
        self.store.update_run(run)
        self.store.update_ticket(ticket)
        self._record_step(run, "human_approval", "blocked", f"Approval rejected: {note or 'no note'}", note)
        self._audit(ticket.tenant_id, decided_by, "approval_rejected", "approval", approval.id, {"run_id": run.id})
        return self.store.get_run(run.id)

    def _triage(self, ticket: Ticket) -> Dict[str, str]:
        text = f"{ticket.subject} {ticket.description}".lower()
        if "401" in text or "unauthorized" in text or "api" in text:
            issue_type = "api_auth"
        elif "invoice" in text or "billing" in text:
            issue_type = "billing"
        elif "bug" in text or "error" in text:
            issue_type = "bug"
        else:
            issue_type = "general_support"

        if any(token in text for token in ["production down", "outage", "all customers", "sev1"]):
            priority = "P1"
            risk_level = "high"
        elif "401" in text or "bug" in text or "error" in text:
            priority = "P2"
            risk_level = "medium"
        else:
            priority = "P3"
            risk_level = "low"

        return {
            "issue_type": issue_type,
            "priority": priority,
            "risk_level": risk_level,
            "requires_human_approval": "true",
        }

    def _execute_optional_tools(self, run: AgentRun, ticket: Ticket, triage: Dict[str, str]) -> List[ToolCall]:
        planned_tools = self.tools.plan(ticket, triage)
        tool_calls: List[ToolCall] = []
        denied = 0

        for tool_name in planned_tools:
            try:
                call = self.tools.execute(run.id, tool_name, ticket)
            except ToolPermissionError as exc:
                denied += 1
                call = ToolCall(
                    run_id=run.id,
                    tool_name=tool_name,
                    status="denied",
                    input_summary="Denied by tool whitelist.",
                    output_summary=str(exc),
                )
            self.store.add_tool_call(call)
            tool_calls.append(call)

        if planned_tools:
            status = "success" if denied == 0 else "blocked"
            summary = f"Executed {len(planned_tools) - denied} tools; denied {denied} by whitelist."
        else:
            status = "success"
            summary = "No tool call required for this ticket."

        self._record_step(
            run,
            "tool_call_optional",
            status,
            summary,
            ticket.description,
            tool_call_ids=[call.id for call in tool_calls],
        )
        return tool_calls

    def _compose_reply(
        self,
        ticket: Ticket,
        triage: Dict[str, str],
        evidence: List[Evidence],
        tool_calls: List[ToolCall],
    ) -> str:
        if not evidence:
            return (
                f"您好 {ticket.customer_name}，我们需要人工继续排查这个问题。当前信息不足以安全生成带引用的结论，"
                "请补充 request_id、发生时间、接口路径以及是否近期更换过凭证。"
            )

        evidence_lines = "\n".join(
            f"[{index}] {item.title} - {item.uri}" for index, item in enumerate(evidence, start=1)
        )
        tool_summary = "；".join(call.output_summary for call in tool_calls if call.status == "success")
        if not tool_summary:
            tool_summary = "当前无需额外工具动作。"

        return (
            f"您好 {ticket.customer_name}，我们已按 {triage['priority']} 优先级初步排查该 API 401 问题。\n\n"
            "最可能的原因是 Authorization header 缺失、Bearer token 已过期、API key 无效，"
            "或 OAuth scope 不足。建议先确认请求是否使用 `Authorization: Bearer <token>`，"
            "再检查 token 过期时间和所需 scope。请不要通过工单发送原始密钥。\n\n"
            f"工具检查摘要：{tool_summary}\n\n"
            "建议回复客户的下一步：请提供 request_id、发生时间、接口路径，以及是否近期轮换过凭证；"
            "如果确认 token 已过期，请生成新 token 后用同一个 request_id 重试。\n\n"
            f"引用来源：\n{evidence_lines}"
        )

    def _verify(self, draft_reply: str, evidence: List[Evidence], triage: Dict[str, str]) -> Dict[str, object]:
        has_sources = bool(evidence) and "引用来源" in draft_reply and "[1]" in draft_reply
        no_raw_secret_request = "原始密钥" in draft_reply and "不要" in draft_reply
        no_unauthorized_write = "修改客户数据" not in draft_reply
        passed = has_sources and no_raw_secret_request and no_unauthorized_write

        findings = []
        if not has_sources:
            findings.append("missing_citations")
        if not no_raw_secret_request:
            findings.append("secret_handling_unclear")
        if not no_unauthorized_write:
            findings.append("unauthorized_write_risk")

        if passed:
            summary = "Verifier passed: reply has citations, avoids raw secrets, and stays within tool policy."
        else:
            summary = f"Verifier blocked: {', '.join(findings)}."

        return {
            "passed": passed,
            "findings": findings,
            "risk_level": triage["risk_level"],
            "summary": summary,
        }

    def _record_step(
        self,
        run: AgentRun,
        name: str,
        status: str,
        summary: str,
        *token_parts: str,
        latency_ms: Optional[int] = None,
        evidence_ids: Optional[List[str]] = None,
        tool_call_ids: Optional[List[str]] = None,
    ) -> AgentStep:
        run.current_node = name
        step = AgentStep(
            run_id=run.id,
            name=name,
            status=status,
            summary=summary,
            latency_ms=0 if latency_ms is None else latency_ms,
            token_count=estimate_tokens(summary, *token_parts),
            evidence_ids=evidence_ids or [],
            tool_call_ids=tool_call_ids or [],
        )
        return self.store.add_step(step)

    def _audit(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        metadata: Dict[str, str],
    ) -> None:
        self.store.add_audit(
            AuditLog(
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                metadata=metadata,
            )
        )
