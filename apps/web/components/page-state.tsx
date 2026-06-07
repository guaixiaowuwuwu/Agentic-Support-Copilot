import { AlertTriangle, Inbox, Loader2, ShieldAlert } from "lucide-react";

import { RetryButton } from "@/components/retry-button";
import { isApiError, isPermissionError } from "@/lib/api";
import type { Dictionary } from "@/lib/i18n";

type StateTone = "empty" | "error" | "loading" | "permission";

const stateIcons = {
  empty: Inbox,
  error: AlertTriangle,
  loading: Loader2,
  permission: ShieldAlert
};

export function StatePanel({
  title,
  body,
  tone = "empty",
  actionLabel,
  detail,
  compact = false
}: {
  title: string;
  body: string;
  tone?: StateTone;
  actionLabel?: string;
  detail?: string;
  compact?: boolean;
}) {
  const Icon = stateIcons[tone];

  return (
    <div className={`state-panel state-${tone}${compact ? " state-panel-compact" : ""}`}>
      <Icon className="state-icon" size={compact ? 20 : 24} aria-hidden="true" />
      <div className="state-copy">
        <h2>{title}</h2>
        <p>{body}</p>
        {detail ? <code className="state-detail">{detail}</code> : null}
        {actionLabel ? (
          <div className="state-actions">
            <RetryButton label={actionLabel} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ApiErrorState({
  error,
  dict,
  body,
  compact = false
}: {
  error: unknown;
  dict: Dictionary;
  body: string;
  compact?: boolean;
}) {
  const permission = isPermissionError(error);
  const detail = isApiError(error) ? error.message : undefined;

  return (
    <StatePanel
      tone={permission ? "permission" : "error"}
      title={permission ? dict.state.permissionTitle : dict.state.errorTitle}
      body={permission ? dict.state.permissionBody : body}
      detail={detail}
      actionLabel={dict.state.retry}
      compact={compact}
    />
  );
}

export function PageLoadingState({ dict }: { dict: Dictionary }) {
  return (
    <main className="page">
      <StatePanel tone="loading" title={dict.state.loadingTitle} body={dict.state.loadingBody} />
    </main>
  );
}
