import type {
  AdminConfig,
  AgentRun,
  Approval,
  AuditLog,
  Document,
  RunTrace,
  Ticket,
  UserContext
} from "@support-copilot/shared";

import { getBrowserLoginRole, identityHeadersForUser, userContextForLoginRole } from "@/lib/local-auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const APP_ENV =
  (
    process.env.NEXT_PUBLIC_SUPPORT_COPILOT_ENV ??
    process.env.NEXT_PUBLIC_VERCEL_ENV ??
    process.env.NODE_ENV ??
    "development"
  ).toLowerCase();
const PRODUCTION_LIKE_ENVS = new Set(["production", "staging", "preview"]);
const DEMO_MODE_ENABLED =
  process.env.NEXT_PUBLIC_SUPPORT_COPILOT_DEMO_MODE === "true" && !PRODUCTION_LIKE_ENVS.has(APP_ENV);
const LOCAL_IDENTITY_HEADERS_ENABLED =
  !PRODUCTION_LIKE_ENVS.has(APP_ENV) && process.env.NEXT_PUBLIC_SUPPORT_COPILOT_LOCAL_IDENTITY_HEADERS !== "false";

type ApiErrorOptions = {
  status?: number;
  detail?: string;
  path?: string;
  cause?: unknown;
};

export class ApiError extends Error {
  status?: number;
  detail?: string;
  path?: string;

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.detail = options.detail;
    this.path = options.path;
    this.cause = options.cause;
  }

  get isPermissionError(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

export const apiConfig = {
  baseUrl: API_BASE,
  appEnv: APP_ENV,
  demoMode: DEMO_MODE_ENABLED,
  localIdentityHeaders: LOCAL_IDENTITY_HEADERS_ENABLED
};

export const localDevUserContext: UserContext = userContextForLoginRole("support_agent");

export function localDevIdentityHeaders(userContext?: UserContext | null): Record<string, string> {
  if (!LOCAL_IDENTITY_HEADERS_ENABLED) {
    return {};
  }
  const browserRole = userContext ? null : getBrowserLoginRole();
  const activeUser = userContext ?? (browserRole ? userContextForLoginRole(browserRole) : null);
  return identityHeadersForUser(activeUser);
}

async function readResponseDetail(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return "";
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
    const detail = parsed.detail ?? parsed.message;
    return typeof detail === "string" ? detail : text;
  } catch {
    return text;
  }
}

export async function apiErrorFromResponse(response: Response, path: string): Promise<ApiError> {
  const detail = await readResponseDetail(response);
  return new ApiError(detail || `Request failed with status ${response.status}`, {
    status: response.status,
    detail,
    path
  });
}

export function normalizeApiError(error: unknown, path: string): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (error instanceof Error) {
    return new ApiError(error.message || "Unable to reach the API", { path, cause: error });
  }
  return new ApiError("Unable to reach the API", { path, cause: error });
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isPermissionError(error: unknown): boolean {
  return isApiError(error) && error.isPermissionError;
}

export function isAuthenticationError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}

export function isNotFoundError(error: unknown): boolean {
  return isApiError(error) && error.status === 404;
}

export async function apiGet<T>(path: string, demoFallback?: T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: localDevIdentityHeaders()
    });
    if (!response.ok) {
      throw await apiErrorFromResponse(response, path);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (DEMO_MODE_ENABLED && demoFallback !== undefined) {
      return demoFallback;
    }
    throw normalizeApiError(error, path);
  }
}

export async function apiPost<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...localDevIdentityHeaders() },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response, path);
  }
  return (await response.json()) as T;
}

export const demoTicket: Ticket = {
  id: "demo-ticket-api-401",
  tenant_id: "acme",
  customer_name: "Acme Customer",
  channel: "email",
  subject: "API 报 401",
  description: "客户说 API 报 401，帮我排查并回复。",
  status: "awaiting_approval",
  priority: "P2",
  issue_type: "api_auth",
  final_reply: null,
  run_ids: ["demo-run-api-401"],
  created_at: new Date(Date.now() - 1000 * 60 * 42).toISOString(),
  updated_at: new Date(Date.now() - 1000 * 60 * 9).toISOString()
};

export const demoApproval: Approval = {
  id: "demo-approval-api-401",
  run_id: "demo-run-api-401",
  ticket_id: "demo-ticket-api-401",
  action_type: "send_reply",
  proposed_reply:
    "您好 Acme Customer，我们已按 P2 优先级初步排查该 API 401 问题。最可能的原因是 Authorization header 缺失、Bearer token 已过期、API key 无效，或 OAuth scope 不足。\n\n引用来源：\n[1] API Authentication Runbook - kb://api/authentication-runbook",
  risk_level: "medium",
  reason: "Customer-facing reply requires approval.",
  status: "pending",
  created_at: new Date(Date.now() - 1000 * 60 * 8).toISOString()
};

export const demoDocuments: Document[] = [
  {
    id: "demo-doc-auth-runbook",
    tenant_id: "acme",
    title: "API Authentication Runbook",
    source_type: "knowledge_base",
    uri: "kb://api/authentication-runbook",
    content:
      "401 Unauthorized responses are usually caused by a missing Authorization header, expired token, invalid API key, or insufficient OAuth scope.",
    status: "active",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    updated_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    chunk_count: 1,
    embedded_chunk_count: 1,
    embedding_status: "embedded"
  }
];

export const demoAuditLogs: AuditLog[] = [
  {
    id: "demo-audit-approval",
    tenant_id: "acme",
    actor: "lead@acme.example",
    action: "approval_approved_via_api",
    target_type: "approval",
    target_id: "demo-approval-api-401",
    metadata: {
      ticket_id: "demo-ticket-api-401",
      run_id: "demo-run-api-401",
      trace_id: "demo-trace-api-401",
      correlation_id: "demo-correlation-api-401",
      approval_reason: "Customer-facing reply requires approval.",
      decision_note_summary: "Approved from dashboard"
    },
    created_at: new Date(Date.now() - 1000 * 60 * 6).toISOString()
  },
  {
    id: "demo-audit-tool",
    tenant_id: "acme",
    actor: "system",
    action: "tool_call_succeeded",
    target_type: "tool_call",
    target_id: "tool-log",
    metadata: {
      run_id: "demo-run-api-401",
      ticket_id: "demo-ticket-api-401",
      trace_id: "demo-trace-api-401",
      correlation_id: "demo-correlation-api-401",
      tool_name: "log_search",
      status: "success",
      input_summary: "API returns 401 :: request_id=req_123",
      output_summary: "Read-only log search completed. Auth service shows repeated 401 responses."
    },
    created_at: new Date(Date.now() - 1000 * 60 * 8).toISOString()
  },
  {
    id: "demo-audit-run",
    tenant_id: "acme",
    actor: "system",
    action: "agent_run_started",
    target_type: "agent_run",
    target_id: "demo-run-api-401",
    metadata: {
      ticket_id: "demo-ticket-api-401",
      trace_id: "demo-trace-api-401",
      correlation_id: "demo-correlation-api-401",
      status: "running"
    },
    created_at: new Date(Date.now() - 1000 * 60 * 10).toISOString()
  }
];

export const demoAdminConfig: AdminConfig = {
  environment: "development",
  store: "memory",
  auth: {
    mode: "local_headers",
    app_env: "development",
    trusted_identity_required: false,
    trusted_identity_secret_configured: false,
    local_dev_headers_enabled: true
  },
  llm: {
    enabled: false
  },
  embeddings: {
    provider: "hashing",
    mode: "hashing_fallback",
    dimensions: 1536
  },
  tools: {
    allowed: ["log_search", "db_read", "jira_search", "github_search"],
    configured_backends: [],
    status: [
      {
        name: "log_search",
        allowed: true,
        configured: false,
        read_only: true,
        mode: "deterministic_fallback",
        backend_type: "none"
      },
      {
        name: "db_read",
        allowed: true,
        configured: false,
        read_only: true,
        mode: "deterministic_fallback",
        backend_type: "none"
      },
      {
        name: "jira_search",
        allowed: true,
        configured: false,
        read_only: true,
        mode: "deterministic_fallback",
        backend_type: "none"
      },
      {
        name: "github_search",
        allowed: true,
        configured: false,
        read_only: true,
        mode: "deterministic_fallback",
        backend_type: "none"
      }
    ]
  }
};

export const demoTrace: RunTrace = {
  run: {
    id: "demo-run-api-401",
    ticket_id: "demo-ticket-api-401",
    tenant_id: "acme",
    trace_id: "demo-trace-api-401",
    correlation_id: "demo-correlation-api-401",
    status: "awaiting_approval",
    current_node: "human_approval",
    triage: {
      issue_type: "api_auth",
      priority: "P2",
      risk_level: "medium",
      requires_human_approval: "true"
    },
    evidence: [],
    tool_call_ids: ["tool-log", "tool-db"],
    step_ids: ["step-triage", "step-retrieval", "step-tool", "step-draft", "step-verifier", "step-approval"],
    approval_id: "demo-approval-api-401",
    final_reply: null,
    verifier_report: {
      passed: true,
      findings: [],
      risk_level: "medium",
      summary: "Verifier passed: reply has citations, avoids raw secrets, and stays within tool policy."
    },
    created_at: new Date(Date.now() - 1000 * 60 * 10).toISOString(),
    updated_at: new Date(Date.now() - 1000 * 60 * 8).toISOString()
  },
  steps: [
    {
      id: "step-triage",
      run_id: "demo-run-api-401",
      name: "triage",
      status: "success",
      summary: "api_auth classified as P2 with medium risk.",
      latency_ms: 12,
      token_count: 76,
      evidence_ids: [],
      tool_call_ids: [],
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    },
    {
      id: "step-retrieval",
      run_id: "demo-run-api-401",
      name: "retrieval",
      status: "success",
      summary: "Found 3 tenant-scoped evidence chunks.",
      latency_ms: 21,
      token_count: 128,
      evidence_ids: ["chunk-auth", "chunk-historical"],
      tool_call_ids: [],
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    },
    {
      id: "step-tool",
      run_id: "demo-run-api-401",
      name: "tool_call_optional",
      status: "success",
      summary: "Executed 2 tools; denied 0 by whitelist.",
      latency_ms: 36,
      token_count: 164,
      evidence_ids: [],
      tool_call_ids: ["tool-log", "tool-db"],
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    },
    {
      id: "step-draft",
      run_id: "demo-run-api-401",
      name: "reply_draft",
      status: "success",
      summary: "Reply draft composed and ready for verifier checks.",
      latency_ms: 16,
      token_count: 88,
      evidence_ids: [],
      tool_call_ids: [],
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    },
    {
      id: "step-verifier",
      run_id: "demo-run-api-401",
      name: "verifier",
      status: "success",
      summary: "Verifier passed: reply has citations, avoids raw secrets, and stays within tool policy.",
      latency_ms: 18,
      token_count: 96,
      evidence_ids: ["chunk-auth"],
      tool_call_ids: [],
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    },
    {
      id: "step-approval",
      run_id: "demo-run-api-401",
      name: "human_approval",
      status: "blocked",
      summary: "Created send_reply approval demo-approval-api-401.",
      latency_ms: 4,
      token_count: 52,
      evidence_ids: [],
      tool_call_ids: [],
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    }
  ],
  evidence: [
    {
      chunk_id: "chunk-auth",
      document_id: "doc-auth",
      title: "API Authentication Runbook",
      uri: "kb://api/authentication-runbook",
      excerpt:
        "401 Unauthorized responses are usually caused by a missing Authorization header, expired token, invalid API key, or insufficient OAuth scope.",
      score: 0.75
    },
    {
      chunk_id: "chunk-historical",
      document_id: "doc-historical",
      title: "Historical Ticket: Expired API Token",
      uri: "ticket://hist-1042",
      excerpt:
        "A customer reported API calls returning 401 after a deployment. The root cause was an expired service account token.",
      score: 0.5
    }
  ],
  tool_calls: [
    {
      id: "tool-log",
      run_id: "demo-run-api-401",
      tool_name: "log_search",
      status: "success",
      input_summary: "API 报 401 :: 客户说 API 报 401，帮我排查并回复。",
      output_summary: "Read-only log search completed. Auth service shows repeated 401 responses.",
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    },
    {
      id: "tool-db",
      run_id: "demo-run-api-401",
      tool_name: "db_read",
      status: "success",
      input_summary: "API 报 401 :: 客户说 API 报 401，帮我排查并回复。",
      output_summary: "Read-only metadata check completed. No customer data was modified.",
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString()
    }
  ],
  approval: demoApproval
};

export const demoTickets: Ticket[] = [demoTicket];
export const demoApprovals: Approval[] = [demoApproval];
