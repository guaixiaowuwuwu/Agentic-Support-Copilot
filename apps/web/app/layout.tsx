import type { Metadata } from "next";

import { RoleLoginGate } from "@/components/role-session";
import { TopNav } from "@/components/top-nav";
import { apiConfig } from "@/lib/api";
import { getI18n } from "@/lib/i18n-server";
import { getCurrentUserResult, getSelectedLoginRole } from "@/lib/server-api";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic Support Copilot",
  description: "Enterprise support copilot dashboard"
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const { locale, dict } = await getI18n();
  const [userResult, selectedLoginRole] = await Promise.all([getCurrentUserResult(), getSelectedLoginRole()]);
  const showLocalLogin = apiConfig.localIdentityHeaders && !selectedLoginRole && !userResult.ok;
  const user = showLocalLogin ? null : userResult.ok ? userResult.data : null;

  return (
    <html lang={locale === "zh" ? "zh-CN" : "en"}>
      <body>
        <TopNav
          dict={dict}
          locale={locale}
          user={user}
          localRoleSwitchEnabled={apiConfig.localIdentityHeaders}
          selectedLoginRole={selectedLoginRole}
        />
        {showLocalLogin ? <RoleLoginGate locale={locale} /> : children}
      </body>
    </html>
  );
}
