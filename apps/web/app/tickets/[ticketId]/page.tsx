import type { RunTrace, Ticket } from "@support-copilot/shared";
import { GitBranch, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { ApprovalButtons, StartRunButton } from "@/components/run-actions";
import { StatusBadge } from "@/components/status-badge";
import { demoTicket, demoTrace } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type TraceResult = { ok: true; trace: RunTrace } | { ok: false; error: unknown } | null;

export default async function TicketPage({ params }: { params: Promise<{ ticketId: string }> }) {
  const { locale, dict } = await getI18n();
  const { ticketId } = await params;
  const userResult = await getCurrentUserResult();

  if (!userResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.ticketDetail.ticket}</p>
            <h1>{compactId(ticketId)}</h1>
          </div>
        </section>
        <ApiErrorState error={userResult.error} dict={dict} body={dict.state.ticketErrorBody} />
      </main>
    );
  }

  const user = userResult.data;
  if (!hasCapability(user, "tickets")) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.ticketDetail.ticket}</p>
            <h1>{compactId(ticketId)}</h1>
          </div>
        </section>
        <StatePanel tone="permission" title={dict.state.permissionTitle} body={dict.state.workspaceDeniedBody} />
      </main>
    );
  }

  let ticket: Ticket;

  try {
    ticket = await serverApiGet<Ticket>(`/api/tickets/${ticketId}`, demoTicket);
  } catch (error) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.ticketDetail.ticket}</p>
            <h1>{compactId(ticketId)}</h1>
          </div>
        </section>
        <ApiErrorState error={error} dict={dict} body={dict.state.ticketErrorBody} />
      </main>
    );
  }

  const latestRunId = ticket.run_ids.at(-1);
  let traceResult: TraceResult = null;

  if (latestRunId) {
    try {
      traceResult = { ok: true, trace: await serverApiGet<RunTrace>(`/api/runs/${latestRunId}/trace`, demoTrace) };
    } catch (error) {
      traceResult = { ok: false, error };
    }
  }

  const trace = traceResult?.ok ? traceResult.trace : null;
  const traceError = traceResult && !traceResult.ok ? traceResult.error : null;

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{ticket.customer_name}</p>
          <h1>{ticket.subject}</h1>
        </div>
        {hasCapability(user, "start_run") ? <StartRunButton ticketId={ticket.id} locale={locale} /> : null}
      </section>

      <section className="detail-grid">
        <div className="surface">
          <div className="surface-header">
            <h2>{dict.ticketDetail.ticket}</h2>
            <StatusBadge value={ticket.status} locale={locale} />
          </div>
          <dl className="kv">
            <div>
              <dt>{dict.ticketDetail.tenant}</dt>
              <dd>{ticket.tenant_id}</dd>
            </div>
            <div>
              <dt>{dict.ticketDetail.channel}</dt>
              <dd>{ticket.channel}</dd>
            </div>
            <div>
              <dt>{dict.ticketDetail.priority}</dt>
              <dd>{ticket.priority ?? "-"}</dd>
            </div>
            <div>
              <dt>{dict.ticketDetail.type}</dt>
              <dd>{ticket.issue_type ?? "-"}</dd>
            </div>
            <div>
              <dt>{dict.ticketDetail.updated}</dt>
              <dd>{formatDate(ticket.updated_at, locale)}</dd>
            </div>
          </dl>
          <p className="ticket-body">{ticket.description}</p>
        </div>

        <div className="surface">
          <div className="surface-header">
            <h2>{dict.ticketDetail.currentRun}</h2>
            {trace ? <StatusBadge value={trace.run.status} locale={locale} /> : <StatusBadge value="open" locale={locale} />}
          </div>
          {traceError ? (
            <ApiErrorState error={traceError} dict={dict} body={dict.state.runErrorBody} compact />
          ) : trace ? (
            <>
              <dl className="kv">
                <div>
                  <dt>{dict.common.run}</dt>
                  <dd>{compactId(trace.run.id)}</dd>
                </div>
                <div>
                  <dt>{dict.ticketDetail.node}</dt>
                  <dd>{trace.run.current_node}</dd>
                </div>
                <div>
                  <dt>{dict.ticketDetail.risk}</dt>
                  <dd>{trace.run.triage.risk_level ?? "-"}</dd>
                </div>
              </dl>
              <div className="action-row">
                <Link className="icon-button" href={`/runs/${trace.run.id}/trace`} title={dict.common.openRunTrace}>
                  <GitBranch size={17} />
                  <span>{dict.common.trace}</span>
                </Link>
                {trace.approval?.status === "pending" && hasCapability(user, "approvals") ? (
                  <Link className="icon-button" href="/approvals" title={dict.common.openApprovalQueue}>
                    <ShieldCheck size={17} />
                    <span>{dict.common.review}</span>
                  </Link>
                ) : null}
              </div>
            </>
          ) : (
            <StatePanel tone="empty" title={dict.ticketDetail.noRun} body={dict.state.noRunBody} compact />
          )}
        </div>
      </section>

      {trace?.approval ? (
        <section className="surface">
          <div className="surface-header">
            <h2>{dict.common.approval}</h2>
            <StatusBadge value={trace.approval.status} locale={locale} />
          </div>
          <pre className="reply-preview">{trace.approval.proposed_reply}</pre>
          {trace.approval.status === "pending" && hasCapability(user, "approval_decision") ? (
            <ApprovalButtons approvalId={trace.approval.id} locale={locale} />
          ) : null}
        </section>
      ) : null}

      {ticket.final_reply ? (
        <section className="surface">
          <div className="surface-header">
            <h2>{dict.common.finalReply}</h2>
            <StatusBadge value="replied" locale={locale} />
          </div>
          <pre className="reply-preview">{ticket.final_reply}</pre>
        </section>
      ) : null}
    </main>
  );
}
