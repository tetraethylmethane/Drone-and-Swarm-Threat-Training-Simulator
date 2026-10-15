/**
 * Minimal typed API client.
 *
 * - Same-origin requests to /api/v1 (proxied by Vite in development, nginx in deployment).
 * - Session cookie is HttpOnly; the CSRF token is read from the readable cookie and sent
 *   as X-CSRF-Token on every state-changing request.
 * - Errors are normalised to ApiError with the backend's structured code and message.
 */

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

type Listener = (status: number) => void;
const authListeners = new Set<Listener>();
export function onAuthFailure(fn: Listener): () => void {
  authListeners.add(fn);
  return () => authListeners.delete(fn);
}

export async function request<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  init?: { signal?: AbortSignal; raw?: boolean },
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = readCookie("drikr_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      signal: init?.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(
      0,
      "network_error",
      "The training server cannot be reached. Check the connection and retry.",
    );
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status})`;
    let details: unknown;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
      details = data?.error?.details;
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) authListeners.forEach((fn) => fn(401));
    // The role now requires MFA (policy changed mid-session): let the app route to enrolment.
    if (res.status === 403 && code === "mfa_enrollment_required") authListeners.forEach((fn) => fn(403));
    throw new ApiError(res.status, code, message, details);
  }
  if (init?.raw) return (await res.blob()) as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
};

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Download a protected file (CSV/PDF) using the session cookie, then save it locally. */
export async function download(path: string, filename: string): Promise<void> {
  const blob = await request<Blob>("GET", path, undefined, { raw: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
