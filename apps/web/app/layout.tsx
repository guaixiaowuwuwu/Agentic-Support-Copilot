import type { Metadata } from "next";

import { TopNav } from "@/components/top-nav";
import { getI18n } from "@/lib/i18n-server";
import { getCurrentUserResult } from "@/lib/server-api";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic Support Copilot",
  description: "Enterprise support copilot dashboard"
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const { locale, dict } = await getI18n();
  const userResult = await getCurrentUserResult();

  return (
    <html lang={locale === "zh" ? "zh-CN" : "en"}>
      <body>
        <TopNav dict={dict} locale={locale} user={userResult.ok ? userResult.data : null} />
        {children}
      </body>
    </html>
  );
}
