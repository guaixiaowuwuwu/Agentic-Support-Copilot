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
  const [isRunning, setIsRunning] = useState(false);

  async function startRun() {
    setIsRunning(true);
    try {
      const run = await apiPost<AgentRun>(`/api/runs/${ticketId}/start`);
      router.push(`/runs/${run.id}/trace`);
      router.refresh();
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <button className="icon-button" onClick={startRun} disabled={isRunning} title={dict.startRunTitle}>
      <PlayCircle size={17} />
      <span>{isRunning ? dict.running : dict.startRun}</span>
    </button>
  );
}

export function ApprovalButtons({ approvalId, locale }: { approvalId: string; locale?: Locale }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].runActions;
  const [isBusy, setIsBusy] = useState(false);

  async function decide(action: "approve" | "reject") {
    setIsBusy(true);
    try {
      await apiPost<AgentRun>(`/api/approvals/${approvalId}/${action}`, {
        decided_by: userContext.email,
        note: action === "approve" ? dict.approvedNote : dict.rejectedNote
      });
      router.refresh();
    } finally {
      setIsBusy(false);
    }
  }

  return (
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
  );
}
