import type { RunTrace } from "@support-copilot/shared";

import { ApiErrorState, StatePanel } from "@/components/page-state";
import { RunTraceView } from "@/components/run-trace-view";
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

  const user = userResult.data;

  if (!hasCapability(user, "trace")) {
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

  return <RunTraceView initialTrace={trace} locale={locale} canManageRun={hasCapability(user, "start_run")} />;
}
