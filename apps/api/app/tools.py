from __future__ import annotations

import re
from typing import Dict, Iterable, List

from .models import Ticket, ToolCall

SECRET_RE = re.compile(r"(bearer\s+)[a-zA-Z0-9._-]+|(sk-[a-zA-Z0-9_-]+)", re.IGNORECASE)


class ToolPermissionError(PermissionError):
    pass


def redact_secrets(text: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1) or ''}[REDACTED]", text)


class ToolRegistry:
    def __init__(self, allowed_tools: Iterable[str] = ("log_search", "db_read", "jira_create")) -> None:
        self.allowed_tools = set(allowed_tools)

    def ensure_allowed(self, tool_name: str) -> None:
        if tool_name not in self.allowed_tools:
            raise ToolPermissionError(f"Tool '{tool_name}' is not in the whitelist")

    def plan(self, ticket: Ticket, triage: Dict[str, str]) -> List[str]:
        planned: List[str] = []
        text = f"{ticket.subject} {ticket.description}".lower()

        if triage.get("issue_type") == "api_auth" or "401" in text:
            planned.extend(["log_search", "db_read"])

        if triage.get("priority") == "P1" or "outage" in text or "bug" in text:
            planned.append("jira_create")

        return planned

    def execute(self, run_id: str, tool_name: str, ticket: Ticket) -> ToolCall:
        self.ensure_allowed(tool_name)
        input_summary = redact_secrets(f"{ticket.subject} :: {ticket.description}")[:260]

        if tool_name == "log_search":
            output = (
                "Read-only log search completed. Auth service shows repeated 401 responses for matching "
                "request patterns, with no platform-wide outage signal."
            )
        elif tool_name == "db_read":
            output = (
                "Read-only metadata check completed. Likely causes are expired token, missing Bearer prefix, "
                "or insufficient OAuth scope. No customer data was modified."
            )
        elif tool_name == "jira_create":
            output = (
                f"Jira escalation draft SUP-{ticket.id[:8].upper()} prepared for support review. "
                "No external ticket was written without approval."
            )
        else:
            output = "Unknown tool."

        return ToolCall(
            run_id=run_id,
            tool_name=tool_name,
            status="success",
            input_summary=input_summary,
            output_summary=output,
        )

