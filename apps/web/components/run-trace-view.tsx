"use client";

import type { AgentRun, RunTrace } from "@support-copilot/shared";
import { Database, FileSearch, GitBranch, RefreshCw, Timer, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StatePanel } from "@/components/page-state";
import { StatusBadge } from "@/components/status-badge";
import { apiGet, apiPost, demoTrace } from "@/lib/api";
import { compactId } from "@/lib/format";
import { dictionaries, normalizeLocale, type Locale } from "@/lib/i18n";

const activeRunStatuses = new Set(["queued", "running"]);

export function RunTraceView({
  initialTrace,
  locale,
  canManageRun = false
}: {
  initialTrace: RunTrace;
  locale?: Locale;
  canManageRun?: boolean;
}) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale];
  const [trace, setTrace] = useState(initialTrace);
  const [actionError, setActionError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    setTrace(initialTrace);
  }, [initialTrace]);

  useEffect(() => {
    if (!activeRunStatuses.has(trace.run.status)) {
      return;
    }
    const interval = window.setInterval(async () => {
      try {
        const nextTrace = await apiGet<RunTrace>(`/api/runs/${trace.run.id}/trace`, demoTrace);
        setTrace(nextTrace);
      } catch {
        window.clearInterval(interval);
      }
    }, 1500);
    return () => window.clearInterval(interval);
  }, [trace.run.id, trace.run.status]);

  const totalTokens = trace.steps.reduce((sum, step) => sum + step.token_count, 0);
  const totalLatency = trace.steps.reduce((sum, step) => sum + step.latency_ms, 0);
  const verifierStatus = trace.run.verifier_report.summary
    ? trace.run.verifier_report.passed
      ? "success"
      : "blocked"
    : "pending";

  async function refreshTrace() {
    const nextTrace = await apiGet<RunTrace>(`/api/runs/${trace.run.id}/trace`, demoTrace);
    setTrace(nextTrace);
  }

  async function cancelRun() {
    setActionError("");
    setIsBusy(true);
    try {
      const run = await apiPost<AgentRun>(`/api/runs/${trace.run.id}/cancel`);
      setTrace((current) => ({ ...current, run }));
      await refreshTrace();
      router.refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : dict.trace.cancelFailed);
    } finally {
      setIsBusy(false);
    }
  }

  async function retryRun() {
    setActionError("");
    setIsBusy(true);
    try {
      const run = await apiPost<AgentRun>(`/api/runs/${trace.run.id}/retry`);
      router.push(`/runs/${run.id}/trace`);
      router.refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : dict.trace.retryFailed);
      setIsBusy(false);
    }
  }

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">
            {dict.common.run} {compactId(trace.run.id)}
          </p>
          <h1>{dict.trace.title}</h1>
          <div className="id-row">
            <span>
              {dict.trace.traceId}: {compactId(trace.run.trace_id)}
            </span>
            <span>
              {dict.trace.correlationId}: {compactId(trace.run.correlation_id)}
            </span>
          </div>
        </div>
        <div className="action-stack">
          <div className="title-actions">
            {canManageRun && trace.run.status === "failed" ? (
              <button className="icon-button" onClick={retryRun} disabled={isBusy} title={dict.trace.retryRun}>
                <RefreshCw size={17} />
                <span>{dict.trace.retryRun}</span>
              </button>
            ) : null}
            {canManageRun && activeRunStatuses.has(trace.run.status) ? (
              <button className="icon-button reject" onClick={cancelRun} disabled={isBusy} title={dict.trace.cancelRun}>
                <XCircle size={17} />
                <span>{dict.trace.cancelRun}</span>
              </button>
            ) : null}
            <StatusBadge value={trace.run.status} locale={activeLocale} />
          </div>
          {actionError ? <span className="form-error" role="alert">{actionError}</span> : null}
        </div>
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
                      <StatusBadge value={step.status} locale={activeLocale} />
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
              <StatusBadge value={verifierStatus} locale={activeLocale} />
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
                      <StatusBadge value={call.status} locale={activeLocale} />
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
