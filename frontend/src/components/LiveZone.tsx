import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../api";
import { cameras, type Camera } from "../api/cameras";
import { countPeople, loadDetector, smoother, type Box } from "../live/detector";
import CameraPreview from "./CameraPreview";

export type LiveZoneData = {
  zone_id: string; camera_id: string; people: number; view_area_m2: number; capacity_people: number;
  density: number; risk_score: number; risk_level: string; age_sec: number; status: "LIVE" | "STALE";
};
type NodeLite = { id: string; label: string };
type Props = { nodes: NodeLite[]; live: LiveZoneData[] };

const INTERVAL_MS = 1000;

/** Counts people from a registered camera in this browser and reports the number to the backend for a live zone. */
export default function LiveZone({ nodes, live }: Props) {
  const [list, setList] = useState<Camera[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [zoneId, setZoneId] = useState("gate-e");
  const [area, setArea] = useState(20);
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState<"idle" | "starting" | "loading-model" | "counting">("idle");
  const [count, setCount] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const stop = useRef(false);

  const refresh = useCallback(() => {
    cameras.list().then(r => {
      const regs = r.items.filter(c => c.origin === "registered" && c.source_type !== "usb");
      setList(regs);
      setCameraId(cur => cur || regs[0]?.id || "");
    }).catch(() => setList([]));
  }, []);
  useEffect(refresh, [refresh]);

  const draw = useCallback((boxes: Box[], vw: number, vh: number) => {
    const c = overlay.current, v = video;
    if (!c || !v) return;
    c.width = v.clientWidth; c.height = v.clientHeight;
    const ctx = c.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);
    // the <video> letterboxes its picture (object-fit: contain), so map frame pixels into the visible picture area
    const scale = Math.min(c.width / vw, c.height / vh);
    const ox = (c.width - vw * scale) / 2, oy = (c.height - vh * scale) / 2;
    ctx.strokeStyle = "#5dd0b1"; ctx.lineWidth = 2;
    for (const b of boxes) ctx.strokeRect(ox + b.x * scale, oy + b.y * scale, b.w * scale, b.h * scale);
  }, [video]);

  // Counting loop. Re-created only when the settings or the video element change.
  useEffect(() => {
    if (!running || !video || !cameraId) return;
    stop.current = false;
    const smooth = smoother(3);
    let timer: number | undefined;
    const tick = async () => {
      if (stop.current) return;
      try {
        if (video.readyState >= 2 && video.videoWidth > 0) {
          setPhase("counting");
          const d = await countPeople(video);
          if (stop.current) return;
          const n = smooth(d.people);
          setCount(n); draw(d.boxes, d.videoWidth, d.videoHeight);
          await request("/api/live/observations", { method: "POST", body: JSON.stringify({ camera_id: cameraId, zone_id: zoneId, people: n, view_area_m2: area }) });
          setError("");
        }
      } catch (e) { if (!stop.current) setError((e as Error).message); }
      if (!stop.current) timer = window.setTimeout(tick, INTERVAL_MS);
    };
    tick();
    return () => { stop.current = true; window.clearTimeout(timer); };
  }, [running, video, cameraId, zoneId, area, draw]);

  const start = async () => {
    setError(""); setPhase("starting");
    try {
      await cameras.startStream(cameraId);             // the gateway must be serving the camera
      setPhase("loading-model");
      await loadDetector();                            // bundled model, loaded once
      setRunning(true);
    } catch (e) { setPhase("idle"); setError((e as Error).message); }
  };
  const halt = async () => {
    stop.current = true; setRunning(false); setPhase("idle"); setCount(null);
    overlay.current?.getContext("2d")?.clearRect(0, 0, 9999, 9999);
    try { await request(`/api/live/${zoneId}`, { method: "DELETE" }); } catch { /* zone may already be gone */ }
    try { await cameras.stopStream(cameraId); } catch { /* ignore */ }
  };

  const zone = live.find(z => z.zone_id === zoneId && z.camera_id === cameraId);
  return (
    <section className="livezone">
      <label>LIVE CAMERA ZONE (real people count · in-browser detection)</label>
      <div className="lz-controls">
        <select value={cameraId} onChange={e => setCameraId(e.target.value)} disabled={running} aria-label="Camera">
          {list.length ? list.map(c => <option key={c.id} value={c.id}>{c.name}</option>) : <option value="">No registered cameras</option>}
        </select>
        <select value={zoneId} onChange={e => setZoneId(e.target.value)} disabled={running} aria-label="Venue zone">
          {nodes.map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
        </select>
        <input type="number" min={1} max={10000} value={area} onChange={e => setArea(Math.max(1, Number(e.target.value) || 1))} disabled={running} aria-label="Camera view area in square metres" title="Floor area the camera can see, in m²" />
        <span className="muted">m² in view</span>
        {!running
          ? <button disabled={!cameraId || phase !== "idle"} onClick={start}>{phase === "starting" ? "STARTING CAMERA…" : phase === "loading-model" ? "LOADING DETECTOR…" : "START LIVE COUNTING"}</button>
          : <button onClick={halt}>STOP</button>}
        <button onClick={refresh} disabled={running}>RELOAD CAMERAS</button>
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="lz-stage">
        <CameraPreview cameraId={cameraId} active={running} supported={true} onVideo={setVideo} />
        <canvas ref={overlay} className="lz-overlay" aria-hidden="true" />
      </div>
      {running && (
        <p className="lz-readout">
          <b>{count ?? "…"}</b> people in view
          {zone && <> · density {(zone.density * 100).toFixed(0)}% of the view's limit · <span className={"lvl " + zone.risk_level.toLowerCase()}>{zone.risk_level} {Math.round(zone.risk_score)}</span></>}
        </p>
      )}
      <p className="muted">Counts people-shaped objects in this browser tab. No faces are recognised and no images are stored or sent; only the number is reported.
        Risk uses the camera's own view: the area you enter × 2 people per m² is treated as its limit. Keep this tab open while counting.</p>
    </section>
  );
}
