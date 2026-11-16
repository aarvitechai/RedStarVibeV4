/**
 * Browser API client. Same-origin through the gateway, cookie auth.
 * - Sends x-csrf-token (double-submit) on every mutating request, fetching the cookie first if needed.
 * - On 401 token_expired, refreshes once and retries.
 * - Errors always arrive in the standard shape (ADR 0010) and are thrown as ApiError.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiErrorBody,
  ) {
    super(body.message);
  }
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function csrfToken(): Promise<string> {
  const existing = readCookie("rsv_csrf");
  if (existing) return existing;
  const r = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
  const data = (await r.json()) as { csrf_token: string };
  return data.csrf_token;
}

async function send(path: string, init: RequestInit): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  if (!SAFE.has(method)) headers.set("x-csrf-token", await csrfToken());
  return fetch(path, { ...init, method, headers, credentials: "same-origin" });
}

async function parseError(r: Response): Promise<ApiError> {
  try {
    const data = (await r.json()) as { error: ApiErrorBody };
    return new ApiError(r.status, data.error);
  } catch {
    return new ApiError(r.status, { code: "network_error", message: "Something went wrong. Please try again.", details: {}, request_id: "-" });
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let r = await send(path, init);
  if (r.status === 401) {
    const err = await parseError(r.clone());
    if (err.body.code === "token_expired") {
      const refreshed = await send("/api/v1/auth/refresh", { method: "POST" });
      if (refreshed.ok) r = await send(path, init);
    }
  }
  if (!r.ok) throw await parseError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || err.body.code !== "validation_error") return {};
  const fields = (err.body.details.fields ?? []) as Array<{ loc: Array<string | number>; msg: string }>;
  const out: Record<string, string> = {};
  for (const f of fields) {
    const key = String(f.loc[f.loc.length - 1] ?? "form");
    out[key === "body" ? "form" : key] = f.msg.replace(/^Value error, /, "");
  }
  return out;
}
