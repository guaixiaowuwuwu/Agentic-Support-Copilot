import { cache } from "react";
import { headers } from "next/headers";

import type { UserContext } from "@support-copilot/shared";

import {
  apiConfig,
  apiErrorFromResponse,
  localDevIdentityHeaders,
  localDevUserContext,
  normalizeApiError
} from "@/lib/api";

export type LoadResult<T> = { ok: true; data: T } | { ok: false; error: unknown };

const FORWARDED_IDENTITY_HEADERS: Array<[string, string[]]> = [
  [
    "X-Support-Copilot-User-Email",
    ["x-support-copilot-user-email", "x-auth-request-email"]
  ],
  [
    "X-Support-Copilot-Tenant-Id",
    ["x-support-copilot-tenant-id", "x-auth-request-tenant-id"]
  ],
  [
    "X-Support-Copilot-Tenant-Ids",
    ["x-support-copilot-tenant-ids", "x-auth-request-tenant-ids"]
  ],
  [
    "X-Support-Copilot-User-Roles",
    ["x-support-copilot-user-roles", "x-auth-request-roles", "x-auth-request-groups"]
  ]
];

async function serverIdentityHeaders(): Promise<Record<string, string>> {
  const incoming = await headers();
  const requestHeaders: Record<string, string> = {};

  for (const [targetHeader, sourceHeaders] of FORWARDED_IDENTITY_HEADERS) {
    const value = sourceHeaders.map((sourceHeader) => incoming.get(sourceHeader)).find(Boolean);
    if (value) {
      requestHeaders[targetHeader] = value;
    }
  }

  const trustedSecret =
    process.env.SUPPORT_COPILOT_API_TRUSTED_IDENTITY_SECRET ??
    process.env.SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET;
  if (trustedSecret) {
    requestHeaders["X-Support-Copilot-Trusted-Identity"] = trustedSecret;
  }

  return {
    ...localDevIdentityHeaders(),
    ...requestHeaders
  };
}

export async function serverApiGet<T>(path: string, demoFallback?: T): Promise<T> {
  try {
    const response = await fetch(`${apiConfig.baseUrl}${path}`, {
      cache: "no-store",
      headers: await serverIdentityHeaders()
    });
    if (!response.ok) {
      throw await apiErrorFromResponse(response, path);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (apiConfig.demoMode && demoFallback !== undefined) {
      return demoFallback;
    }
    throw normalizeApiError(error, path);
  }
}

export async function loadResult<T>(promise: Promise<T>): Promise<LoadResult<T>> {
  try {
    return { ok: true, data: await promise };
  } catch (error) {
    return { ok: false, error };
  }
}

export const getCurrentUserResult = cache(async (): Promise<LoadResult<UserContext>> => {
  return loadResult(serverApiGet<UserContext>("/api/auth/me", localDevUserContext));
});
