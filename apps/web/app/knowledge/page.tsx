import type { Document as KnowledgeDocument } from "@support-copilot/shared";
import { BookOpenText, CheckCircle2, Database, Layers3 } from "lucide-react";

import { KnowledgeActions } from "@/components/knowledge-actions";
import { ApiErrorState, StatePanel } from "@/components/page-state";
import { demoDocuments } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

const embeddingBadgeVariant: Record<string, string> = {
  empty: "badge-neutral",
  pending: "badge-amber",
  partial: "badge-blue",
  embedded: "badge-green"
};

export default async function KnowledgePage() {
  const { locale, dict } = await getI18n();
  const userResult = await getCurrentUserResult();

  if (!userResult.ok) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.knowledge.eyebrow}</p>
            <h1>{dict.knowledge.title}</h1>
          </div>
        </section>
        <ApiErrorState error={userResult.error} dict={dict} body={dict.state.knowledgeErrorBody} />
      </main>
    );
  }

  const user = userResult.data;
  if (!hasCapability(user, "knowledge")) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.knowledge.eyebrow}</p>
            <h1>{dict.knowledge.title}</h1>
          </div>
        </section>
        <StatePanel tone="permission" title={dict.state.permissionTitle} body={dict.state.workspaceDeniedBody} />
      </main>
    );
  }

  let documents: KnowledgeDocument[];
  try {
    documents = await serverApiGet<KnowledgeDocument[]>("/api/knowledge/documents", demoDocuments);
  } catch (error) {
    return (
      <main className="page">
        <section className="page-title">
          <div>
            <p className="eyebrow">{dict.knowledge.eyebrow}</p>
            <h1>{dict.knowledge.title}</h1>
          </div>
        </section>
        <ApiErrorState error={error} dict={dict} body={dict.state.knowledgeErrorBody} />
      </main>
    );
  }

  const totalChunks = documents.reduce((sum, document) => sum + (document.chunk_count ?? 0), 0);
  const readyDocuments = documents.filter((document) => document.embedding_status === "embedded").length;
  const pendingDocuments = documents.filter((document) => {
    const status = document.embedding_status ?? "pending";
    return status === "pending" || status === "partial";
  }).length;

  return (
    <main className="page">
      <section className="page-title">
        <div>
          <p className="eyebrow">{dict.knowledge.eyebrow}</p>
          <h1>{dict.knowledge.title}</h1>
        </div>
        <div className="queue-count">
          <BookOpenText size={18} />
          <strong>{documents.length}</strong>
        </div>
      </section>

      <section className="metrics-grid" aria-label={dict.knowledge.metricsLabel}>
        <div className="metric">
          <BookOpenText size={20} />
          <span>{dict.knowledge.totalDocuments}</span>
          <strong>{documents.length}</strong>
        </div>
        <div className="metric">
          <Layers3 size={20} />
          <span>{dict.knowledge.totalChunks}</span>
          <strong>{totalChunks}</strong>
        </div>
        <div className="metric">
          <CheckCircle2 size={20} />
          <span>{dict.knowledge.readyDocuments}</span>
          <strong>{readyDocuments}</strong>
        </div>
        <div className="metric">
          <Database size={20} />
          <span>{dict.knowledge.pendingEmbedding}</span>
          <strong>{pendingDocuments}</strong>
        </div>
      </section>

      {hasCapability(user, "knowledge_write") ? (
        <section className="surface">
          <div className="surface-header">
            <h2>{dict.knowledge.newDocument}</h2>
          </div>
          <KnowledgeActions key={locale} locale={locale} tenantId={user.tenant_id} />
        </section>
      ) : null}

      <section className="surface">
        <div className="surface-header">
          <h2>{dict.knowledge.documents}</h2>
        </div>
        {documents.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{dict.knowledge.tableTitle}</th>
                  <th>{dict.knowledge.tableSource}</th>
                  <th>{dict.knowledge.metadata}</th>
                  <th>{dict.knowledge.sourceUri}</th>
                  <th>{dict.knowledge.tableChunks}</th>
                  <th>{dict.knowledge.tableEmbedding}</th>
                  <th>{dict.knowledge.tableCreated}</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => {
                  const chunkCount = document.chunk_count ?? 0;
                  const embeddedChunkCount = document.embedded_chunk_count ?? 0;
                  const embeddingStatus = document.embedding_status ?? "pending";
                  const embeddingLabel =
                    dict.knowledge.embeddingStatus[
                      embeddingStatus as keyof typeof dict.knowledge.embeddingStatus
                    ] ?? embeddingStatus;

                  return (
                    <tr key={document.id}>
                      <td>
                        <strong>{document.title}</strong>
                        <span className="muted-line">{compactId(document.id)}</span>
                        <details className="document-details">
                          <summary>{dict.knowledge.viewDetails}</summary>
                          <p>{document.content}</p>
                        </details>
                      </td>
                      <td>{document.source_type}</td>
                      <td>
                        <span className="muted-line">
                          {dict.knowledge.productLine}: {document.product_line || "-"}
                        </span>
                        <span className="muted-line">
                          {dict.knowledge.version}: {document.version || "-"}
                        </span>
                        <span className="muted-line">
                          {dict.knowledge.requiredPermissions}: {(document.required_permissions ?? []).join(", ") || "-"}
                        </span>
                        <span className="muted-line">
                          {dict.knowledge.sourceSystem}: {document.source_system || "-"}
                        </span>
                      </td>
                      <td className="uri-cell">{document.uri}</td>
                      <td>
                        {dict.knowledge.embeddedChunks
                          .replace("{embedded}", String(embeddedChunkCount))
                          .replace("{total}", String(chunkCount))}
                      </td>
                      <td>
                        <span className={`badge ${embeddingBadgeVariant[embeddingStatus] ?? "badge-neutral"}`}>
                          {embeddingLabel}
                        </span>
                      </td>
                      <td>{formatDate(document.created_at, locale)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <StatePanel
            tone="empty"
            title={dict.state.documentsEmptyTitle}
            body={dict.state.documentsEmptyBody}
            compact
          />
        )}
      </section>
    </main>
  );
}
