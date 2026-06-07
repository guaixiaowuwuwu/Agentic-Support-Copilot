"use client";

import { RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";

export function RetryButton({ label }: { label: string }) {
  const router = useRouter();

  return (
    <button className="icon-button" onClick={() => router.refresh()} title={label}>
      <RefreshCw size={17} />
      <span>{label}</span>
    </button>
  );
}
