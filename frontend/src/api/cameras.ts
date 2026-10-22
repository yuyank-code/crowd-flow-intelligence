import { request } from "../api";

export type CameraStatus = "unknown" | "online" | "offline" | "auth_required" | "auth_failed" | "agent_offline" | "error";
export type SourceType = "rtsp" | "onvif" | "usb";

export type Capabilities = {
  preview: boolean; snapshot: boolean; ptz: boolean; discovery: boolean;
  playback_formats: string[]; source_formats: string[];
};

export type Camera = {
  id: string; name: string; source_type?: SourceType; zone_id?: string | null; zone?: string | null;
  endpoint_host?: string | null; status: CameraStatus | string; last_seen_at?: string | null; last_error_code?: string | null;
  capabilities?: Capabilities; has_credentials?: boolean; origin?: "registered" | "config";
  configured: boolean; access_policy: string; analytics?: string; stream_active?: boolean;
  diagnostic?: string; audit?: { action: string; detail: string; at: string }[];
};

export type CameraList = { items: Camera[]; policy: string; gateway_configured: boolean; operator_auth_configured: boolean };

export type NewCamera = {
  name: string; source_type: SourceType; zone_id?: string; endpoint?: string; device_label?: string;
  username?: string; password?: string; playback_path?: string;
};

export type PtzCommand = { action: "move" | "stop" | "zoom" | "home"; pan?: number; tilt?: number; zoom?: number };

const base = "/api/cctv/sources";
const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const cameras = {
  list: () => request<CameraList>(base),
  get: (id: string) => request<Camera>(`${base}/${id}`),
  create: (c: NewCamera) => post<Camera>(base, c),
  update: (id: string, patch: { name?: string; zone_id?: string; playback_path?: string }) =>
    request<Camera>(`${base}/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  remove: (id: string) => request<void>(`${base}/${id}`, { method: "DELETE" }),
  test: (id: string) => post<Camera>(`${base}/${id}/test`),
  startStream: (id: string) => post<Camera>(`${base}/${id}/stream/start`),
  stopStream: (id: string) => post<Camera>(`${base}/${id}/stream/stop`),
  playback: (id: string) => request<{ format: string; url: string; expires_at: string }>(`${base}/${id}/playback`),
  snapshot: (id: string) => post<unknown>(`${base}/${id}/snapshot`),
  ptz: (id: string, cmd: PtzCommand) => post<unknown>(`${base}/${id}/ptz`, cmd),
};

export const STATUS_LABEL: Record<string, string> = {
  unknown: "Not tested", online: "Reachable", offline: "Offline", auth_required: "Credentials required",
  auth_failed: "Credentials rejected", agent_offline: "Local agent not connected", error: "Error",
};
