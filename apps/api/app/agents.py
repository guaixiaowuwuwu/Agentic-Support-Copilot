from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .knowledge import RetrievalFilters, Retriever, create_default_retriever
from .llm import ChatClient, LLMError
from .models import AgentRun, AgentStep, Approval, AuditLog, Evidence, Ticket, ToolCall
from .observability import log_event, set_span_attributes, telemetry_span
from .security import clip_text, redact_secrets, sanitize_for_log
from .store import Store
from .time_utils import utc_now
from .tools import ToolPermissionError, ToolRegistry

CITATION_RE = re.compile(r"^\s*\[(\d+)\]\s*(.*?)\s*-\s*(\S+)\s*$", re.MULTILINE)
DEFAULT_SYSTEM_PROMPT = (
    "你是企业客服协作系统的回复草稿生成器。只根据给定工单、检索证据和工具摘要写中文回复。"
)
DEFAULT_REPLY_POLICY = (
    "回复必须适合提交给人工审批；不要编造证据；不要要求客户发送原始密钥、token 或 API key；"
    "不要承诺已经执行、即将执行或可以执行未经授权的写操作。"
)
DEFAULT_CITATION_POLICY = (
    "末尾必须包含“引用来源：”。引用格式严格使用“[编号] 标题 - URI”，且编号必须对应给定证据。"
)
SECRET_SAFETY_LINE = "请不要通过工单发送原始密钥、token 或 API key。"
SECRET_TERMS = (
    "原始密钥",
    "密钥",
    "api key",
    "api_key",
    "apikey",
    "token",
    "令牌",
    "access token",
    "bearer token",
)
SECRET_REQUEST_TERMS = (
    "提供",
    "发送",
    "上传",
    "粘贴",
    "贴出",
    "分享",
    "把",
    "send",
    "provide",
    "share",
    "paste",
    "upload",
)
NEGATION_TERMS = ("不要", "请勿", "不能", "不得", "避免", "do not", "don't", "never", "without")
WRITE_OPERATION_TERMS = (
    "修改客户数据",
    "修改",
    "重置",
    "删除",
    "更新配置",
    "创建",
    "关闭工单",
    "关闭",
    "退款",
    "贷项",
    "合同变更",
    "变更合同",
    "禁用",
    "启用",
    "轮换密钥",
    "reset",
    "delete",
    "update",
    "create",
    "close",
    "refund",
    "disable",
    "enable",
    "rotate",
)
WRITE_COMMITMENT_TERMS = (
    "我们已经",
    "我已经",
    "已为",
    "已经为",
    "将为",
    "会为",
    "马上",
    "立即",
    "直接",
    "请",
    "we have",
    "i have",
    "we will",
    "i will",
)
WRITE_SAFE_TERMS = (
    "不要承诺",
    "不能承诺",
    "不得承诺",
    "需要审批",
    "需要人工审批",
    "需要转交",
    "转交",
    "未经确认",
    "without approval",
    "requires approval",
)


def _configured_text(name: str, default: str) -> str:
    path = os.getenv(f"{name}_FILE", "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip() or default
        except OSError:
            return default
    return os.getenv(name, "").strip() or default


@dataclass(frozen=True)
class PromptConfig:
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    reply_policy: str = DEFAULT_REPLY_POLICY
    citation_policy: str = DEFAULT_CITATION_POLICY
    citation_heading: str = "引用来源："
    prompt_version: str = "support-copilot-v1"

    @classmethod
    def from_env(cls) -> "PromptConfig":
        return cls(
            system_prompt=_configured_text("SUPPORT_COPILOT_LLM_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            reply_policy=_configured_text("SUPPORT_COPILOT_REPLY_POLICY", DEFAULT_REPLY_POLICY),
            citation_policy=_configured_text("SUPPORT_COPILOT_CITATION_POLICY", DEFAULT_CITATION_POLICY),
            citation_heading=os.getenv("SUPPORT_COPILOT_CITATION_HEADING", "引用来源：").strip() or "引用来源：",
            prompt_version=os.getenv("SUPPORT_COPILOT_PROMPT_VERSION", "support-copilot-v1").strip()
            or "support-copilot-v1",
        )

    def system_message(self) -> str:
        return (
            f"{self.system_prompt}\n\n"
            f"回复策略：{self.reply_policy}\n\n"
            f"引用策略：{self.citation_policy}"
        )


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
        chat_client: Optional[ChatClient] = None,
        prompt_config: Optional[PromptConfig] = None,
        min_retrieval_confidence: float = 0.18,
    ) -> None:
        self.store = store
        embedding_model = getattr(store, "embedding_model", None)
        if retriever is not None:
            self.retriever = retriever
        elif embedding_model is not None:
            self.retriever = create_default_retriever(store, embedding_model=embedding_model)
        else:
            self.retriever = create_default_retriever(store)
        self.tools = tools or ToolRegistry()
        self.chat_client = chat_client
        self.prompt_config = prompt_config or PromptConfig.from_env()
        self.min_retrieval_confidence = min_retrieval_confidence

    def start_run(self, ticket_id: str) -> AgentRun:
        ticket = self.store.get_ticket(ticket_id)
        run = self.store.create_run(AgentRun(ticket_id=ticket.id, tenant_id=ticket.tenant_id, status="running"))
        with telemetry_span(
            "agent.run",
            {
                "run.id": run.id,
                "run.trace_id": run.trace_id,
                "run.correlation_id": run.correlation_id,
                "ticket.id": ticket.id,
                "tenant.id": ticket.tenant_id,
            },
        ):
            self._audit(
                ticket.tenant_id,
                "system",
                "agent_run_started",
                "agent_run",
                run.id,
                self._run_metadata(run, ticket),
            )

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
                query = f"{ticket.subject} {ticket.description}"
                retrieval_filters = self._retrieval_filters(ticket, triage)
                evidence = self.retriever.search(
                    ticket.tenant_id,
                    query,
                    chunks,
                    filters=retrieval_filters,
                )
            run.evidence = evidence
            self.store.update_run(run)
            top_score = max((item.score for item in evidence), default=0.0)
            self._record_step(
                run,
                "retrieval",
                "success" if top_score >= self.min_retrieval_confidence else "blocked",
                (
                    f"Found {len(evidence)} tenant-scoped evidence chunks; "
                    f"top_score={top_score:.3f}; product_line={retrieval_filters.product_line or 'any'}."
                ),
                ticket.subject,
                latency_ms=metric["latency_ms"],
                evidence_ids=[item.chunk_id for item in evidence],
            )

            tool_calls = self._execute_optional_tools(run, ticket, triage)
            draft_reply = self._compose_reply(run, ticket, triage, evidence, tool_calls)

            verifier_report = self._verify(draft_reply, evidence, triage)
            run.verifier_report = verifier_report
            self.store.update_run(run)
            self._record_step(
                run,
                "verifier",
                "blocked" if verifier_report.get("manual_review_required") else "success",
                verifier_report["summary"],
                draft_reply,
                evidence_ids=[item.chunk_id for item in evidence],
            )

            manual_review_required = bool(verifier_report.get("manual_review_required"))
            action_type = "manual_review" if manual_review_required else "send_reply"
            if not verifier_report["passed"]:
                approval_reason = "Verifier requires a human to review missing evidence or policy concerns."
            elif manual_review_required:
                approval_reason = "High-risk workflow requires manual review before any customer-visible reply."
            else:
                approval_reason = "Customer-facing reply requires approval."
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
        self._audit(
            ticket.tenant_id,
            decided_by,
            "approval_approved",
            "approval",
            approval.id,
            self._approval_metadata(run, ticket, approval),
        )
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
        self._audit(
            ticket.tenant_id,
            decided_by,
            "approval_rejected",
            "approval",
            approval.id,
            self._approval_metadata(run, ticket, approval),
        )
        return self.store.get_run(run.id)

    def _triage(self, ticket: Ticket) -> Dict[str, str]:
        text = f"{ticket.subject} {ticket.description}".lower()
        outage_terms = ["production down", "outage", "all customers", "sev1"]
        if any(token in text for token in outage_terms):
            issue_type = "outage"
        elif "401" in text or "unauthorized" in text or "api" in text:
            issue_type = "api_auth"
        elif "invoice" in text or "billing" in text:
            issue_type = "billing"
        elif "bug" in text or "error" in text:
            issue_type = "bug"
        else:
            issue_type = "general_support"

        if any(token in text for token in outage_terms):
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

    def _retrieval_filters(self, ticket: Ticket, triage: Dict[str, str]) -> RetrievalFilters:
        text = f"{ticket.subject} {ticket.description}".lower()
        product_line = None
        if triage["issue_type"] == "api_auth" or any(token in text for token in ["api", "oauth", "token", "401"]):
            product_line = "api"
        elif triage["issue_type"] == "billing":
            product_line = "billing"
        elif triage["issue_type"] in {"bug", "outage"}:
            product_line = "platform"
        elif any(token in text for token in ["support", "question", "help", "general"]):
            product_line = "support"

        version_match = re.search(r"\b(v\d+(?:\.\d+)*)\b|\bversion\s+(\d+(?:\.\d+)*)\b", text)
        version = None
        if version_match:
            version = version_match.group(1) or f"v{version_match.group(2)}"

        return RetrievalFilters(
            product_line=product_line,
            version=version,
            permissions=("support_agent",),
            as_of=utc_now(),
        )

    def _execute_optional_tools(self, run: AgentRun, ticket: Ticket, triage: Dict[str, str]) -> List[ToolCall]:
        planned_tools = self.tools.plan(ticket, triage)
        tool_calls: List[ToolCall] = []

        for tool_name in planned_tools:
            try:
                call = self.tools.execute(run.id, tool_name, ticket, triage)
            except ToolPermissionError as exc:
                call = ToolCall(
                    run_id=run.id,
                    tool_name=tool_name,
                    status="denied",
                    input_summary="Denied by tool whitelist.",
                    output_summary=str(exc),
                )
            self.store.add_tool_call(call)
            self._audit_tool_call(ticket, call)
            tool_calls.append(call)

        if planned_tools:
            successful = sum(1 for call in tool_calls if call.status == "success")
            denied = sum(1 for call in tool_calls if call.status == "denied")
            failed = sum(1 for call in tool_calls if call.status == "failed")
            status = "success" if denied == 0 and failed == 0 else "blocked"
            summary = f"Executed {successful} read-only tools; failed {failed}; denied {denied} by whitelist."
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
        run: AgentRun,
        ticket: Ticket,
        triage: Dict[str, str],
        evidence: List[Evidence],
        tool_calls: List[ToolCall],
    ) -> str:
        fallback_reply = self._compose_template_reply(ticket, triage, evidence, tool_calls)
        if not evidence or self.chat_client is None:
            return fallback_reply

        messages = self._reply_messages(ticket, triage, evidence, tool_calls)
        llm_reply = ""
        try:
            with telemetry_span(
                "llm.call",
                {
                    "run.id": run.id,
                    "run.trace_id": run.trace_id,
                    "run.correlation_id": run.correlation_id,
                    "tenant.id": ticket.tenant_id,
                },
            ) as span:
                llm_reply = self.chat_client.complete(
                    messages,
                    temperature=0.2,
                    max_tokens=700,
                )
                normalized_reply = self._normalize_llm_reply(llm_reply, evidence, fallback_reply)
                policy_fallback = normalized_reply == fallback_reply and llm_reply.strip() != fallback_reply.strip()
                llm_status = "policy_fallback" if policy_fallback else "success"
                set_span_attributes(span, {"llm.status": llm_status, "llm.model": self._llm_model_name()})
                log_event(
                    "INFO",
                    "llm_call_completed",
                    run_id=run.id,
                    trace_id=run.trace_id,
                    correlation_id=run.correlation_id,
                    tenant_id=ticket.tenant_id,
                    status=llm_status,
                    model=self._llm_model_name(),
                )
                self._audit_llm_call(
                    ticket,
                    run,
                    status=llm_status,
                    messages=messages,
                    response_text=llm_reply,
                    fallback_used=policy_fallback,
                )
                return normalized_reply
        except LLMError as exc:
            log_event(
                "WARNING",
                "llm_call_completed",
                run_id=run.id,
                trace_id=run.trace_id,
                correlation_id=run.correlation_id,
                tenant_id=ticket.tenant_id,
                status="failed",
                model=self._llm_model_name(),
            )
            self._audit_llm_call(
                ticket,
                run,
                status="failed",
                messages=messages,
                response_text=llm_reply,
                fallback_used=True,
                error_summary=str(exc),
            )
            return fallback_reply

    def _compose_template_reply(
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

        if triage["issue_type"] == "api_auth":
            guidance = (
                "最可能的原因是 Authorization header 缺失、Bearer token 已过期、API key 无效，"
                "或 OAuth scope 不足。建议先确认请求是否使用 `Authorization: Bearer <token>`，"
                "再检查 token 过期时间和所需 scope。"
            )
            next_step = (
                "请提供 request_id、发生时间、接口路径，以及是否近期轮换过凭证；"
                "如果确认 token 已过期，请生成新 token 后用同一个 request_id 重试。"
            )
            topic = "API 401 问题"
        elif triage["issue_type"] == "billing":
            guidance = (
                "账单问题应先核对账期、发票号、付款状态、税务设置、订阅计划和按比例计费事件。"
                "退款、贷项或合同变更需要转交账务专员确认。"
            )
            next_step = "请提供发票号、账期、账户 ID 和争议的行项目，我们会先核对可见账单记录。"
            topic = "账单问题"
        elif triage["issue_type"] == "bug":
            guidance = (
                "缺陷排查需要复现步骤、受影响版本、运行环境、期望行为、实际行为，以及截图或日志。"
                "在升级前应先检索既有 Jira 和 GitHub 记录。"
            )
            next_step = "请提供复现步骤、版本、环境、发生时间和影响范围；如有临时规避方案我们会同步给客户。"
            topic = "缺陷问题"
        elif triage["issue_type"] == "outage":
            guidance = (
                "生产不可用、全量客户影响或 SEV1 报告应按 P1 事件处理，先核对状态页、事件负责人记录和近期发布。"
                "客户回复可以确认正在排查影响，但不要承诺未经确认的恢复时间。"
            )
            next_step = "请补充受影响区域、租户、时间窗口、request_id、业务影响和是否所有用户均受影响。"
            topic = "服务中断问题"
        else:
            guidance = (
                "当前问题需要先澄清产品区域、用户角色、期望结果、实际结果和发生时间，"
                "再判断是否需要转入专门 runbook。"
            )
            next_step = "请补充产品模块、操作路径、截图或日志、发生时间和期望结果。"
            topic = "通用支持问题"

        return (
            f"您好 {ticket.customer_name}，我们已按 {triage['priority']} 优先级初步排查该{topic}。\n\n"
            f"{guidance} 请不要通过工单发送原始密钥、token 或 API key。\n\n"
            f"工具检查摘要：{tool_summary}\n\n"
            f"建议回复客户的下一步：{next_step}\n\n"
            f"{self.prompt_config.citation_heading}\n{evidence_lines}"
        )

    def _reply_messages(
        self,
        ticket: Ticket,
        triage: Dict[str, str],
        evidence: List[Evidence],
        tool_calls: List[ToolCall],
    ) -> List[Dict[str, str]]:
        evidence_lines = "\n".join(
            f"[{index}] {item.title} - {item.uri}\n摘要：{item.excerpt}"
            for index, item in enumerate(evidence, start=1)
        )
        tool_lines = "\n".join(
            f"- {call.tool_name}: {call.output_summary}" for call in tool_calls if call.status == "success"
        )
        if not tool_lines:
            tool_lines = "- 当前无需额外工具动作。"

        return [
            {
                "role": "system",
                "content": self.prompt_config.system_message(),
            },
            {
                "role": "user",
                "content": (
                    "请生成一份客户可读的支持回复草稿。\n\n"
                    f"客户：{ticket.customer_name}\n"
                    f"渠道：{ticket.channel}\n"
                    f"主题：{redact_secrets(ticket.subject)}\n"
                    f"描述：{redact_secrets(ticket.description)}\n"
                    f"分诊：issue_type={triage['issue_type']}, priority={triage['priority']}, "
                    f"risk_level={triage['risk_level']}\n\n"
                    f"工具摘要：\n{tool_lines}\n\n"
                    f"可引用证据：\n{evidence_lines}"
                ),
            },
        ]

    def _normalize_llm_reply(self, llm_reply: str, evidence: List[Evidence], fallback_reply: str) -> str:
        reply = redact_secrets(llm_reply).strip()
        if not reply:
            return fallback_reply

        if self._contains_raw_secret_request(reply) or self._contains_unauthorized_write_promise(reply):
            return fallback_reply

        if not self._has_secret_safety_notice(reply):
            reply = f"{reply}\n\n{SECRET_SAFETY_LINE}"

        if self.prompt_config.citation_heading not in reply or "[1]" not in reply:
            citation_lines = "\n".join(
                f"[{index}] {item.title} - {item.uri}" for index, item in enumerate(evidence, start=1)
            )
            reply = f"{reply}\n\n{self.prompt_config.citation_heading}\n{citation_lines}"

        return reply

    def _verify(self, draft_reply: str, evidence: List[Evidence], triage: Dict[str, str]) -> Dict[str, object]:
        citation_report = self._validate_citations(draft_reply, evidence)
        top_evidence_score = max((item.score for item in evidence), default=0.0)
        has_confident_evidence = bool(evidence) and top_evidence_score >= self.min_retrieval_confidence
        risk_level = triage.get("risk_level", "unknown")
        high_risk = risk_level == "high"

        checks = [
            self._verifier_check(
                "citations_traceable",
                bool(citation_report["passed"]),
                "invalid_citations" if citation_report["invalid_citations"] else "missing_citations",
                "Reply citations must exactly match retrieved evidence.",
                severity="blocker",
            ),
            self._verifier_check(
                "retrieval_confidence",
                has_confident_evidence,
                "low_confidence_evidence",
                "At least one tenant-scoped evidence item must meet retrieval confidence.",
                severity="blocker",
            ),
            self._verifier_check(
                "raw_secret_request",
                not self._contains_raw_secret_request(draft_reply),
                "raw_secret_request",
                "Reply must not ask the customer to send raw secrets, tokens, or API keys.",
                severity="blocker",
            ),
            self._verifier_check(
                "secret_safety_notice",
                self._has_secret_safety_notice(draft_reply),
                "secret_handling_unclear",
                "Reply must explicitly tell the customer not to send raw credentials.",
                severity="blocker",
            ),
            self._verifier_check(
                "unauthorized_write_policy",
                not self._contains_unauthorized_write_promise(draft_reply),
                "unauthorized_write_risk",
                "Reply must not promise or request unauthorized write operations.",
                severity="blocker",
            ),
            self._verifier_check(
                "high_risk_manual_review",
                not high_risk,
                "high_risk_manual_review",
                "High-risk tickets require manual review even when the draft is policy compliant.",
                severity="review",
                blocking=False,
                manual_review_required=high_risk,
            ),
        ]

        blocking_findings = [
            check["finding"]
            for check in checks
            if check["blocking"] and not check["passed"] and check["finding"]
        ]
        review_findings = [
            check["finding"]
            for check in checks
            if check["manual_review_required"] and check["finding"]
        ]
        findings = sorted(set(blocking_findings + review_findings))
        passed = not blocking_findings
        manual_review_required = bool(review_findings) or not passed

        if passed and manual_review_required:
            summary = f"Verifier passed with manual review required: {', '.join(review_findings)}."
        elif passed:
            summary = "Verifier passed: reply cites retrieved evidence, avoids raw secrets, and stays within tool policy."
        else:
            summary = f"Verifier blocked: {', '.join(blocking_findings)}."

        return {
            "passed": passed,
            "findings": findings,
            "risk_level": risk_level,
            "summary": summary,
            "checks": checks,
            "manual_review_required": manual_review_required,
            "citation_report": citation_report,
            "top_evidence_score": round(top_evidence_score, 3),
            "min_retrieval_confidence": self.min_retrieval_confidence,
        }

    def _verifier_check(
        self,
        code: str,
        passed: bool,
        finding: str,
        summary: str,
        *,
        severity: str,
        blocking: bool = True,
        manual_review_required: bool = False,
    ) -> Dict[str, object]:
        return {
            "code": code,
            "passed": passed,
            "finding": "" if passed else finding,
            "severity": severity,
            "blocking": blocking,
            "manual_review_required": manual_review_required,
            "summary": summary,
        }

    def _contains_raw_secret_request(self, text: str) -> bool:
        for sentence in self._sentences(text):
            lowered = sentence.lower()
            if not any(term in lowered for term in SECRET_TERMS):
                continue
            if not any(term in lowered for term in SECRET_REQUEST_TERMS):
                continue
            if any(term in lowered for term in NEGATION_TERMS):
                continue
            return True
        return False

    def _has_secret_safety_notice(self, text: str) -> bool:
        for sentence in self._sentences(text):
            lowered = sentence.lower()
            if any(term in lowered for term in SECRET_TERMS) and any(term in lowered for term in NEGATION_TERMS):
                return True
        return False

    def _contains_unauthorized_write_promise(self, text: str) -> bool:
        for sentence in self._sentences(text):
            lowered = sentence.lower()
            if any(term in lowered for term in WRITE_SAFE_TERMS):
                continue
            if not any(term in lowered for term in WRITE_OPERATION_TERMS):
                continue
            if any(term in lowered for term in WRITE_COMMITMENT_TERMS):
                return True
        return False

    def _sentences(self, text: str) -> List[str]:
        return [part.strip() for part in re.split(r"[\n。！？!?；;]+", text) if part.strip()]

    def _validate_citations(self, draft_reply: str, evidence: List[Evidence]) -> Dict[str, object]:
        evidence_by_index = {
            index: (item.title.strip(), item.uri.strip(), item.chunk_id)
            for index, item in enumerate(evidence, start=1)
        }
        citation_lines = list(CITATION_RE.finditer(draft_reply))
        bracket_numbers = {int(match) for match in re.findall(r"\[(\d+)\]", draft_reply)}
        cited_evidence_ids: List[str] = []
        invalid_citations: List[str] = []

        if self.prompt_config.citation_heading not in draft_reply or not citation_lines:
            return {
                "passed": False,
                "citation_count": 0,
                "cited_evidence_ids": [],
                "sources": [],
                "invalid_citations": [],
            }

        for match in citation_lines:
            index = int(match.group(1))
            title = match.group(2).strip()
            uri = match.group(3).strip()
            expected = evidence_by_index.get(index)
            if expected is None:
                invalid_citations.append(f"[{index}] {title} - {uri}")
                continue
            expected_title, expected_uri, chunk_id = expected
            if title != expected_title or uri != expected_uri:
                invalid_citations.append(f"[{index}] {title} - {uri}")
                continue
            cited_evidence_ids.append(chunk_id)

        for index in bracket_numbers:
            if index not in evidence_by_index:
                invalid_citations.append(f"[{index}]")

        return {
            "passed": bool(cited_evidence_ids) and not invalid_citations,
            "citation_count": len(cited_evidence_ids),
            "cited_evidence_ids": cited_evidence_ids,
            "sources": [
                {
                    "evidence_id": item.chunk_id,
                    "document_id": item.document_id,
                    "title": item.title,
                    "uri": item.uri,
                }
                for item in evidence
                if item.chunk_id in cited_evidence_ids
            ],
            "invalid_citations": sorted(set(invalid_citations)),
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
        with telemetry_span(
            "agent.step",
            {
                "run.id": run.id,
                "run.trace_id": run.trace_id,
                "run.correlation_id": run.correlation_id,
                "tenant.id": run.tenant_id,
                "agent.step.name": name,
            },
        ) as span:
            run.current_node = name
            step = AgentStep(
                run_id=run.id,
                name=name,
                status=status,
                summary=clip_text(redact_secrets(summary), 1000),
                latency_ms=0 if latency_ms is None else latency_ms,
                token_count=estimate_tokens(summary, *token_parts),
                evidence_ids=evidence_ids or [],
                tool_call_ids=tool_call_ids or [],
            )
            recorded = self.store.add_step(step)
            set_span_attributes(
                span,
                {
                    "agent.step.id": recorded.id,
                    "agent.step.status": recorded.status,
                    "agent.step.latency_ms": recorded.latency_ms,
                    "agent.step.token_count": recorded.token_count,
                    "agent.step.evidence_count": len(recorded.evidence_ids),
                    "agent.step.tool_call_count": len(recorded.tool_call_ids),
                },
            )
            log_event(
                "INFO" if status == "success" else "WARNING",
                "agent_step_completed",
                run_id=run.id,
                trace_id=run.trace_id,
                correlation_id=run.correlation_id,
                tenant_id=run.tenant_id,
                step_id=recorded.id,
                step_name=name,
                status=status,
                latency_ms=recorded.latency_ms,
                token_count=recorded.token_count,
                evidence_ids=recorded.evidence_ids,
                tool_call_ids=recorded.tool_call_ids,
                summary=recorded.summary,
            )
            return recorded

    def _audit(
        self,
        tenant_id: str,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        metadata: Dict[str, Any],
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

    def _audit_tool_call(self, ticket: Ticket, call: ToolCall) -> None:
        run = self.store.get_run(call.run_id)
        action_by_status = {
            "success": "tool_call_succeeded",
            "failed": "tool_call_failed",
            "denied": "tool_call_denied",
        }
        self._audit(
            ticket.tenant_id,
            "system",
            action_by_status.get(call.status, "tool_call_recorded"),
            "tool_call",
            call.id,
            {
                "run_id": call.run_id,
                "ticket_id": ticket.id,
                "trace_id": run.trace_id,
                "correlation_id": run.correlation_id,
                "tool_name": call.tool_name,
                "status": call.status,
                "input_summary": call.input_summary,
                "output_summary": call.output_summary,
            },
        )
        log_event(
            "INFO" if call.status == "success" else "WARNING",
            "tool_call_audited",
            run_id=call.run_id,
            tool_call_id=call.id,
            trace_id=run.trace_id,
            correlation_id=run.correlation_id,
            tenant_id=ticket.tenant_id,
            tool_name=call.tool_name,
            status=call.status,
        )

    def _audit_llm_call(
        self,
        ticket: Ticket,
        run: AgentRun,
        *,
        status: str,
        messages: List[Dict[str, str]],
        response_text: str,
        fallback_used: bool,
        error_summary: str = "",
    ) -> None:
        metadata = {
            "run_id": run.id,
            "ticket_id": ticket.id,
            "trace_id": run.trace_id,
            "correlation_id": run.correlation_id,
            "status": status,
            "model": self._llm_model_name(),
            "prompt_version": self.prompt_config.prompt_version,
            "prompt_summary": self._prompt_summary(messages),
            "response_summary": clip_text(redact_secrets(response_text), 400) if response_text else "",
            "fallback_used": fallback_used,
            "error_summary": clip_text(redact_secrets(error_summary), 300) if error_summary else "",
            "client_metadata": getattr(self.chat_client, "last_call_metadata", {}),
        }
        self._audit(
            ticket.tenant_id,
            "system",
            "llm_call_completed",
            "agent_run",
            run.id,
            sanitize_for_log(metadata, string_limit=1000),
        )

    def _llm_model_name(self) -> str:
        if self.chat_client is None:
            return "deterministic_fallback"
        settings = getattr(self.chat_client, "settings", None)
        model = getattr(settings, "model", None) or getattr(self.chat_client, "model", None)
        return str(model or self.chat_client.__class__.__name__)

    def _prompt_summary(self, messages: List[Dict[str, str]]) -> Dict[str, object]:
        system_message = next((message["content"] for message in messages if message.get("role") == "system"), "")
        user_message = next((message["content"] for message in messages if message.get("role") == "user"), "")
        return {
            "message_count": len(messages),
            "system_summary": clip_text(redact_secrets(system_message), 400),
            "user_summary": clip_text(redact_secrets(user_message), 500),
        }

    def _run_metadata(self, run: AgentRun, ticket: Ticket) -> Dict[str, Any]:
        return {
            "ticket_id": ticket.id,
            "trace_id": run.trace_id,
            "correlation_id": run.correlation_id,
            "status": run.status,
        }

    def _approval_metadata(self, run: AgentRun, ticket: Ticket, approval: Approval) -> Dict[str, Any]:
        return {
            "run_id": run.id,
            "ticket_id": ticket.id,
            "trace_id": run.trace_id,
            "correlation_id": run.correlation_id,
            "approval_status": approval.status,
            "action_type": approval.action_type,
            "risk_level": approval.risk_level,
            "approval_reason": approval.reason,
            "decision_note_summary": clip_text(redact_secrets(approval.decision_note or ""), 400),
            "decided_at": approval.decided_at,
        }
