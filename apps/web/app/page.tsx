import type { Approval, Ticket } from "@support-copilot/shared";
import { Clock3, Gauge, ShieldCheck, TicketCheck } from "lucide-react";
import Link from "next/link";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { StatusBadge } from "@/components/status-badge";
import { TicketCreator } from "@/components/ticket-creator";
import { apiGet, demoApprovals, demoTickets } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";

export const dynamic = "force-dynamic";

type LoadResult<T> = { ok: true; data: T } | { ok: false; error: unknown };

async function loadResult<T>(promise: Promise<T>): Promise<LoadResult<T>> {
  try {
    return { ok: true, data: await promise };
  } catch (error) {
    return { ok: false, error };
  }
}

export default async function DashboardPage() {
  const { locale, dict } = await getI18n();
  const [ticketsResult, approvalsResult] = await Promise.all([
    loadResult(apiGet<Ticket[]>("/api/tickets", demoTickets)),
    loadResult(apiGet<Approval[]>("/api/approvals?status=pending", demoApprovals))
  ]);

  if (!ticketsResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.dashboard.eyebrow}</p>
            <h1>{dict.dashboard.title}</h1>
          </div>
        </section>
        <ApiErrorState error={ticketsResult.error} dict={dict} body={dict.state.dashboardErrorBody} />
      </main>
    );
  }

  const tickets = ticketsResult.data;
  const approvals = approvalsResult.ok ? approvalsResult.data : [];
  const awaiting = tickets.filter((ticket) => ticket.status === "awaiting_approval").length;
  const replied = tickets.filter((ticket) => ticket.status === "replied").length;

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{dict.dashboard.eyebrow}</p>
          <h1>{dict.dashboard.title}</h1>
        </div>
        <div className="title-actions">
          <Link className="icon-button" href="/approvals" title={dict.dashboard.openApprovals}>
            <ShieldCheck size={17} />
            <span>{dict.nav.approvals}</span>
          </Link>
        </div>
      </section>

      <section className="metrics-grid" aria-label={dict.dashboard.metricsLabel}>
        <div className="metric">
          <TicketCheck size={20} />
          <span>{dict.dashboard.totalTickets}</span>
          <strong>{tickets.length}</strong>
        </div>
        <div className="metric">
          <Clock3 size={20} />
          <span>{dict.dashboard.awaitingApproval}</span>
          <strong>{awaiting}</strong>
        </div>
        <div className="metric">
          <ShieldCheck size={20} />
          <span>{dict.dashboard.pendingApprovals}</span>
          <strong>{approvalsResult.ok ? approvals.length : "-"}</strong>
        </div>
        <div className="metric">
          <Gauge size={20} />
          <span>{dict.dashboard.replied}</span>
          <strong>{replied}</strong>
        </div>
      </section>

      {!approvalsResult.ok ? (
        <ApiErrorState
          error={approvalsResult.error}
          dict={dict}
          body={dict.state.dashboardApprovalsErrorBody}
        />
      ) : null}

      <section className="work-grid">
        <div className="surface">
          <div className="surface-header">
            <h2>{dict.dashboard.newTicket}</h2>
          </div>
          <TicketCreator key={locale} locale={locale} />
        </div>

        <div className="surface">
          <div className="surface-header">
            <h2>{dict.dashboard.queue}</h2>
          </div>
          {tickets.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{dict.dashboard.tableSubject}</th>
                    <th>{dict.dashboard.tableStatus}</th>
                    <th>{dict.dashboard.tablePriority}</th>
                    <th>{dict.dashboard.tableUpdated}</th>
                  </tr>
                </thead>
                <tbody>
                  {tickets.map((ticket) => (
                    <tr key={ticket.id}>
                      <td>
                        <Link href={`/tickets/${ticket.id}`} className="table-link">
                          {ticket.subject}
                        </Link>
                        <span className="muted-line">{ticket.customer_name}</span>
                      </td>
                      <td>
                        <StatusBadge value={ticket.status} locale={locale} />
                      </td>
                      <td>{ticket.priority ?? "-"}</td>
                      <td>{formatDate(ticket.updated_at, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <StatePanel
              tone="empty"
              title={dict.state.ticketsEmptyTitle}
              body={dict.state.ticketsEmptyBody}
              compact
            />
          )}
        </div>
      </section>
    </main>
  );
}
