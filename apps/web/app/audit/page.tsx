import type { AuditLog } from "@support-copilot/shared";
import Link from "next/link";
import { ExternalLink, RotateCcw, ScrollText, Search } from "lucide-react";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { demoAuditLogs } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type AuditSearchParams = Record<string, string | string[] | undefined>;

type AuditPageProps = {
  searchParams?: Promise<AuditSearchParams>;
};

function firstParam(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return value[0] ?? "";
  }
  return value ?? "";
}

function auditQuery(params: AuditSearchParams): string {
  const query = new URLSearchParams();
  for (const key of ["tenant_id", "actor", "action", "target", "start_time", "end_time"]) {
    const value = firstParam(params[key]);
    if (value) {
      query.set(key, value);
    }
  }
  query.set("limit", firstParam(params.limit) || "200");
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

function metadataValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function metadataEntries(audit: AuditLog): Array<[string, string]> {
  return Object.entries(audit.metadata)
    .filter(([key]) => key !== "trace_id" && key !== "correlation_id")
    .map(([key, value]) => [key, metadataValue(value)] as [string, string])
    .filter(([, value]) => value !== "-")
    .slice(0, 8);
}

function runIdForAudit(audit: AuditLog): string | null {
  const runId = audit.metadata.run_id;
  if (typeof runId === "string" && runId) {
    return runId;
  }
  if (audit.target_type === "agent_run") {
    return audit.target_id;
  }
  return null;
}

export default async function AuditPage({ searchParams }: AuditPageProps) {
  const { locale, dict } = await getI18n();
  const params = searchParams ? await searchParams : {};
  const userResult = await getCurrentUserResult();
  const filters = {
    tenant_id: firstParam(params.tenant_id),
    actor: firstParam(params.actor),
    action: firstParam(params.action),
    target: firstParam(params.target),
    start_time: firstParam(params.start_time),
    end_time: firstParam(params.end_time)
  };

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
    auditLogs = await serverApiGet<AuditLog[]>(`/api/audit-logs${auditQuery(params)}`, demoAuditLogs);
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
          <span>{dict.audit.count}</span>
          <strong>{auditLogs.length}</strong>
        </div>
      </section>

      <form className="surface audit-filters" action="/audit">
        <div className="surface-header">
          <h2>{dict.audit.filters}</h2>
        </div>
        <div className="audit-filter-grid">
          <label>
            {dict.audit.tenant}
            <input name="tenant_id" defaultValue={filters.tenant_id} placeholder={dict.audit.tenantPlaceholder} />
          </label>
          <label>
            {dict.audit.actor}
            <input name="actor" defaultValue={filters.actor} placeholder={dict.audit.actorPlaceholder} />
          </label>
          <label>
            {dict.audit.action}
            <input name="action" defaultValue={filters.action} placeholder={dict.audit.actionPlaceholder} />
          </label>
          <label>
            {dict.audit.target}
            <input name="target" defaultValue={filters.target} placeholder={dict.audit.targetPlaceholder} />
          </label>
          <label>
            {dict.audit.start}
            <input name="start_time" type="datetime-local" defaultValue={filters.start_time} />
          </label>
          <label>
            {dict.audit.end}
            <input name="end_time" type="datetime-local" defaultValue={filters.end_time} />
          </label>
        </div>
        <div className="form-footer">
          <Link className="icon-button" href="/audit" title={dict.audit.reset}>
            <RotateCcw size={16} />
            <span>{dict.audit.reset}</span>
          </Link>
          <button className="button button-primary" type="submit">
            <Search size={16} />
            {dict.audit.search}
          </button>
        </div>
      </form>

      <section className="surface">
        {auditLogs.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{dict.audit.actor}</th>
                  <th>{dict.audit.action}</th>
                  <th>{dict.audit.target}</th>
                  <th>{dict.audit.metadata}</th>
                  <th>{dict.audit.created}</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((audit) => {
                  const runId = runIdForAudit(audit);
                  const traceId = typeof audit.metadata.trace_id === "string" ? audit.metadata.trace_id : null;
                  const correlationId =
                    typeof audit.metadata.correlation_id === "string" ? audit.metadata.correlation_id : null;
                  return (
                    <tr key={audit.id}>
                      <td>
                        <strong>{audit.actor}</strong>
                        <span className="muted-line">{audit.tenant_id}</span>
                      </td>
                      <td>{audit.action}</td>
                      <td>
                        {audit.target_type}
                        <span className="muted-line">{compactId(audit.target_id)}</span>
                        {runId ? (
                          <Link className="table-inline-link" href={`/runs/${runId}/trace`}>
                            <ExternalLink size={13} />
                            {dict.audit.runTrace}
                          </Link>
                        ) : null}
                      </td>
                      <td className="audit-metadata">
                        {traceId ? (
                          <span>
                            {dict.audit.traceId}: {compactId(traceId)}
                          </span>
                        ) : null}
                        {correlationId ? (
                          <span>
                            {dict.audit.correlationId}: {compactId(correlationId)}
                          </span>
                        ) : null}
                        {metadataEntries(audit).map(([key, value]) => (
                          <span key={key}>
                            {key}: {value}
                          </span>
                        ))}
                      </td>
                      <td>{formatDate(audit.created_at, locale)}</td>
                    </tr>
                  );
                })}
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
