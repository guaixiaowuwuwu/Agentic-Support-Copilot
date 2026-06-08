import type { RunTrace } from "@support-copilot/shared";
import { Database, FileSearch, GitBranch, Timer } from "lucide-react";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { StatusBadge } from "@/components/status-badge";
import { demoTrace } from "@/lib/api";
import { compactId } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

export default async function RunTracePage({ params }: { params: Promise<{ runId: string }> }) {
  const { locale, dict } = await getI18n();
  const { runId } = await params;
  const userResult = await getCurrentUserResult();

  if (!userResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">
              {dict.common.run} {compactId(runId)}
            </p>
            <h1>{dict.trace.title}</h1>
          </div>
        </section>
        <ApiErrorState error={userResult.error} dict={dict} body={dict.state.traceErrorBody} />
      </main>
    );
  }

  if (!hasCapability(userResult.data, "trace")) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">
              {dict.common.run} {compactId(runId)}
            </p>
            <h1>{dict.trace.title}</h1>
          </div>
        </section>
        <StatePanel tone="permission" title={dict.state.permissionTitle} body={dict.state.workspaceDeniedBody} />
      </main>
    );
  }

  let trace: RunTrace;

  try {
    trace = await serverApiGet<RunTrace>(`/api/runs/${runId}/trace`, demoTrace);
  } catch (error) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">
              {dict.common.run} {compactId(runId)}
            </p>
            <h1>{dict.trace.title}</h1>
          </div>
        </section>
        <ApiErrorState error={error} dict={dict} body={dict.state.traceErrorBody} />
      </main>
    );
  }

  const totalTokens = trace.steps.reduce((sum, step) => sum + step.token_count, 0);
  const totalLatency = trace.steps.reduce((sum, step) => sum + step.latency_ms, 0);

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">
            {dict.common.run} {compactId(trace.run.id)}
          </p>
          <h1>{dict.trace.title}</h1>
        </div>
        <StatusBadge value={trace.run.status} locale={locale} />
      </section>

      <section className="metrics-grid" aria-label={dict.trace.metricsLabel}>
        <div className="metric">
          <GitBranch size={20} />
          <span>{dict.trace.currentNode}</span>
          <strong>{trace.run.current_node}</strong>
        </div>
        <div className="metric">
          <Timer size={20} />
          <span>{dict.trace.latency}</span>
          <strong>{totalLatency} ms</strong>
        </div>
        <div className="metric">
          <FileSearch size={20} />
          <span>{dict.trace.evidence}</span>
          <strong>{trace.evidence.length}</strong>
        </div>
        <div className="metric">
          <Database size={20} />
          <span>{dict.trace.tokens}</span>
          <strong>{totalTokens}</strong>
        </div>
      </section>

      <section className="trace-grid">
        <div className="surface">
          <div className="surface-header">
            <h2>{dict.trace.agentSteps}</h2>
          </div>
          {trace.steps.length ? (
            <ol className="timeline">
              {trace.steps.map((step) => (
                <li key={step.id}>
                  <div className="timeline-dot" />
                  <div className="timeline-content">
                    <div className="timeline-head">
                      <strong>{step.name}</strong>
                      <StatusBadge value={step.status} locale={locale} />
                    </div>
                    <p>{step.summary}</p>
                    <div className="timeline-meta">
                      <span>{step.latency_ms} ms</span>
                      <span>{step.token_count} tokens</span>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <StatePanel tone="empty" title={dict.state.stepsEmptyTitle} body={dict.state.stepsEmptyBody} compact />
          )}
        </div>

        <div className="stack">
          <div className="surface">
            <div className="surface-header">
              <h2>{dict.trace.verifier}</h2>
              <StatusBadge value={trace.run.verifier_report.passed ? "success" : "blocked"} locale={locale} />
            </div>
            <p className="body-copy">{trace.run.verifier_report.summary ?? "-"}</p>
          </div>

          <div className="surface">
            <div className="surface-header">
              <h2>{dict.trace.toolCalls}</h2>
            </div>
            {trace.tool_calls.length ? (
              <div className="list">
                {trace.tool_calls.map((call) => (
                  <article className="list-item" key={call.id}>
                    <div className="list-head">
                      <strong>{call.tool_name}</strong>
                      <StatusBadge value={call.status} locale={locale} />
                    </div>
                    <p>{call.output_summary}</p>
                  </article>
                ))}
              </div>
            ) : (
              <StatePanel tone="empty" title={dict.state.toolsEmptyTitle} body={dict.state.toolsEmptyBody} compact />
            )}
          </div>

          <div className="surface">
            <div className="surface-header">
              <h2>{dict.trace.evidence}</h2>
            </div>
            {trace.evidence.length ? (
              <div className="list">
                {trace.evidence.map((item) => (
                  <article className="list-item" key={item.chunk_id}>
                    <div className="list-head">
                      <strong>{item.title}</strong>
                      <span className="score">{item.score}</span>
                    </div>
                    <p>{item.excerpt}</p>
                    <span className="muted-line">{item.uri}</span>
                  </article>
                ))}
              </div>
            ) : (
              <StatePanel tone="empty" title={dict.state.evidenceEmptyTitle} body={dict.state.evidenceEmptyBody} compact />
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
