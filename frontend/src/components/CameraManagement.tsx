import { useCallback, useEffect, useMemo, useState } from "react";
import { setOperatorKey } from "../api";
import { cameras, STATUS_LABEL, type Camera, type NewCamera, type SourceType } from "../api/cameras";
import CameraControls from "./CameraControls";
import CameraPreview from "./CameraPreview";

const EMPTY: NewCamera = { name: "", source_type: "rtsp", zone_id: "", endpoint: "", device_label: "", username: "", password: "", playback_path: "" };

export default function CameraManagement() {
  const [items, setItems] = useState<Camera[] | null>(null);
  const [gateway, setGateway] = useState(false);
  const [authConfigured, setAuthConfigured] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Camera | null>(null);
  const [form, setForm] = useState<NewCamera>(EMPTY);
  const [showForm, setShowForm] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const r = await cameras.list();
      setItems(r.items); setGateway(r.gateway_configured); setAuthConfigured(r.operator_auth_configured);
    } catch (e) { setError((e as Error).message); setItems((cur) => cur ?? []); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { setOperatorKey(key); }, [key]);

  const loadDetail = useCallback(async (id: string) => {
    try { setDetail(await cameras.get(id)); } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { if (selectedId) loadDetail(selectedId); else setDetail(null); }, [selectedId, loadDetail]);

  // One operator action at a time; surfaces API errors verbatim (they never contain secrets).
  const act = async (label: string, fn: () => Promise<unknown>, okMsg?: string) => {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null);
    try { await fn(); if (okMsg) setNotice(okMsg); }
    catch (e) { setError(`${label}: ${(e as Error).message}`); }
    finally { setBusy(false); await refresh(); if (selectedId) await loadDetail(selectedId); }
  };

  const visible = useMemo(() => (items ?? []).filter(c => filter === "all" || c.status === filter), [items, filter]);
  const canOperate = key.length > 0;
  const registered = detail?.origin === "registered";
  const formError = (() => {
    if (!form.name.trim()) return "Name is required.";
    if (form.source_type !== "usb" && !form.endpoint?.trim()) return "Endpoint is required.";
    if (form.source_type === "usb" && !form.device_label?.trim()) return "Device label is required.";
    if (!!form.username !== !!form.password) return "Provide both username and password, or neither.";
    return null;
  })();

  const submit = () => act("Register", async () => {
    const body: NewCamera = { name: form.name.trim(), source_type: form.source_type };
    (["zone_id", "endpoint", "device_label", "username", "password", "playback_path"] as const).forEach(k => { const v = form[k]?.trim(); if (v) body[k] = v; });
    const created = await cameras.create(body);
    setForm(EMPTY); setShowForm(false); setSelectedId(created.id);
  }, "Camera registered (not yet tested).");

  return (
    <div className="cameras">
      <div className="cam-toolbar">
        <h2>Cameras</h2>
        <input type="password" placeholder="Operator key (memory only)" value={key} onChange={e => setKey(e.target.value)} aria-label="Operator key" autoComplete="off" />
        <select value={filter} onChange={e => setFilter(e.target.value)} aria-label="Filter by status">
          <option value="all">All statuses</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button onClick={() => setShowForm(s => !s)} disabled={!canOperate} title={canOperate ? "" : "Enter the operator key first"}>{showForm ? "CANCEL" : "ADD CAMERA"}</button>
        <button onClick={refresh}>REFRESH</button>
      </div>
      {!authConfigured && <div className="banner">Operator auth is not configured on the server (OPERATOR_API_KEY). Camera changes and controls are disabled.</div>}
      {!gateway && <p className="muted">No media gateway configured: cameras can be registered and tested, but live preview is unavailable.</p>}
      {error && <div className="banner" role="alert">{error} <button onClick={() => setError(null)}>dismiss</button></div>}
      {notice && <p className="notice" role="status">{notice}</p>}

      {showForm && (
        <form className="cam-form" onSubmit={e => { e.preventDefault(); if (!formError) submit(); }}>
          <label>Type
            <select value={form.source_type} onChange={e => setForm({ ...form, source_type: e.target.value as SourceType })}>
              <option value="rtsp">RTSP / IP camera</option><option value="onvif">ONVIF device</option><option value="usb">USB (needs local agent)</option>
            </select>
          </label>
          <label>Name<input value={form.name} maxLength={80} onChange={e => setForm({ ...form, name: e.target.value })} /></label>
          <label>Zone (venue node id)<input value={form.zone_id} maxLength={64} onChange={e => setForm({ ...form, zone_id: e.target.value })} placeholder="gate-e" /></label>
          {form.source_type === "usb"
            ? <label>Device label<input value={form.device_label} maxLength={120} onChange={e => setForm({ ...form, device_label: e.target.value })} /></label>
            : <>
                <label>Endpoint<input value={form.endpoint} maxLength={512} onChange={e => setForm({ ...form, endpoint: e.target.value })} placeholder={form.source_type === "rtsp" ? "rtsp://192.168.1.20:554/stream1" : "http://192.168.1.20/onvif/device_service"} /></label>
                <label>Username<input value={form.username} maxLength={128} autoComplete="off" onChange={e => setForm({ ...form, username: e.target.value })} /></label>
                <label>Password<input type="password" value={form.password} maxLength={128} autoComplete="new-password" onChange={e => setForm({ ...form, password: e.target.value })} /></label>
                <label>Gateway playback path (optional)<input value={form.playback_path} maxLength={100} onChange={e => setForm({ ...form, playback_path: e.target.value })} placeholder="gate-e-cam" /></label>
              </>}
          {formError && <p className="muted">{formError}</p>}
          <small className="muted">Only register cameras you are authorized to access. Credentials are encrypted server-side and never shown again.</small>
          <button type="submit" disabled={busy || !!formError}>{busy ? "SAVING…" : "REGISTER"}</button>
        </form>
      )}

      {items === null ? <p className="muted">Loading cameras…</p> : (
        <div className="cam-layout">
          <div className="cam-grid">
            {visible.length === 0 && <p className="muted">{items.length ? "No cameras match this filter." : "No cameras registered yet."}</p>}
            {visible.map(c => (
              <button key={c.id} className={"cam-card" + (c.id === selectedId ? " selected" : "")} onClick={() => setSelectedId(c.id)}>
                <span className={"dot " + c.status} aria-hidden />
                <b>{c.name}</b>
                <small>{(c.source_type ?? "config").toUpperCase()} · {c.zone_id ?? c.zone ?? "no zone"}</small>
                <small>{STATUS_LABEL[c.status] ?? c.status}</small>
              </button>
            ))}
          </div>
          <div className="cam-detail">
            {!detail ? <p className="muted">Select a camera.</p> : (
              <>
                <h3>{detail.name}</h3>
                <p className="muted">Status: <b>{STATUS_LABEL[detail.status] ?? detail.status}</b>
                  {detail.last_seen_at && <> · last reachable {new Date(detail.last_seen_at).toLocaleString()}</>}
                  {detail.last_error_code && <> · {detail.last_error_code}</>}</p>
                {detail.endpoint_host && <p className="muted">Endpoint: {detail.endpoint_host}{detail.has_credentials && " · credentials stored"}</p>}
                {detail.diagnostic && <p className="muted">{detail.diagnostic}</p>}
                {!registered ? <p className="muted">Configured via server settings (read-only here; metadata only).</p> : (
                  <>
                    <CameraPreview cameraId={detail.id} active={!!detail.stream_active} supported={!!detail.capabilities?.preview} />
                    <CameraControls camera={detail} busy={busy} canOperate={canOperate}
                      onTest={() => act("Test", async () => { const r = await cameras.test(detail.id); setDetail(r); }, "Connection test finished.")}
                      onStart={() => act("Start stream", () => cameras.startStream(detail.id))}
                      onStop={() => act("Stop stream", () => cameras.stopStream(detail.id))}
                      onSnapshot={() => act("Snapshot", () => cameras.snapshot(detail.id))}
                      onPtz={(action, pan, tilt) => act("PTZ", () => cameras.ptz(detail.id, { action, pan, tilt }))} />
                    <button className="danger" disabled={busy || !canOperate}
                      onClick={() => { if (window.confirm(`Remove camera “${detail.name}”?`)) act("Delete", async () => { await cameras.remove(detail.id); setSelectedId(null); }, "Camera removed."); }}>REMOVE CAMERA</button>
                    {detail.audit && detail.audit.length > 0 && (
                      <details><summary>Recent operator actions</summary>
                        <ul>{detail.audit.map((a, i) => <li key={i} className="muted">{new Date(a.at).toLocaleTimeString()} · {a.action} {a.detail}</li>)}</ul>
                      </details>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
