import type { UserContext, UserRole } from "@support-copilot/shared";

export type LoginRole = Extract<UserRole, "support_agent" | "approver" | "knowledge_admin" | "admin">;

export const loginRoleCookieName = "support-copilot-login-role";
export const loginRoles = ["support_agent", "approver", "knowledge_admin", "admin"] as const satisfies readonly LoginRole[];

const roleEmails: Record<LoginRole, string> = {
  support_agent: "support.agent@acme.example",
  approver: "approver@acme.example",
  knowledge_admin: "knowledge.admin@acme.example",
  admin: "admin@acme.example"
};

function splitCsv(value: string | undefined, fallback: string[]): string[] {
  const items = value
    ?.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items?.length ? items : fallback;
}

export function normalizeLoginRole(value?: string | null): LoginRole | null {
  if (!value) {
    return null;
  }
  return loginRoles.includes(value as LoginRole) ? (value as LoginRole) : null;
}

export function loginRoleFromCookieHeader(cookieHeader?: string | null): LoginRole | null {
  if (!cookieHeader) {
    return null;
  }
  const cookies = cookieHeader.split(";").map((item) => item.trim());
  const rawValue = cookies
    .find((item) => item.startsWith(`${loginRoleCookieName}=`))
    ?.slice(loginRoleCookieName.length + 1);
  return normalizeLoginRole(rawValue ? decodeURIComponent(rawValue) : null);
}

export function getBrowserLoginRole(): LoginRole | null {
  if (typeof document === "undefined") {
    return null;
  }
  return loginRoleFromCookieHeader(document.cookie);
}

export function userContextForLoginRole(role: LoginRole): UserContext {
  const tenantId = process.env.NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_ID ?? "acme";
  return {
    email: roleEmails[role],
    tenant_id: tenantId,
    tenant_ids: splitCsv(process.env.NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_IDS, [tenantId]),
    roles: [role]
  };
}

export function defaultPathForLoginRole(role: LoginRole): string {
  if (role === "approver") {
    return "/approvals";
  }
  if (role === "knowledge_admin") {
    return "/knowledge";
  }
  if (role === "admin") {
    return "/audit";
  }
  return "/";
}

export function identityHeadersForUser(user: UserContext | null | undefined): Record<string, string> {
  if (!user) {
    return {};
  }
  return {
    "X-User-Email": user.email,
    "X-Tenant-Id": user.tenant_id,
    "X-Tenant-Ids": user.tenant_ids.join(","),
    "X-User-Roles": user.roles.join(",")
  };
}
