import { PageLoadingState } from "@/components/page-state";
import { getI18n } from "@/lib/i18n-server";

export default async function Loading() {
  const { dict } = await getI18n();

  return <PageLoadingState dict={dict} />;
}
