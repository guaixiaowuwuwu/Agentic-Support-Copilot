import type { AdminConfig, ToolConfigStatus } from "@support-copilot/shared";
import { Bot, Database, KeyRound, Settings, ShieldCheck, Wrench } from "lucide-react";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { demoAdminConfig } from "@/lib/api";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

function modeBadgeClass(mode: string) {
  if (mode === "configured" || mode === "openai_compatible") {
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
    hashing_fallback: dict.admin.modeFallback,
    openai_compatible: dict.admin.modeConfigured,
    blocked_write_tool: dict.admin.modeBlocked,
    disabled: dict.admin.modeDisabled
  };
  const embeddings = config.embeddings ?? {
    provider: "-",
    mode: "hashing_fallback",
    model: null,
    base_url_configured: false,
    api_key_configured: false
  };
  const llmMode = config.llm.mode ?? (config.llm.enabled ? "openai_compatible" : "deterministic_fallback");
  const embeddingMode = embeddings.mode;

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

      <section className="detail-grid">
        <div className="surface">
          <div className="surface-header">
            <h2>{dict.admin.llm}</h2>
            <span className={`badge ${modeBadgeClass(llmMode)}`}>{modeLabels[llmMode] ?? llmMode}</span>
          </div>
          <div className="list">
            <article className="list-item">
              <div className="list-head">
                <strong>{dict.admin.enabled}</strong>
                <span className={`badge ${config.llm.enabled ? "badge-green" : "badge-neutral"}`}>
                  {config.llm.enabled ? dict.admin.yes : dict.admin.no}
                </span>
              </div>
              <div className="tool-status-meta">
                <span>
                  <Bot size={14} aria-hidden="true" /> {dict.admin.model}: {config.llm.model ?? "-"}
                </span>
                <span>
                  <Settings size={14} aria-hidden="true" /> {dict.admin.baseUrlConfigured}:{" "}
                  {config.llm.base_url_configured ? dict.admin.yes : dict.admin.no}
                </span>
                <span>
                  <KeyRound size={14} aria-hidden="true" /> {dict.admin.apiKeyConfigured}:{" "}
                  {config.llm.api_key_configured ? dict.admin.yes : dict.admin.no}
                </span>
                {typeof config.llm.rate_limit_per_minute === "number" ? (
                  <span>
                    {dict.admin.rateLimit}: {config.llm.rate_limit_per_minute}
                  </span>
                ) : null}
              </div>
            </article>
          </div>
        </div>

        <div className="surface">
          <div className="surface-header">
            <h2>{dict.admin.embeddings}</h2>
            <span className={`badge ${modeBadgeClass(embeddingMode)}`}>
              {modeLabels[embeddingMode] ?? embeddingMode}
            </span>
          </div>
          <div className="list">
            <article className="list-item">
              <div className="list-head">
                <strong>{embeddings.provider}</strong>
                <span className="badge badge-neutral">{dict.admin.provider}</span>
              </div>
              <div className="tool-status-meta">
                <span>
                  <Database size={14} aria-hidden="true" /> {dict.admin.model}: {embeddings.model ?? "-"}
                </span>
                <span>
                  <Settings size={14} aria-hidden="true" /> {dict.admin.baseUrlConfigured}:{" "}
                  {embeddings.base_url_configured ? dict.admin.yes : dict.admin.no}
                </span>
                <span>
                  <KeyRound size={14} aria-hidden="true" /> {dict.admin.apiKeyConfigured}:{" "}
                  {embeddings.api_key_configured ? dict.admin.yes : dict.admin.no}
                </span>
                {typeof embeddings.dimensions === "number" ? (
                  <span>
                    {dict.admin.dimensions}: {embeddings.dimensions}
                  </span>
                ) : null}
              </div>
            </article>
          </div>
        </div>
      </section>
    </main>
  );
}
