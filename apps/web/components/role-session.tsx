"use client";

import type { UserContext } from "@support-copilot/shared";
import { BookOpenText, Headphones, Settings, ShieldCheck, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  defaultPathForLoginRole,
  loginRoleCookieName,
  loginRoles,
  type LoginRole
} from "@/lib/local-auth";
import { dictionaries, normalizeLocale, type Locale } from "@/lib/i18n";

const roleIcons: Record<LoginRole, typeof Headphones> = {
  support_agent: Headphones,
  approver: ShieldCheck,
  knowledge_admin: BookOpenText,
  admin: Settings
};

function setLoginRoleCookie(role: LoginRole) {
  document.cookie = `${loginRoleCookieName}=${role}; path=/; max-age=31536000; samesite=lax`;
}

export function RoleLoginGate({ locale }: { locale?: Locale }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].auth;
  const [selectedRole, setSelectedRole] = useState<LoginRole | null>(null);

  function chooseRole(role: LoginRole) {
    setSelectedRole(role);
    setLoginRoleCookie(role);
    router.push(defaultPathForLoginRole(role));
    router.refresh();
  }

  return (
    <main className="page login-page">
      <section className="surface login-panel" aria-labelledby="role-login-title">
        <div className="surface-header">
          <div>
            <p className="eyebrow">{dict.eyebrow}</p>
            <h1 id="role-login-title">{dict.title}</h1>
          </div>
        </div>
        <div className="role-grid">
          {loginRoles.map((role) => {
            const Icon = roleIcons[role];
            const roleCopy = dict.roles[role];
            return (
              <button
                className="role-card"
                type="button"
                key={role}
                onClick={() => chooseRole(role)}
                disabled={selectedRole !== null}
              >
                <span className="role-card-icon">
                  <Icon size={20} />
                </span>
                <span>
                  <strong>{roleCopy.label}</strong>
                  <small>{roleCopy.description}</small>
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </main>
  );
}

export function RoleSwitcher({
  locale,
  currentRole,
  user
}: {
  locale?: Locale;
  currentRole: LoginRole;
  user?: UserContext | null;
}) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const dict = dictionaries[activeLocale].auth;

  function switchRole(role: LoginRole) {
    setLoginRoleCookie(role);
    router.push(defaultPathForLoginRole(role));
    router.refresh();
  }

  return (
    <div className="role-switcher">
      <div className="user-chip" title={user ? `${user.email} · ${user.roles.join(", ")}` : dict.switchRole}>
        <UserRound size={16} />
        <span>{user?.tenant_id ?? "-"}</span>
        <small>{user?.email ?? dict.currentRole}</small>
      </div>
      <label className="role-select-label">
        <span>{dict.switchRole}</span>
        <select
          className="role-select"
          value={currentRole}
          onChange={(event) => switchRole(event.target.value as LoginRole)}
          aria-label={dict.switchRole}
        >
          {loginRoles.map((role) => (
            <option key={role} value={role}>
              {dict.roles[role].label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
