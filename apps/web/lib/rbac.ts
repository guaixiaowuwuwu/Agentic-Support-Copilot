import type { UserContext } from "@support-copilot/shared";
import type { Dictionary } from "@/lib/i18n";

export type WorkspaceId = "tickets" | "approvals" | "knowledge" | "audit" | "admin";
export type Capability =
  | WorkspaceId
  | "trace"
  | "start_run"
  | "approval_decision"
  | "knowledge_write";

const capabilityRoles: Record<Capability, string[]> = {
  tickets: ["support_agent", "admin"],
  approvals: ["approver", "admin"],
  knowledge: ["knowledge_admin", "admin"],
  audit: ["admin"],
  admin: ["admin"],
  trace: ["support_agent", "approver", "admin"],
  start_run: ["support_agent", "admin"],
  approval_decision: ["approver", "admin"],
  knowledge_write: ["knowledge_admin", "admin"]
};

const defaultWorkspaceOrder: WorkspaceId[] = ["tickets", "approvals", "knowledge", "audit", "admin"];

export function hasCapability(user: UserContext | null | undefined, capability: Capability): boolean {
  if (!user) {
    return false;
  }
  return user.roles.some((role) => capabilityRoles[capability].includes(role));
}

export function defaultPathForUser(user: UserContext): string {
  const workspace = defaultWorkspaceOrder.find((item) => hasCapability(user, item));
  if (workspace === "tickets") {
    return "/";
  }
  return workspace ? `/${workspace}` : "/";
}

export function navigationForUser(user: UserContext, dict: Dictionary): Array<{ id: WorkspaceId; label: string; href: string }> {
  return defaultWorkspaceOrder
    .filter((workspace) => hasCapability(user, workspace))
    .map((workspace) => ({
      id: workspace,
      label: dict.nav[workspace],
      href: workspace === "tickets" ? "/" : `/${workspace}`
    }));
}
