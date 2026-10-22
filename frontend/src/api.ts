/** Base URL for HTTP calls. Empty string = same origin (nginx proxies /api and /ws in Docker). */
export const API: string = import.meta.env.VITE_API_BASE_URL ?? "";

export function wsUrl(): string {
  const explicit = import.meta.env.VITE_WS_BASE_URL;
  if (explicit) return explicit + "/ws/simulation";
  if (API) return API.replace(/^http/, "ws") + "/ws/simulation";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/simulation`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const KEY_STORAGE = "crowdflow.operatorKey";
// sessionStorage keeps the key only for this tab; it can throw in private/blocked contexts.
const getKey = (): string => { try { return sessionStorage.getItem(KEY_STORAGE) ?? ""; } catch { return ""; } };
const setKey = (k: string) => { try { k ? sessionStorage.setItem(KEY_STORAGE, k) : sessionStorage.removeItem(KEY_STORAGE); } catch { /* ignore */ } };

/** Operator key for this browser tab (sessionStorage; never localStorage or env files). */
export function setOperatorKey(k: string) { if (k) setKey(k); }  // empty input must not wipe a stored key
export function hasOperatorKey() { return getKey().length > 0; }

const FRIENDLY: Record<string, string> = {
  operator_key_required: "Operator key missing or incorrect.",
  rate_limited: "Too many requests. Wait a moment and try again.",
};

/** JSON request that turns HTTP/network failures into readable ApiErrors.
 *  State-changing calls send the operator key; on 401 the operator is asked for it once and the call retried. */
export async function request<T = unknown>(path: string, init?: RequestInit, retried = false): Promise<T> {
  let res: Response;
  const key = getKey();
  try {
    res = await fetch(API + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(key ? { "X-API-Key": key } : {}), ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the backend. Is it running?");
  }
  if (res.status === 401 && !retried) {
    const entered = window.prompt("Operator key required for this action:");
    if (entered) {
      setKey(entered.trim());
      return request<T>(path, init, true);
    }
  }
  if (res.status === 401) setKey("");  // wrong key: forget it
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, FRIENDLY[detail] ?? detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
