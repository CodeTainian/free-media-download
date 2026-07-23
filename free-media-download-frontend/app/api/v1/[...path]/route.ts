import type { NextRequest } from "next/server";

type ProxyContext = {
  params: Promise<{ path: string[] }>;
};

const SAFE_PATH_SEGMENT = /^[A-Za-z0-9._~-]+$/;
const REQUEST_HEADERS = ["accept", "content-type", "if-range", "last-event-id", "range"];
const RESPONSE_HEADERS = [
  "accept-ranges",
  "cache-control",
  "content-disposition",
  "content-length",
  "content-range",
  "content-type",
  "etag",
  "last-modified",
  "location",
  "x-accel-buffering",
];

function apiOrigin() {
  const configured = process.env.SAVEBOLT_API_ORIGIN?.trim();
  if (!configured && process.env.NODE_ENV === "production") return null;

  const url = new URL(configured || "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("SAVEBOLT_API_ORIGIN must be an HTTP(S) origin without credentials.");
  }
  return url.origin;
}

async function proxy(request: NextRequest, context: ProxyContext) {
  const origin = apiOrigin();
  if (!origin) {
    return Response.json(
      {
        code: "SERVICE_OFFLINE",
        message: "The SaveBolt API origin is not configured for this deployment.",
        retryable: true,
      },
      { status: 503 },
    );
  }

  const { path } = await context.params;
  if (!path.length || path.some((segment) => !SAFE_PATH_SEGMENT.test(segment))) {
    return Response.json(
      { code: "INVALID_API_PATH", message: "The requested API path is invalid.", retryable: false },
      { status: 400 },
    );
  }

  const target = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, origin);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return Response.json(
      {
        code: "SERVICE_OFFLINE",
        message: "SaveBolt could not reach the media service.",
        retryable: true,
      },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const dynamic = "force-dynamic";

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const DELETE = proxy;
