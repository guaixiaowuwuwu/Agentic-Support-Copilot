import type { RunTrace } from "@support-copilot/shared";
import { Database, FileSearch, GitBranch, Timer } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { apiGet, demoTrace } from "@/lib/api";
import { compactId } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";

export const dynamic = "force-dynamic";

export default async function RunTracePage({ params }: { params: Promise<{ runId: string }> }) {
  const { locale, dict } = await getI18n();
  const { runId } = await params;
  const trace = await apiGet<RunTrace>(`/api/runs/${runId}/trace`, demoTrace);
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
          </div>

          <div className="surface">
            <div className="surface-header">
              <h2>{dict.trace.evidence}</h2>
            </div>
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
          </div>
        </div>
      </section>
    </main>
  );
}
