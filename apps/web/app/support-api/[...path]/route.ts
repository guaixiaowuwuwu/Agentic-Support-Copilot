import { NextRequest, NextResponse } from "next/server";

import { serverApiBaseUrl, serverIdentityHeaders } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

function responseHeadersFrom(response: Response): Headers {
  const headers = new Headers();
  for (const header of ["content-type", "x-correlation-id"]) {
    const value = response.headers.get(header);
    if (value) {
      headers.set(header, value);
    }
  }
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const targetPath = `/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers(await serverIdentityHeaders());
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const response = await fetch(`${serverApiBaseUrl()}${targetPath}`, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
    cache: "no-store"
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: responseHeadersFrom(response)
  });
}

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}
