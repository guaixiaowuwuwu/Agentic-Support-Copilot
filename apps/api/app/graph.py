from __future__ import annotations


def graph_engine_name() -> str:
    try:
        import langgraph  # noqa: F401
    except Exception:
        return "sequential-fallback"
    return "langgraph-ready"


WORKFLOW_NODES = [
    "triage",
    "retrieval",
    "tool_call_optional",
    "verifier",
    "human_approval",
    "reply_executor",
]

