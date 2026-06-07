import { Bot, ClipboardList, GitBranch, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";

import { LanguageToggle } from "@/components/language-toggle";
import { userContext } from "@/lib/api";
import type { Dictionary, Locale } from "@/lib/i18n";

export function TopNav({ dict, locale }: { dict: Dictionary; locale: Locale }) {
  return (
    <header className="topbar">
      <Link href="/" className="brand" aria-label="Agentic Support Copilot dashboard">
        <Bot size={22} />
        <span>Agentic Support Copilot</span>
      </Link>
      <div className="topbar-actions">
        <nav className="navlinks" aria-label="Primary navigation">
          <Link href="/">
            <ClipboardList size={16} />
            {dict.nav.tickets}
          </Link>
          <Link href="/approvals">
            <ShieldCheck size={16} />
            {dict.nav.approvals}
          </Link>
          <Link href="/runs/demo-run-api-401/trace">
            <GitBranch size={16} />
            {dict.nav.trace}
          </Link>
        </nav>
        <div className="user-chip" title={`${userContext.email} · ${userContext.roles.join(", ")}`}>
          <UserRound size={16} />
          <span>{userContext.tenant_id}</span>
          <small>{userContext.email}</small>
        </div>
        <LanguageToggle locale={locale} />
      </div>
    </header>
  );
}
