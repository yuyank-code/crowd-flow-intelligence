import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CameraManagement from "./components/CameraManagement";
import DecisionSupport from "./components/DecisionSupport";
import LiveZone, { type LiveZoneData } from "./components/LiveZone";
import { request, wsUrl } from "./api";

type Node = { id: string; label: string; kind: string; x: number; y: number; capacity: number; occupancy: number };
type Edge = { id: string; source: string; target: string; capacity_per_min: number; density: number; status: string };
type Snapshot = {
  venue: { name: string; latitude: number; longitude: number };
  state: {
    status: string; sim_time_min: number; people_inside: number; total_entered: number; total_exited: number;
    risk_score: number; risk_level: string; bottlenecks: string[]; events: { type: string; node_id?: string | null; time: number }[];
    active_agents: number; stranded_agents: number; waiting_to_exit: number; reroutes: number;
    effective_crowd_size: number; crowd_capped: boolean; closed_nodes: string[];
  };
  nodes: Node[]; edges: Edge[];
  live?: LiveZoneData[];
};
type Interpretation = { crowd_size: number; arrival_rate: number; exit_rate: number; assumptions: string[]; explanation: string };
type HistoryRow = { id: number; created_at: string; sim_time_min: number; risk_score: number; risk_level: string };
type Camera = { id: string; name: string; configured: boolean; status?: string };
type Geo = { error?: string; features?: unknown[]; attribution?: string; source?: string };

const STALE_AFTER_MS = 3000;

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [lastUpdate, setLastUpdate] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [connected, setConnected] = useState(false);
  const [scenario, setScenario] = useState("30,000 people arriving for an evening concert");
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [geo, setGeo] = useState<Geo | null>(null);
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [history, setHistory] = useState<HistoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // name of the in-flight action; blocks duplicates
  const busyRef = useRef(false);
  const [view, setView] = useState<"dashboard" | "cameras">("dashboard");

  const accept = useCallback((s: Snapshot) => { setSnap(s); setLastUpdate(Date.now()); }, []);

  // Initial load + WebSocket with reconnect; everything is cleaned up on unmount.
  useEffect(() => {
    let closed = false, ws: WebSocket | undefined, timer: number | undefined;
    request<Snapshot>("/api/simulation").then(accept).catch(e => setError((e as Error).message));
    request<{ items: Camera[] }>("/api/cctv/sources").then(x => setCameras(x.items)).catch(() => setCameras([]));
    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => { setConnected(true); setError(null); };
      ws.onmessage = e => accept(JSON.parse(e.data));
      ws.onclose = () => { setConnected(false); if (!closed) timer = window.setTimeout(connect, 1500); };
      ws.onerror = () => ws?.close();
    };
    connect();
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { closed = true; window.clearTimeout(timer); window.clearInterval(tick); ws?.close(); };
  }, [accept]);

  // One command at a time: prevents double-clicks and overlapping start/pause/reset.
  const run = async (name: string, fn: () => Promise<unknown>) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(name); setError(null);
    try { await fn(); } catch (e) { setError(`${name}: ${(e as Error).message}`); }
    finally { busyRef.current = false; setBusy(null); }
  };
  const post = async (path: string, body?: unknown) =>
    accept(await request<Snapshot>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }));
  const control = async (path: string) => {
    await request(path, { method: "POST" });
    accept(await request<Snapshot>("/api/simulation"));
  };

  const interpretAndRun = () => run("Scenario", async () => {
    const x = await request<Interpretation>("/api/scenarios/interpret", { method: "POST", body: JSON.stringify({ text: scenario }) });
    setInterpretation(x);
    await post("/api/simulation/scenario", x);
  });
  const loadGeo = () => run("Geo context", async () => {
    if (!snap) throw new Error("no venue loaded yet");
    setGeo(await request<Geo>("/api/geo/context", { method: "POST", body: JSON.stringify({ lat: snap.venue.latitude, lon: snap.venue.longitude, radius_m: 1000 }) }));
  });
  const loadHistory = () => run("History", async () => setHistory((await request<{ items: HistoryRow[] }>("/api/simulation/history?limit=20")).items));

  const nodes = useMemo(() => snap?.nodes ?? [], [snap]);
  const edges = snap?.edges ?? [];
  const liveZones = snap?.live ?? [];
  const s = snap?.state;
  const stale = connected && now - lastUpdate > STALE_AFTER_MS;
  const statusLabel = !connected ? "OFFLINE" : stale ? "STALE" : "LIVE";
  const off = !!busy || !snap;

  if (!snap) {
    return <div className="app"><p className="muted" style={{ padding: 24 }}>{error ?? "Connecting to simulation…"}</p></div>;
  }

  return (
    <div className="app">
      <header>
        <div><b>CROWD FLOW</b><span> INTELLIGENCE</span><small>Venue operations & geospatial decision support · prototype, not a certified life-safety system</small></div>
        <nav className="tabs">
          <button className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}>DASHBOARD</button>
          <button className={view === "cameras" ? "active" : ""} onClick={() => setView("cameras")}>CAMERAS</button>
        </nav>
        <div className="status">● {statusLabel}{!connected && " – showing last known state"}</div>
      </header>
      {error && <div className="banner" role="alert">{error} <button onClick={() => setError(null)}>dismiss</button></div>}
      {view === "cameras" ? <CameraManagement /> : (
      <main>
        <aside>
          <section>
            <label>SCENARIO (rule-based parser, not an LLM)</label>
            <textarea value={scenario} maxLength={2000} onChange={e => setScenario(e.target.value)} />
            <button disabled={off || !scenario.trim()} onClick={interpretAndRun}>{busy === "Scenario" ? "WORKING…" : "INTERPRET & SIMULATE"}</button>
            {interpretation && (
              <div className="muted">
                <p>{interpretation.crowd_size.toLocaleString()} people · {interpretation.arrival_rate}/min in · {interpretation.exit_rate}/min out</p>
                <ul>{interpretation.assumptions.map(a => <li key={a}>{a}</li>)}</ul>
              </div>
            )}
            {s?.crowd_capped && <p className="muted">Crowd capped at {s.effective_crowd_size.toLocaleString()} simulated people (1 agent = 1 person).</p>}
          </section>
          <section>
            <label>RUN CONTROLS</label>
            <div className="row">
              <button disabled={off || s?.status === "running"} onClick={() => run("Start", () => control("/api/simulation/start"))}>START</button>
              <button disabled={off || s?.status !== "running"} onClick={() => run("Pause", () => control("/api/simulation/pause"))}>PAUSE</button>
              <button disabled={off} onClick={() => run("Reset", () => post("/api/simulation/reset"))}>RESET</button>
            </div>
          </section>
          <section>
            <label>EMERGENCY TEST</label>
            <div className="row">
              <button disabled={off || s?.closed_nodes.includes("gate-e")} onClick={() => run("Emergency", () => post("/api/simulation/emergency", { kind: "gate-failure", node_id: "gate-e" }))}>GATE E</button>
              <button disabled={off || s?.closed_nodes.includes("j-c")} onClick={() => run("Emergency", () => post("/api/simulation/emergency", { kind: "fire", node_id: "j-c" }))}>FIRE</button>
            </div>
            {s?.closed_nodes.length ? s.closed_nodes.map(id => (
              <button key={id} disabled={off} onClick={() => run("Clear", () => post("/api/simulation/emergency/clear", { node_id: id }))}>CLEAR {id.toUpperCase()}</button>
            )) : <p className="muted">No active incidents.</p>}
            {(s?.closed_nodes.length ?? 0) > 1 && <button disabled={off} onClick={() => run("Clear", () => post("/api/simulation/emergency/clear"))}>CLEAR ALL</button>}
          </section>
          <section>
            <label>GEO CONTEXT (OpenStreetMap, on demand)</label>
            <p>Venue: {snap.venue.name}</p>
            <p>Lat/Lon: {snap.venue.latitude.toFixed(4)}, {snap.venue.longitude.toFixed(4)}</p>
            <button disabled={off} onClick={loadGeo}>{busy === "Geo context" ? "LOADING…" : "LOAD PUBLIC GEO CONTEXT"}</button>
            {geo && <p className="muted">{geo.error ? `Unavailable: ${geo.error}` : `${geo.features?.length ?? 0} features loaded (fetched ${new Date().toLocaleTimeString()}).`}<br />{geo.attribution}</p>}
            <p className="muted">Static public map data only. No live traffic, satellite or incident feed is connected.</p>
          </section>
        </aside>
        <div className="center">
          <div className="metrics">
            {([["PEOPLE", s?.people_inside], ["MOVING", s?.active_agents], ["STRANDED", s?.stranded_agents], ["EXITED", s?.total_exited], ["REROUTES", s?.reroutes], ["RISK", Math.round(s?.risk_score ?? 0)]] as const).map(([k, v]) => (
              <div className="metric" key={k}><small>{k}</small><strong>{v ?? 0}</strong></div>
            ))}
          </div>
          <div className="map">
            <div className="grid" />
            {edges.map(e => {
              const a = nodes.find(n => n.id === e.source), b = nodes.find(n => n.id === e.target);
              if (!a || !b) return null;
              const cls = e.status === "emergency-closed" ? "closed" : e.density > 0.65 ? "hot" : "";
              return <div key={e.id} className={"edge " + cls} title={`${e.id}: ${(e.density * 100).toFixed(0)}% · ${e.status}`}
                style={{ left: a.x + "%", top: a.y + "%", width: Math.hypot(b.x - a.x, b.y - a.y) + "%", transform: `rotate(${Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI}deg)` }} />;
            })}
            {nodes.map(n => {
              const lz = liveZones.find(z => z.zone_id === n.id);
              return (
                <div key={n.id} className={"node " + n.kind + (lz ? " live " + lz.risk_level.toLowerCase() : "")} style={{ left: n.x + "%", top: n.y + "%" }}
                  title={lz ? `${n.label}: LIVE camera count ${lz.people} (${lz.status})` : `${n.label}: simulated ${n.occupancy}/${n.capacity}`}>
                  <span /><small>{n.label} ({n.occupancy} sim){lz && <em> · {lz.status} {lz.people} real</em>}</small>
                </div>
              );
            })}
            <div className="maptitle">VENUE GRAPH · SIMULATED AGENTS{liveZones.length ? " · LIVE CAMERA ZONES OUTLINED" : ""}</div>
          </div>
          <LiveZone nodes={nodes} live={liveZones} />
          <div className="timeline">Simulation time: {s?.sim_time_min.toFixed(1)} min · Status: {s?.status} · Inside: {s?.people_inside} · Waiting to exit: {s?.waiting_to_exit}</div>
        </div>
        <aside className="right">
          <section><label>RISK ENGINE (deterministic)</label><div className={"risk " + (s?.risk_level ?? "LOW").toLowerCase()}>{s?.risk_level} <b>{Math.round(s?.risk_score ?? 0)}/100</b></div></section>
          <section><label>BOTTLENECKS</label>{s?.bottlenecks.length ? <ul>{s.bottlenecks.map(x => <li key={x}>{x}</li>)}</ul> : <p>All monitored corridors are below threshold.</p>}</section>
          <section><label>LIVE ZONES (real camera counts)</label>
            {liveZones.length ? liveZones.map(z => (
              <p key={z.zone_id} className="muted"><span className={"lvl " + z.risk_level.toLowerCase()}>● {z.status}</span> {nodes.find(n => n.id === z.zone_id)?.label ?? z.zone_id}: <b>{z.people}</b> people · {z.risk_level} {Math.round(z.risk_score)}/100{z.status === "STALE" ? " (no fresh count)" : ""}</p>
            )) : <p className="muted">No live camera zone. Start live counting below the venue graph. Everything else on this page is simulated.</p>}
          </section>
          <section><label>CAMERAS (registered sources)</label>
            {cameras === null ? <p className="muted">Loading…</p> : cameras.length ? cameras.map(c => <p className="muted" key={c.id}>● {c.name} · {c.status ?? "unknown"} · {c.configured ? "endpoint set" : "metadata only"}</p>) : <p className="muted">No authorized camera sources configured.</p>}
          </section>
          <section><label>INCIDENTS</label>{s?.events.length ? <ul>{s.events.slice(-5).map((x, i) => <li key={i}>{x.type} · {x.node_id ?? "all"} · t={x.time}</li>)}</ul> : <p>No incidents recorded.</p>}</section>
          <section><label>DECISION SUPPORT (rule-based)</label><DecisionSupport active={connected} /></section>
          <section><label>HISTORY</label>
            <button disabled={!!busy} onClick={loadHistory}>{busy === "History" ? "LOADING…" : history ? "REFRESH" : "LOAD HISTORY"}</button>
            {history && (history.length ? <ul>{history.map(h => <li key={h.id}>t={h.sim_time_min.toFixed(1)}m · {h.risk_level} {Math.round(h.risk_score)} · {new Date(h.created_at).toLocaleTimeString()}</li>)}</ul> : <p className="muted">No saved snapshots yet. Start a run; one is stored every few seconds.</p>)}
          </section>
        </aside>
      </main>
      )}
    </div>
  );
}
