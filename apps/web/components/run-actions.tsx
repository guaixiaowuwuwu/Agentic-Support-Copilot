"use client";

import type { AgentRun } from "@support-copilot/shared";
import { CheckCircle2, PlayCircle, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost, userContext } from "@/lib/api";
import { dictionaries, normalizeLocale, type Locale } from "@/lib/i18n";

export function StartRunButton({ ticketId, locale }: { ticketId: string; locale?: Locale }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].runActions;
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  async function startRun() {
    setError("");
    setIsRunning(true);
    try {
      const run = await apiPost<AgentRun>(`/api/runs/${ticketId}/start`);
      router.push(`/runs/${run.id}/trace`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : dict.startFailed);
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="action-stack">
      <button className="icon-button" onClick={startRun} disabled={isRunning} title={dict.startRunTitle}>
        <PlayCircle size={17} />
        <span>{isRunning ? dict.running : dict.startRun}</span>
      </button>
      {error ? <span className="form-error" role="alert">{error}</span> : null}
    </div>
  );
}

export function ApprovalButtons({ approvalId, locale }: { approvalId: string; locale?: Locale }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].runActions;
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  async function decide(action: "approve" | "reject") {
    setError("");
    setIsBusy(true);
    try {
      await apiPost<AgentRun>(`/api/approvals/${approvalId}/${action}`, {
        decided_by: userContext.email,
        note: action === "approve" ? dict.approvedNote : dict.rejectedNote
      });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : dict.decisionFailed);
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="decision-stack">
      <div className="button-pair">
        <button className="icon-button approve" onClick={() => decide("approve")} disabled={isBusy} title={dict.approveTitle}>
          <CheckCircle2 size={17} />
          <span>{dict.approve}</span>
        </button>
        <button className="icon-button reject" onClick={() => decide("reject")} disabled={isBusy} title={dict.rejectTitle}>
          <XCircle size={17} />
          <span>{dict.reject}</span>
        </button>
      </div>
      {error ? <span className="form-error" role="alert">{error}</span> : null}
    </div>
  );
}
