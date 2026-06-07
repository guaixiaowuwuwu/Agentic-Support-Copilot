import type { RunTrace, Ticket } from "@support-copilot/shared";
import { GitBranch, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { ApprovalButtons, StartRunButton } from "@/components/run-actions";
import { StatusBadge } from "@/components/status-badge";
import { apiGet, demoTicket, demoTrace } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";

export const dynamic = "force-dynamic";

export default async function TicketPage({ params }: { params: Promise<{ ticketId: string }> }) {
  const { locale, dict } = await getI18n();
  const { ticketId } = await params;
  const ticket = await apiGet<Ticket>(`/api/tickets/${ticketId}`, demoTicket);
  const latestRunId = ticket.run_ids.at(-1);
  const trace = latestRunId
    ? await apiGet<RunTrace>(`/api/runs/${latestRunId}/trace`, demoTrace)
    : null;

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{ticket.customer_name}</p>
          <h1>{ticket.subject}</h1>
        </div>
        <StartRunButton ticketId={ticket.id} locale={locale} />
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
          {trace ? (
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
                {trace.approval?.status === "pending" ? (
                  <Link className="icon-button" href="/approvals" title={dict.common.openApprovalQueue}>
                    <ShieldCheck size={17} />
                    <span>{dict.common.review}</span>
                  </Link>
                ) : null}
              </div>
            </>
          ) : (
            <p className="empty-state">{dict.ticketDetail.noRun}</p>
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
          {trace.approval.status === "pending" ? <ApprovalButtons approvalId={trace.approval.id} locale={locale} /> : null}
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
