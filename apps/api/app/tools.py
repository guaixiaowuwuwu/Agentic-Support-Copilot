from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Ticket, ToolCall

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional runtime dependency.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


DEFAULT_ALLOWED_TOOLS = ("log_search", "db_read", "jira_search", "github_search")
DEFAULT_TOOL_RESULT_LIMIT = 5
DEFAULT_HTTP_TIMEOUT_SECONDS = 8

SECRET_RE = re.compile(
    r"(bearer\s+)[a-zA-Z0-9._-]+|"
    r"(sk-[a-zA-Z0-9_-]+)|"
    r"((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+",
    re.IGNORECASE,
)
REQUEST_ID_RE = re.compile(
    r"\b(?:request[_-]?id|req(?:uest)?id)\s*[:=]\s*([a-zA-Z0-9._:-]+)\b",
    re.IGNORECASE,
)
REQUEST_ID_FALLBACK_RE = re.compile(r"\b(req_[a-zA-Z0-9._:-]+)\b", re.IGNORECASE)
SQL_FORBIDDEN_RE = re.compile(
    r"\b("
    r"alter|analyze|call|copy|create|delete|do|drop|execute|grant|insert|listen|lock|merge|"
    r"notify|reindex|revoke|truncate|update|vacuum"
    r")\b",
    re.IGNORECASE,
)
TENANT_MARKER_RE = re.compile(r"\btenant(?:_id)?\s*[:=]\s*([a-zA-Z0-9_-]+)\b", re.IGNORECASE)


class ToolPermissionError(PermissionError):
    pass


class ToolBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str
    tool_name: str
    ticket: Ticket
    triage: Mapping[str, str]
    request_id: Optional[str]
    search_text: str
    input_summary: str


class ToolBackend(Protocol):
    def execute(self, context: ToolExecutionContext) -> str:
        ...


def redact_secrets(text: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1) or match.group(3) or ''}[REDACTED]", text)


def create_tool_registry_from_env() -> "ToolRegistry":
    allowed_tools = _split_csv(os.getenv("SUPPORT_COPILOT_ALLOWED_TOOLS")) or list(DEFAULT_ALLOWED_TOOLS)
    result_limit = _env_int("SUPPORT_COPILOT_TOOL_RESULT_LIMIT", DEFAULT_TOOL_RESULT_LIMIT)
    timeout_seconds = _env_int("SUPPORT_COPILOT_TOOL_TIMEOUT_SECONDS", DEFAULT_HTTP_TIMEOUT_SECONDS)

    backends: Dict[str, ToolBackend] = {}

    log_paths = _split_csv(os.getenv("SUPPORT_COPILOT_LOG_PATHS"))
    if log_paths:
        backends["log_search"] = LogSearchTool(
            log_paths=log_paths,
            max_lines=result_limit,
            max_bytes=_env_int("SUPPORT_COPILOT_LOG_MAX_BYTES", 2_000_000),
        )

    readonly_database_url = os.getenv("SUPPORT_COPILOT_READONLY_DATABASE_URL") or os.getenv("READONLY_DATABASE_URL")
    readonly_query = os.getenv("SUPPORT_COPILOT_READONLY_DB_QUERY")
    if readonly_database_url and readonly_query:
        backends["db_read"] = ReadOnlyDatabaseTool(
            database_url=readonly_database_url,
            query=readonly_query,
            max_rows=result_limit,
            timeout_seconds=timeout_seconds,
        )

    jira_base_url = os.getenv("SUPPORT_COPILOT_JIRA_BASE_URL")
    if jira_base_url:
        backends["jira_search"] = JiraSearchTool(
            base_url=jira_base_url,
            email=os.getenv("SUPPORT_COPILOT_JIRA_EMAIL"),
            api_token=os.getenv("SUPPORT_COPILOT_JIRA_API_TOKEN"),
            bearer_token=os.getenv("SUPPORT_COPILOT_JIRA_BEARER_TOKEN"),
            project_key=os.getenv("SUPPORT_COPILOT_JIRA_PROJECT_KEY"),
            jql_template=os.getenv("SUPPORT_COPILOT_JIRA_JQL_TEMPLATE"),
            search_path=os.getenv("SUPPORT_COPILOT_JIRA_SEARCH_PATH", "/rest/api/3/search"),
            max_results=result_limit,
            timeout_seconds=timeout_seconds,
        )

    github_repos = _split_csv(os.getenv("SUPPORT_COPILOT_GITHUB_REPOS"))
    if github_repos:
        backends["github_search"] = GitHubSearchTool(
            repos=github_repos,
            base_url=os.getenv("SUPPORT_COPILOT_GITHUB_BASE_URL", "https://api.github.com"),
            token=os.getenv("SUPPORT_COPILOT_GITHUB_TOKEN"),
            api_version=os.getenv("SUPPORT_COPILOT_GITHUB_API_VERSION"),
            max_results=result_limit,
            timeout_seconds=timeout_seconds,
        )

    return ToolRegistry(allowed_tools=allowed_tools, backends=backends)


class ToolRegistry:
    def __init__(
        self,
        allowed_tools: Iterable[str] = DEFAULT_ALLOWED_TOOLS,
        backends: Optional[Mapping[str, ToolBackend]] = None,
    ) -> None:
        self.allowed_tools = set(allowed_tools)
        self.backends = dict(backends or {})

    def ensure_allowed(self, tool_name: str) -> None:
        if tool_name not in self.allowed_tools:
            raise ToolPermissionError(f"Tool '{tool_name}' is not in the whitelist")

    def plan(self, ticket: Ticket, triage: Dict[str, str]) -> List[str]:
        planned: List[str] = []
        text = f"{ticket.subject} {ticket.description}".lower()

        if triage.get("issue_type") == "api_auth" or "401" in text:
            planned.extend(["log_search", "db_read"])

        if triage.get("priority") == "P1" or "outage" in text or "bug" in text:
            planned.extend(["jira_search", "github_search"])

        return planned

    def execute(
        self,
        run_id: str,
        tool_name: str,
        ticket: Ticket,
        triage: Optional[Mapping[str, str]] = None,
    ) -> ToolCall:
        self.ensure_allowed(tool_name)
        context = self._context(run_id, tool_name, ticket, triage or {})
        status = "success"

        try:
            backend = self.backends.get(tool_name)
            output = backend.execute(context) if backend else self._mock_output(tool_name, ticket)
        except ToolBackendError as exc:
            status = "failed"
            output = f"{tool_name} failed: {exc}"
        except Exception as exc:  # pragma: no cover - defensive guard for third-party SDK/runtime errors.
            status = "failed"
            output = f"{tool_name} failed: {exc.__class__.__name__}: {exc}"

        return ToolCall(
            run_id=run_id,
            tool_name=tool_name,
            status=status,
            input_summary=context.input_summary,
            output_summary=_clip(redact_secrets(output), 1000),
        )

    def configured_backends(self) -> List[str]:
        return sorted(self.backends)

    def _context(
        self,
        run_id: str,
        tool_name: str,
        ticket: Ticket,
        triage: Mapping[str, str],
    ) -> ToolExecutionContext:
        input_summary = redact_secrets(f"{ticket.subject} :: {ticket.description}")[:260]
        request_id = extract_request_id(ticket)
        search_text = request_id or _search_text(ticket)
        return ToolExecutionContext(
            run_id=run_id,
            tool_name=tool_name,
            ticket=ticket,
            triage=triage,
            request_id=request_id,
            search_text=search_text,
            input_summary=input_summary,
        )

    def _mock_output(self, tool_name: str, ticket: Ticket) -> str:
        if tool_name == "log_search":
            return (
                "Read-only log search completed. Auth service shows repeated 401 responses for matching "
                "request patterns, with no platform-wide outage signal."
            )
        if tool_name == "db_read":
            return (
                "Read-only metadata check completed. Likely causes are expired token, missing Bearer prefix, "
                "or insufficient OAuth scope. No customer data was modified."
            )
        if tool_name == "jira_search":
            return (
                "Read-only Jira search completed in deterministic fallback mode. Similar support issues may "
                "exist, but no external Jira issue was created or modified."
            )
        if tool_name == "github_search":
            return (
                "Read-only GitHub search completed in deterministic fallback mode. No code, issue, or pull "
                "request was created or modified."
            )
        if tool_name == "jira_create":
            return (
                f"Jira escalation draft SUP-{ticket.id[:8].upper()} prepared for support review. "
                "No external ticket was written without approval."
            )
        return f"Unknown tool '{tool_name}'. No external action was performed."


class LogSearchTool:
    def __init__(
        self,
        log_paths: Iterable[str],
        max_lines: int = DEFAULT_TOOL_RESULT_LIMIT,
        max_bytes: int = 2_000_000,
    ) -> None:
        self.log_paths = [Path(path).expanduser() for path in log_paths]
        self.max_lines = max(1, max_lines)
        self.max_bytes = max(1024, max_bytes)

    def execute(self, context: ToolExecutionContext) -> str:
        files = self._candidate_files()
        if not files:
            return "Read-only log search found no configured log files to scan."

        matches: List[str] = []
        scanned = 0
        for path in files:
            scanned += 1
            try:
                matches.extend(self._matching_lines(path, context))
            except OSError as exc:
                matches.append(f"{path.name}: skipped ({exc.__class__.__name__})")
            if len(matches) >= self.max_lines:
                break

        if not matches:
            return f"Read-only log search scanned {scanned} files and found no tenant-scoped matches."

        summary = " | ".join(matches[: self.max_lines])
        return (
            f"Read-only log search scanned {scanned} files and found {len(matches)} tenant-scoped matches. "
            f"Top signals: {summary}"
        )

    def _candidate_files(self) -> List[Path]:
        files: List[Path] = []
        for path in self.log_paths:
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                files.extend(sorted(item for item in path.rglob("*.log") if item.is_file())[:20])
        return files[:40]

    def _matching_lines(self, path: Path, context: ToolExecutionContext) -> List[str]:
        matches: List[str] = []
        bytes_read = 0
        terms = _search_terms(context)
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, line in enumerate(handle, start=1):
                bytes_read += len(line.encode("utf-8", errors="ignore"))
                if bytes_read > self.max_bytes:
                    break
                if not _line_matches_context(line, context, terms):
                    continue
                cleaned = _clip(redact_secrets(" ".join(line.split())), 180)
                matches.append(f"{path.name}:{line_number} {cleaned}")
                if len(matches) >= self.max_lines:
                    break
        return matches


class ReadOnlyDatabaseTool:
    def __init__(
        self,
        database_url: str,
        query: str,
        max_rows: int = DEFAULT_TOOL_RESULT_LIMIT,
        timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.database_url = database_url
        self.query = query
        self.max_rows = max(1, max_rows)
        self.timeout_seconds = max(1, timeout_seconds)

    def execute(self, context: ToolExecutionContext) -> str:
        _ensure_read_only_sql(self.query)
        _ensure_tenant_scoped_sql(self.query)
        if self.database_url.startswith("sqlite:///"):
            rows = self._execute_sqlite(context)
        else:
            rows = self._execute_postgres(context)
        return _summarize_rows("Read-only database query", rows, self.max_rows)

    def _params(self, context: ToolExecutionContext) -> Dict[str, Any]:
        return {
            "tenant_id": context.ticket.tenant_id,
            "request_id": context.request_id or "",
            "query": context.search_text,
        }

    def _execute_sqlite(self, context: ToolExecutionContext) -> List[Mapping[str, Any]]:
        path = self.database_url.removeprefix("sqlite:///")
        uri = f"file:{path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=self.timeout_seconds)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(self.query, self._params(context)).fetchmany(self.max_rows + 1)
                return [dict(row) for row in rows]
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise ToolBackendError(f"SQLite read-only query failed: {exc}") from exc

    def _execute_postgres(self, context: ToolExecutionContext) -> List[Mapping[str, Any]]:
        if psycopg is None or dict_row is None:
            raise ToolBackendError("psycopg is required for PostgreSQL read-only tools")

        try:
            with psycopg.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=self.timeout_seconds,
            ) as conn:
                with conn.transaction():
                    conn.execute("SET TRANSACTION READ ONLY")
                    conn.execute(f"SET LOCAL statement_timeout = {self.timeout_seconds * 1000}")
                    rows = conn.execute(self.query, self._params(context)).fetchmany(self.max_rows + 1)
            return rows
        except Exception as exc:
            raise ToolBackendError(f"PostgreSQL read-only query failed: {exc}") from exc


class JiraSearchTool:
    def __init__(
        self,
        base_url: str,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        bearer_token: Optional[str] = None,
        project_key: Optional[str] = None,
        jql_template: Optional[str] = None,
        search_path: str = "/rest/api/3/search",
        max_results: int = DEFAULT_TOOL_RESULT_LIMIT,
        timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.bearer_token = bearer_token
        self.project_key = _safe_jql_token(project_key or "")
        self.jql_template = jql_template
        self.search_path = search_path
        self.max_results = max(1, max_results)
        self.timeout_seconds = max(1, timeout_seconds)

    def execute(self, context: ToolExecutionContext) -> str:
        if not (self.bearer_token or (self.email and self.api_token)):
            return "Read-only Jira search is configured without credentials; no external Jira request was made."

        jql = self._jql(context)
        payload = {
            "jql": jql,
            "maxResults": self.max_results,
            "fields": ["summary", "status", "priority", "updated"],
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._auth_headers(),
        }
        body = json.dumps(payload).encode("utf-8")
        data = _http_json("POST", _join_url(self.base_url, self.search_path), headers, body, self.timeout_seconds)

        issues = data.get("issues") or []
        if not issues:
            return "Read-only Jira search returned no matching issues."

        summaries = []
        for issue in issues[: self.max_results]:
            fields = issue.get("fields") or {}
            status = (fields.get("status") or {}).get("name", "unknown")
            priority = (fields.get("priority") or {}).get("name", "unprioritized")
            summaries.append(
                f"{issue.get('key', 'unknown')}: {_clip(str(fields.get('summary') or ''), 90)} "
                f"({status}, {priority})"
            )
        return f"Read-only Jira search returned {len(issues)} issues. Top matches: {' | '.join(summaries)}"

    def _jql(self, context: ToolExecutionContext) -> str:
        search_text = _safe_jql_text(context.search_text)
        if self.jql_template:
            return (
                self.jql_template.replace("{search_text}", search_text).replace("{project_key}", self.project_key)
            )
        if self.project_key:
            return f'project = "{self.project_key}" AND text ~ "{search_text}" ORDER BY updated DESC'
        return f'text ~ "{search_text}" ORDER BY updated DESC'

    def _auth_headers(self) -> Dict[str, str]:
        if self.bearer_token:
            return {"Authorization": f"Bearer {self.bearer_token}"}
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}


class GitHubSearchTool:
    def __init__(
        self,
        repos: Iterable[str],
        base_url: str = "https://api.github.com",
        token: Optional[str] = None,
        api_version: Optional[str] = None,
        max_results: int = DEFAULT_TOOL_RESULT_LIMIT,
        timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.repos = [_safe_repo(repo) for repo in repos if _safe_repo(repo)]
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.api_version = api_version
        self.max_results = max(1, max_results)
        self.timeout_seconds = max(1, timeout_seconds)

    def execute(self, context: ToolExecutionContext) -> str:
        if not self.repos:
            return "Read-only GitHub search has no configured repositories; no external GitHub request was made."

        headers = {
            "Accept": "application/vnd.github+json",
            **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            **({"X-GitHub-Api-Version": self.api_version} if self.api_version else {}),
        }
        collected: List[Mapping[str, Any]] = []
        for repo in self.repos:
            query = f"repo:{repo} is:issue {_safe_github_query(context.search_text)}"
            params = urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": self.max_results})
            data = _http_json(
                "GET",
                f"{_join_url(self.base_url, '/search/issues')}?{params}",
                headers,
                None,
                self.timeout_seconds,
            )
            collected.extend(data.get("items") or [])
            if len(collected) >= self.max_results:
                break

        if not collected:
            return "Read-only GitHub issue search returned no matching issues."

        summaries = []
        for item in collected[: self.max_results]:
            repo_name = (item.get("repository_url") or "").rsplit("/", 2)[-2:]
            repo_label = "/".join(repo_name) if repo_name else "unknown/repo"
            summaries.append(
                f"{repo_label}#{item.get('number', '?')}: {_clip(str(item.get('title') or ''), 90)} "
                f"({item.get('state', 'unknown')})"
            )
        return (
            f"Read-only GitHub issue search returned {len(collected)} issues. "
            f"Top matches: {' | '.join(summaries)}"
        )


def extract_request_id(ticket: Ticket) -> Optional[str]:
    text = f"{ticket.subject} {ticket.description}"
    match = REQUEST_ID_RE.search(text) or REQUEST_ID_FALLBACK_RE.search(text)
    return match.group(1) if match else None


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _clip(text: str, limit: int) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 3)]}..."


def _search_text(ticket: Ticket) -> str:
    redacted = redact_secrets(f"{ticket.subject} {ticket.description}")
    cleaned = re.sub(r"[^a-zA-Z0-9_\-:. \u4e00-\u9fff]", " ", redacted)
    return _clip(cleaned, 96)


def _search_terms(context: ToolExecutionContext) -> List[str]:
    if context.request_id:
        return [context.request_id.lower()]
    tokens = re.findall(r"[a-zA-Z0-9_:-]{3,}", context.search_text.lower())
    useful = [token for token in tokens if token not in {"api", "the", "and", "for", "with"}]
    return useful[:8] or [context.ticket.tenant_id.lower()]


def _line_matches_context(line: str, context: ToolExecutionContext, terms: List[str]) -> bool:
    lowered = line.lower()
    tenant_markers = [match.group(1).lower() for match in TENANT_MARKER_RE.finditer(line)]
    if tenant_markers and context.ticket.tenant_id.lower() not in tenant_markers:
        return False
    if not tenant_markers and context.ticket.tenant_id.lower() not in lowered:
        return False
    if context.request_id:
        return context.request_id.lower() in lowered
    return context.ticket.tenant_id.lower() in lowered and any(term in lowered for term in terms)


def _ensure_read_only_sql(sql: str) -> None:
    normalized = sql.strip()
    lowered = normalized.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ToolBackendError("Only SELECT or WITH read-only SQL statements are allowed")
    if ";" in normalized.rstrip(";"):
        raise ToolBackendError("Multiple SQL statements are not allowed")
    if SQL_FORBIDDEN_RE.search(normalized):
        raise ToolBackendError("SQL contains a forbidden write or administrative keyword")


def _ensure_tenant_scoped_sql(sql: str) -> None:
    lowered = sql.lower()
    if "tenant_id" not in lowered:
        raise ToolBackendError("Read-only SQL must include tenant_id filtering")
    if "%(tenant_id)s" not in lowered and ":tenant_id" not in lowered:
        raise ToolBackendError("Read-only SQL must bind the tenant_id parameter")


def _summarize_rows(label: str, rows: List[Mapping[str, Any]], max_rows: int) -> str:
    if not rows:
        return f"{label} returned no rows."

    visible_rows = rows[:max_rows]
    summaries = []
    for row in visible_rows:
        columns = list(row.keys())[:6]
        summaries.append(
            ", ".join(f"{column}={_clip(redact_secrets(str(row.get(column, ''))), 80)}" for column in columns)
        )
    suffix = " Additional rows were omitted." if len(rows) > max_rows else ""
    return f"{label} returned {len(rows)} rows. Rows: {' | '.join(summaries)}.{suffix}"


def _safe_jql_token(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)[:80]


def _safe_jql_text(value: str) -> str:
    cleaned = re.sub(r'["\\]', " ", value)
    cleaned = re.sub(r"[^a-zA-Z0-9_\-:. \u4e00-\u9fff]", " ", cleaned)
    return _clip(cleaned, 80) or "support"


def _safe_repo(repo: str) -> str:
    repo = repo.strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return repo
    return ""


def _safe_github_query(value: str) -> str:
    cleaned = re.sub(r'["\\]', " ", value)
    cleaned = re.sub(r"[^a-zA-Z0-9_\-:. ]", " ", cleaned)
    return _clip(cleaned, 80) or "support"


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _http_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Optional[bytes],
    timeout_seconds: int,
) -> Mapping[str, Any]:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise ToolBackendError(f"HTTP {exc.code}: {redact_secrets(detail)}") from exc
    except URLError as exc:
        raise ToolBackendError(f"HTTP request failed: {redact_secrets(str(exc.reason))}") from exc
    except OSError as exc:
        raise ToolBackendError(f"HTTP request failed: {redact_secrets(str(exc))}") from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolBackendError("HTTP response was not valid JSON") from exc
    if not isinstance(data, Mapping):
        raise ToolBackendError("HTTP response JSON was not an object")
    return data
