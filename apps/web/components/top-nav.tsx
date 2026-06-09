import type { UserContext } from "@support-copilot/shared";
import { BookOpenText, Bot, ClipboardList, ScrollText, Settings, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";

import { LanguageToggle } from "@/components/language-toggle";
import { RoleSwitcher } from "@/components/role-session";
import type { Dictionary, Locale } from "@/lib/i18n";
import type { LoginRole } from "@/lib/local-auth";
import { defaultPathForUser, navigationForUser, type WorkspaceId } from "@/lib/rbac";

const navIcons: Record<WorkspaceId, typeof ClipboardList> = {
  tickets: ClipboardList,
  approvals: ShieldCheck,
  knowledge: BookOpenText,
  audit: ScrollText,
  admin: Settings
};

export function TopNav({
  dict,
  locale,
  user,
  localRoleSwitchEnabled = false,
  selectedLoginRole
}: {
  dict: Dictionary;
  locale: Locale;
  user?: UserContext | null;
  localRoleSwitchEnabled?: boolean;
  selectedLoginRole?: LoginRole | null;
}) {
  const navItems = user ? navigationForUser(user, dict) : [];
  const homeHref = user ? defaultPathForUser(user) : "/";

  return (
    <header className="topbar">
      <Link href={homeHref} className="brand" aria-label="Agentic Support Copilot dashboard">
        <Bot size={22} />
        <span>Agentic Support Copilot</span>
      </Link>
      <div className="topbar-actions">
        {navItems.length ? (
          <nav className="navlinks" aria-label="Primary navigation">
            {navItems.map((item) => {
              const Icon = navIcons[item.id];
              return (
                <Link key={item.id} href={item.href}>
                  <Icon size={16} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        ) : null}
        {localRoleSwitchEnabled && selectedLoginRole ? (
          <RoleSwitcher locale={locale} currentRole={selectedLoginRole} user={user} />
        ) : (
          <div className="user-chip" title={user ? `${user.email} · ${user.roles.join(", ")}` : dict.state.authTitle}>
            <UserRound size={16} />
            <span>{user?.tenant_id ?? "-"}</span>
            <small>{user?.email ?? dict.state.authTitle}</small>
          </div>
        )}
        <LanguageToggle locale={locale} />
      </div>
    </header>
  );
}
