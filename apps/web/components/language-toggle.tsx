"use client";

import { Languages } from "lucide-react";
import { useRouter } from "next/navigation";

import { dictionaries, localeCookieName, normalizeLocale, type Locale } from "@/lib/i18n";

export function LanguageToggle({ locale }: { locale?: Locale }) {
  const router = useRouter();
  const activeLocale = normalizeLocale(locale);
  const nextLocale: Locale = activeLocale === "zh" ? "en" : "zh";
  const dict = dictionaries[activeLocale];

  function switchLanguage() {
    document.cookie = `${localeCookieName}=${nextLocale}; path=/; max-age=31536000; samesite=lax`;
    router.refresh();
  }

  return (
    <button
      className="language-toggle"
      type="button"
      onClick={switchLanguage}
      title={dict.languageToggle.title}
      aria-label={dict.languageToggle.ariaLabel}
    >
      <Languages size={16} />
      <span>{dict.otherLanguageName}</span>
    </button>
  );
}
