import type { Approval } from "@support-copilot/shared";
import { ShieldCheck } from "lucide-react";
import Link from "next/link";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { ApprovalButtons } from "@/components/run-actions";
import { StatusBadge } from "@/components/status-badge";
import { demoApprovals } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage() {
  const { locale, dict } = await getI18n();
  const userResult = await getCurrentUserResult();

  if (!userResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.approvals.eyebrow}</p>
            <h1>{dict.approvals.title}</h1>
          </div>
        </section>
        <ApiErrorState error={userResult.error} dict={dict} body={dict.state.approvalsErrorBody} />
      </main>
    );
  }

  if (!hasCapability(userResult.data, "approvals")) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.approvals.eyebrow}</p>
            <h1>{dict.approvals.title}</h1>
          </div>
        </section>
        <StatePanel tone="permission" title={dict.state.permissionTitle} body={dict.state.workspaceDeniedBody} />
      </main>
    );
  }

  let approvals: Approval[];

  try {
    approvals = await serverApiGet<Approval[]>("/api/approvals?status=pending", demoApprovals);
  } catch (error) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.approvals.eyebrow}</p>
            <h1>{dict.approvals.title}</h1>
          </div>
        </section>
        <ApiErrorState error={error} dict={dict} body={dict.state.approvalsErrorBody} />
      </main>
    );
  }

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{dict.approvals.eyebrow}</p>
          <h1>{dict.approvals.title}</h1>
        </div>
        <div className="queue-count">
          <ShieldCheck size={18} />
          <strong>{approvals.length}</strong>
        </div>
      </section>

      <section className="approval-list">
        {approvals.length ? (
          approvals.map((approval) => (
            <article className="surface" key={approval.id}>
              <div className="surface-header">
                <div>
                  <h2>{approval.action_type}</h2>
                  <span className="muted-line">
                    {compactId(approval.id)} · {formatDate(approval.created_at, locale)}
                  </span>
                </div>
                <StatusBadge value={approval.risk_level} locale={locale} />
              </div>
              <pre className="reply-preview">{approval.proposed_reply}</pre>
              <div className="approval-footer">
                <Link className="icon-button" href={`/runs/${approval.run_id}/trace`} title={dict.common.openRunTrace}>
                  <ShieldCheck size={17} />
                  <span>{dict.common.trace}</span>
                </Link>
                <ApprovalButtons approvalId={approval.id} locale={locale} />
              </div>
            </article>
          ))
        ) : (
          <StatePanel tone="empty" title={dict.state.approvalsEmptyTitle} body={dict.state.approvalsEmptyBody} />
        )}
      </section>
    </main>
  );
}
