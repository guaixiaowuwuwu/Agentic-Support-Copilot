import { cookies } from "next/headers";

import { dictionaries, localeCookieName, normalizeLocale } from "@/lib/i18n";

export async function getI18n() {
  const cookieStore = await cookies();
  const locale = normalizeLocale(cookieStore.get(localeCookieName)?.value);

  return {
    locale,
    dict: dictionaries[locale]
  };
}

