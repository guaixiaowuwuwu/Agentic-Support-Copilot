import type { AuditLog } from "@support-copilot/shared";
import { ScrollText } from "lucide-react";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { demoAuditLogs } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function AuditPage() {
  const { locale, dict } = await getI18n();
  const userResult = await getCurrentUserResult();

  if (!userResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.audit.eyebrow}</p>
            <h1>{dict.audit.title}</h1>
          </div>
        </section>
        <ApiErrorState error={userResult.error} dict={dict} body={dict.state.auditErrorBody} />
      </main>
    );
  }

  if (!hasCapability(userResult.data, "audit")) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.audit.eyebrow}</p>
            <h1>{dict.audit.title}</h1>
          </div>
        </section>
        <StatePanel tone="permission" title={dict.state.permissionTitle} body={dict.state.workspaceDeniedBody} />
      </main>
    );
  }

  let auditLogs: AuditLog[];
  try {
    auditLogs = await serverApiGet<AuditLog[]>("/api/audit/logs", demoAuditLogs);
  } catch (error) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.audit.eyebrow}</p>
            <h1>{dict.audit.title}</h1>
          </div>
        </section>
        <ApiErrorState error={error} dict={dict} body={dict.state.auditErrorBody} />
      </main>
    );
  }

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{dict.audit.eyebrow}</p>
          <h1>{dict.audit.title}</h1>
        </div>
        <div className="queue-count">
          <ScrollText size={18} />
          <strong>{auditLogs.length}</strong>
        </div>
      </section>

      <section className="surface">
        {auditLogs.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{dict.audit.actor}</th>
                  <th>{dict.audit.action}</th>
                  <th>{dict.audit.target}</th>
                  <th>{dict.audit.created}</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((audit) => (
                  <tr key={audit.id}>
                    <td>
                      <strong>{audit.actor}</strong>
                      <span className="muted-line">{audit.tenant_id}</span>
                    </td>
                    <td>{audit.action}</td>
                    <td>
                      {audit.target_type}
                      <span className="muted-line">{compactId(audit.target_id)}</span>
                    </td>
                    <td>{formatDate(audit.created_at, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <StatePanel tone="empty" title={dict.state.auditEmptyTitle} body={dict.state.auditEmptyBody} compact />
        )}
      </section>
    </main>
  );
}
