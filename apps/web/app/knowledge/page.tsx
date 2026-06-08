import type { Document as KnowledgeDocument } from "@support-copilot/shared";
import { BookOpenText } from "lucide-react";

import { KnowledgeActions } from "@/components/knowledge-actions";
import { ApiErrorState, StatePanel } from "@/components/page-state";
import { demoDocuments } from "@/lib/api";
import { compactId, formatDate } from "@/lib/format";
import { getI18n } from "@/lib/i18n-server";
import { hasCapability } from "@/lib/rbac";
import { getCurrentUserResult, serverApiGet } from "@/lib/server-api";

export const dynamic = "force-dynamic";

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
                  <th>{dict.knowledge.uri}</th>
                  <th>{dict.knowledge.tableCreated}</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
                  <tr key={document.id}>
                    <td>
                      <strong>{document.title}</strong>
                      <span className="muted-line">{compactId(document.id)}</span>
                    </td>
                    <td>{document.source_type}</td>
                    <td>{document.uri}</td>
                    <td>{formatDate(document.created_at, locale)}</td>
                  </tr>
                ))}
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
