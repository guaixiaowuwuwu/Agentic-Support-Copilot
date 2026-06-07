export type TicketStatus =
  | "open"
  | "running"
  | "triaged"
  | "awaiting_approval"
  | "replied"
  | "rejected";

export interface Ticket {
  id: string;
  tenant_id: string;
  customer_name: string;
  channel: string;
  subject: string;
  description: string;
  status: TicketStatus | string;
  priority?: string | null;
  issue_type?: string | null;
  final_reply?: string | null;
  run_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  chunk_id: string;
  document_id: string;
  title: string;
  uri: string;
  excerpt: string;
  score: number;
}

export interface ToolCall {
  id: string;
  run_id: string;
  tool_name: string;
  status: string;
  input_summary: string;
  output_summary: string;
  started_at: string;
  ended_at: string;
}

export interface AgentStep {
  id: string;
  run_id: string;
  name: string;
  status: string;
  summary: string;
  latency_ms: number;
  token_count: number;
  evidence_ids: string[];
  tool_call_ids: string[];
  started_at: string;
  ended_at: string;
}

export interface Approval {
  id: string;
  run_id: string;
  ticket_id: string;
  action_type: string;
  proposed_reply: string;
  risk_level: string;
  reason: string;
  status: string;
  decided_by?: string | null;
  decision_note?: string | null;
  created_at: string;
  decided_at?: string | null;
}

export interface AgentRun {
  id: string;
  ticket_id: string;
  tenant_id: string;
  status: string;
  current_node: string;
  triage: Record<string, string>;
  evidence: Evidence[];
  tool_call_ids: string[];
  step_ids: string[];
  approval_id?: string | null;
  final_reply?: string | null;
  verifier_report: {
    passed?: boolean;
    findings?: string[];
    risk_level?: string;
    summary?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface RunTrace {
  run: AgentRun;
  steps: AgentStep[];
  evidence: Evidence[];
  tool_calls: ToolCall[];
  approval?: Approval | null;
}

export interface UserContext {
  email: string;
  tenant_id: string;
  tenant_ids: string[];
  roles: string[];
}
