import { normalizeLocale, statusLabel, type Locale } from "@/lib/i18n";

const variants: Record<string, string> = {
  open: "badge-neutral",
  running: "badge-blue",
  triaged: "badge-blue",
  awaiting_approval: "badge-amber",
  replied: "badge-green",
  completed: "badge-green",
  rejected: "badge-red",
  pending: "badge-amber",
  approved: "badge-green",
  success: "badge-green",
  blocked: "badge-amber",
  denied: "badge-red",
  failed: "badge-red",
  low: "badge-green",
  medium: "badge-amber",
  high: "badge-red"
};

export function StatusBadge({ value, locale }: { value?: string | null; locale?: Locale }) {
  const label = value ?? "unknown";
  const activeLocale = normalizeLocale(locale);
  return <span className={`badge ${variants[label] ?? "badge-neutral"}`}>{statusLabel(value, activeLocale)}</span>;
}
