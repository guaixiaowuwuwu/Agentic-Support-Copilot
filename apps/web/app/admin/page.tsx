import type { AdminConfig, ToolConfigStatus } from "@support-copilot/shared";
import { KeyRound, Settings, ShieldCheck, Wrench } from "lucide-react";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { demoAdminConfig } from "@/lib/api";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

function modeBadgeClass(mode: string) {
  if (mode === "configured") {
    return "badge-green";
  }
  if (mode === "blocked_write_tool") {
    return "badge-red";
  }
  if (mode === "disabled") {
    return "badge-neutral";
  }
  return "badge-amber";
}

function fallbackToolStatus(config: AdminConfig): ToolConfigStatus[] {
  const configured = new Set(config.tools.configured_backends);
  return config.tools.allowed.map((tool) => ({
    name: tool,
    allowed: true,
    configured: configured.has(tool),
    read_only: true,
    mode: configured.has(tool) ? "configured" : "deterministic_fallback",
    backend_type: configured.has(tool) ? tool : "none"
  }));
}

export default async function AdminPage() {
  const { dict } = await getI18n();
  const userResult = await getCurrentUserResult();

  if (!userResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.admin.eyebrow}</p>
            <h1>{dict.admin.title}</h1>
          </div>
        </section>
        <ApiErrorState error={userResult.error} dict={dict} body={dict.state.adminErrorBody} />
      </main>
    );
  }

  if (!hasCapability(userResult.data, "admin")) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.admin.eyebrow}</p>
            <h1>{dict.admin.title}</h1>
          </div>
        </section>
        <StatePanel tone="permission" title={dict.state.permissionTitle} body={dict.state.workspaceDeniedBody} />
      </main>
    );
  }

  let config: AdminConfig;
  try {
    config = await serverApiGet<AdminConfig>("/api/admin/config", demoAdminConfig);
  } catch (error) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.admin.eyebrow}</p>
            <h1>{dict.admin.title}</h1>
          </div>
        </section>
        <ApiErrorState error={error} dict={dict} body={dict.state.adminErrorBody} />
      </main>
    );
  }
  const toolStatuses = config.tools.status?.length ? config.tools.status : fallbackToolStatus(config);
  const modeLabels: Record<string, string> = {
    configured: dict.admin.modeConfigured,
    deterministic_fallback: dict.admin.modeFallback,
    blocked_write_tool: dict.admin.modeBlocked,
    disabled: dict.admin.modeDisabled
  };

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{dict.admin.eyebrow}</p>
          <h1>{dict.admin.title}</h1>
        </div>
      </section>

      <section className="metrics-grid" aria-label={dict.admin.title}>
        <div className="metric">
          <Settings size={20} />
          <span>{dict.admin.environment}</span>
          <strong>{config.environment}</strong>
        </div>
        <div className="metric">
          <Wrench size={20} />
          <span>{dict.admin.store}</span>
          <strong>{config.store}</strong>
        </div>
        <div className="metric">
          <ShieldCheck size={20} />
          <span>{dict.admin.authMode}</span>
          <strong>{config.auth.mode}</strong>
        </div>
        <div className="metric">
          <KeyRound size={20} />
          <span>{dict.admin.trustedSecret}</span>
          <strong>{config.auth.trusted_identity_secret_configured ? dict.admin.enabled : dict.admin.disabled}</strong>
        </div>
      </section>

      <section className="detail-grid">
        <div className="surface">
          <div className="surface-header">
            <h2>{dict.admin.allowedTools}</h2>
          </div>
          <div className="list">
            {(config.tools.allowed.length ? config.tools.allowed : ["-"]).map((tool) => (
              <article className="list-item" key={tool}>
                <strong>{tool}</strong>
              </article>
            ))}
          </div>
        </div>

        <div className="surface">
          <div className="surface-header">
            <h2>{dict.admin.configuredBackends}</h2>
          </div>
          <div className="list">
            {(config.tools.configured_backends.length ? config.tools.configured_backends : ["-"]).map((backend) => (
              <article className="list-item" key={backend}>
                <strong>{backend}</strong>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="surface">
        <div className="surface-header">
          <h2>{dict.admin.toolStatus}</h2>
        </div>
        <div className="list">
          {toolStatuses.map((tool) => (
            <article className="list-item" key={tool.name}>
              <div className="list-head">
                <strong>{tool.name}</strong>
                <span className={`badge ${modeBadgeClass(tool.mode)}`}>
                  {modeLabels[tool.mode] ?? tool.mode}
                </span>
              </div>
              <div className="tool-status-meta">
                <span>
                  {dict.admin.backend}: {tool.backend_type}
                </span>
                <span>
                  {dict.admin.readOnly}: {tool.read_only ? dict.admin.yes : dict.admin.no}
                </span>
                {typeof tool.timeout_seconds === "number" ? (
                  <span>
                    {dict.admin.timeout}: {tool.timeout_seconds}s
                  </span>
                ) : null}
                {typeof tool.retry_count === "number" ? (
                  <span>
                    {dict.admin.retries}: {tool.retry_count}
                  </span>
                ) : null}
                {typeof tool.result_limit === "number" ? (
                  <span>
                    {dict.admin.resultLimit}: {tool.result_limit}
                  </span>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="surface">
        <div className="surface-header">
          <h2>{dict.admin.llm}</h2>
        </div>
        <pre className="reply-preview">{JSON.stringify(config.llm, null, 2)}</pre>
      </section>

      <section className="surface">
        <div className="surface-header">
          <h2>{dict.admin.embeddings}</h2>
        </div>
        <pre className="reply-preview">{JSON.stringify(config.embeddings ?? {}, null, 2)}</pre>
      </section>
    </main>
  );
}
