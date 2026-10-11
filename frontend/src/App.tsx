import { useEffect, useMemo, useState } from "react";
import DecisionSupport from "./components/DecisionSupport";

type Node = { id: string; label: string; kind: string; x: number; y: number; capacity: number; occupancy: number };
type Edge = { id: string; source: string; target: string; capacity_per_min: number; density: number; status: string };
type Snapshot = {
  venue: { id?: string; name: string; latitude: number; longitude: number };
  state: {
    status: string; sim_time_min: number; people_inside: number; total_entered: number; total_exited: number;
    risk_score: number; risk_level: string; bottlenecks: string[]; events: Array<{type:string;node_id?:string|null;time:number}>;
    active_agents: number; stranded_agents?: number; reroutes: number;
  };
  nodes: Node[];
  edges: Edge[];
};
type HistoryItem = { id: number; created_at: string; sim_time_min: number; risk_score: number; risk_level: string; snapshot: Snapshot };

const API = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}

function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [scenario, setScenario] = useState("30,000 people arriving for an evening concert");
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [geo, setGeo] = useState<any>(null);
  const [cameras, setCameras] = useState<any[]>([]);
  const [interpretation, setInterpretation] = useState<any>(null);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);

  const load = async () => {
    const snapshot = await requestJson<Snapshot>(API + "/api/simulation");
    setSnap(snapshot);
    return snapshot;
  };

  useEffect(() => {
    let stopped = false;
    let socket: WebSocket | undefined;
    let reconnectTimer: number | undefined;
    let attempt = 0;

    void load().catch((e) => setError(e instanceof Error ? e.message : "Unable to load simulation"));
    requestJson<{items?: any[]}>(API + "/api/cctv/sources")
      .then((result) => setCameras(result.items || []))
      .catch(() => setCameras([]));

    const wsBase = (import.meta.env.VITE_WS_BASE_URL || API.replace(/^http/, "ws")).replace(/\/$/, "");
    const connect = () => {
      if (stopped) return;
      try {
        socket = new WebSocket(wsBase + "/ws/simulation");
        socket.onopen = () => { setConnected(true); attempt = 0; };
        socket.onmessage = (event) => {
          try { setSnap(JSON.parse(event.data) as Snapshot); }
          catch { setError("Received an invalid live simulation update."); }
        };
        socket.onclose = () => {
          setConnected(false);
          if (!stopped) {
            const delay = Math.min(15000, 1000 * (2 ** Math.min(attempt, 4)));
            attempt += 1;
            reconnectTimer = window.setTimeout(connect, delay);
          }
        };
        socket.onerror = () => socket?.close();
      } catch {
        setConnected(false);
      }
    };
    connect();

    return () => {
      stopped = true;
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  const act = async (path: string, body?: unknown) => {
    setBusy(true);
    setError("");
    try {
      await requestJson(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const interpret = async () => {
    const result = await requestJson<any>(API + "/api/scenarios/interpret", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: scenario }),
    });
    setInterpretation(result);
    return result;
  };

  const runScenario = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await interpret();
      await requestJson(API + "/api/simulation/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scenario could not be applied");
    } finally {
      setBusy(false);
    }
  };

  const loadGeo = async () => {
    if (!snap) return;
    setError("");
    try {
      const result = await requestJson<any>(API + "/api/geo/context", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: snap.venue.latitude, lon: snap.venue.longitude, radius_m: 1000 }),
      });
      setGeo(result);
      if (result.error) setError(String(result.error));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Geospatial context is unavailable");
    }
  };

  const loadHistory = async () => {
    setError("");
    try {
      const result = await requestJson<{items: HistoryItem[]}>(API + "/api/simulation/history?limit=25");
      setHistoryItems(result.items || []);
      setHistoryOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "History could not be loaded");
    }
  };

  const nodes = useMemo(() => snap?.nodes || [], [snap]);
  const edges = snap?.edges || [];

  return <div className="app">
    <header>
      <div><b>CROWD FLOW</b><span> INTELLIGENCE</span><small>Venue operations &amp; geospatial decision support</small></div>
      <div className="status">● {connected ? "LIVE" : "RECONNECTING / OFFLINE"}</div>
    </header>
    {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError("")}>DISMISS</button></div>}
    <main>
      <aside>
        <section>
          <label>SCENARIO ASSISTANT</label>
          <textarea value={scenario} onChange={(e) => setScenario(e.target.value)} />
          <button disabled={busy} onClick={runScenario}>{busy ? "WORKING…" : "INTERPRET & SIMULATE"}</button>
          {interpretation && <div className="muted">
            Interpreted: {Number(interpretation.crowd_size).toLocaleString()} people · {interpretation.arrival_rate}/min arrival · {interpretation.exit_rate}/min exit
            {interpretation.assumptions?.length > 0 && <ul>{interpretation.assumptions.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>}
          </div>}
          <p className="muted">Text parsing is deterministic; risk and routing are calculated by the simulation engine.</p>
        </section>
        <section>
          <label>RUN CONTROLS</label>
          <div className="row">
            <button disabled={busy} onClick={() => void act("/api/simulation/start")}>START</button>
            <button disabled={busy} onClick={() => void act("/api/simulation/pause")}>PAUSE</button>
            <button disabled={busy} onClick={() => void act("/api/simulation/reset")}>RESET</button>
          </div>
        </section>
        <section>
          <label>EMERGENCY EXERCISE</label>
          <div className="row">
            <button disabled={busy} onClick={() => void act("/api/simulation/emergency", { kind: "gate-failure", node_id: "gate-e" })}>GATE E</button>
            <button disabled={busy} onClick={() => void act("/api/simulation/emergency", { kind: "fire", node_id: "j-c" })}>FIRE</button>
          </div>
          <button disabled={busy} onClick={() => void act("/api/simulation/emergency/clear")}>CLEAR INCIDENT</button>
        </section>
        <section>
          <label>GEO CONTEXT</label>
          <p>Venue: {snap?.venue.name || "—"}</p>
          <p>Lat/Lon: {snap ? `${snap.venue.latitude.toFixed(4)}, ${snap.venue.longitude.toFixed(4)}` : "—"}</p>
          <button disabled={!snap || busy} onClick={loadGeo}>LOAD PUBLIC GEO CONTEXT</button>
          {geo && <p className="muted">{geo.error || `${geo.features?.length || 0} nearby public features loaded`}<br />{geo.attribution}</p>}
          <p className="muted">Provider-backed public data only; no unrestricted satellite or CCTV access is assumed.</p>
        </section>
      </aside>

      <div className="center">
        <div className="metrics">
          {[
            ["PEOPLE INSIDE", snap?.state.people_inside || 0],
            ["ACTIVE AGENTS", snap?.state.active_agents || 0],
            ["STRANDED", snap?.state.stranded_agents || 0],
            ["RISK SCORE", Math.round(snap?.state.risk_score || 0)],
          ].map(([key, value]) => <div className="metric" key={key}><small>{key}</small><strong>{value}</strong></div>)}
        </div>
        <div className="map">
          <div className="grid" />
          {edges.map((edge) => {
            const a = nodes.find((node) => node.id === edge.source);
            const b = nodes.find((node) => node.id === edge.target);
            if (!a || !b) return null;
            return <div key={edge.id} className={"edge " + (edge.density >= 0.65 ? "hot" : "") + (edge.status === "emergency-closed" ? " closed" : "")}
              style={{ left: a.x + "%", top: a.y + "%", width: Math.hypot(b.x - a.x, b.y - a.y) + "%", transform: `rotate(${Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI}deg)` }} />;
          })}
          {nodes.map((node) => <div key={node.id} className={"node " + node.kind} style={{ left: node.x + "%", top: node.y + "%" }} title={node.label}>
            <span /><small>{node.label}<br />{node.occupancy.toLocaleString()}</small>
          </div>)}
          <div className="maptitle">VENUE DIGITAL TWIN · SIMULATED AGENTS</div>
        </div>
        <div className="timeline">
          Simulation time: {snap?.state.sim_time_min.toFixed(1) || "0.0"} min · Status: {snap?.state.status || "standby"} · Entered: {snap?.state.total_entered || 0} · Exited: {snap?.state.total_exited || 0} · Reroutes: {snap?.state.reroutes || 0}
        </div>
        <section className="history-section">
          <div className="history-heading"><label>SIMULATION HISTORY</label><button onClick={() => historyOpen ? setHistoryOpen(false) : void loadHistory()}>{historyOpen ? "HIDE HISTORY" : "LOAD HISTORY"}</button></div>
          {historyOpen && (historyItems.length ? <div className="history-list">{historyItems.map((item) => <div className="history-item" key={item.id}>
            <span>#{item.id} · {new Date(item.created_at).toLocaleString()}</span>
            <span>{item.sim_time_min.toFixed(1)} min · {item.risk_level} ({Math.round(item.risk_score)})</span>
            <span>Inside: {item.snapshot?.state?.people_inside ?? "—"}</span>
          </div>) : <p className="muted">No snapshots saved yet. Start the simulation and check again.</p>)}
        </section>
      </div>

      <aside className="right">
        <section><label>RISK ENGINE</label><div className={"risk " + (snap?.state.risk_level || "LOW").toLowerCase()}>{snap?.state.risk_level || "LOW"} <b>{Math.round(snap?.state.risk_score || 0)}/100</b></div><p className="muted">Deterministic heuristic, not a certified safety prediction.</p></section>
        <section><label>BOTTLENECKS</label>{snap?.state.bottlenecks.length ? <ul>{snap.state.bottlenecks.map((id) => <li key={id}>{id}</li>)}</ul> : <p>All monitored corridors are below the configured threshold.</p>}</section>
        <section><label>CCTV SOURCES</label>{cameras.length ? cameras.map((camera) => <p className="muted" key={camera.id}>● {camera.name} · {camera.configured ? "configured" : "metadata only"}</p>) : <p className="muted">No authorized camera sources configured. Video analytics are not implemented.</p>}</section>
        <section><label>INCIDENTS</label>{snap?.state.events.length ? <ul>{snap.state.events.slice(-5).map((event, i) => <li key={i}>{event.type} · {event.node_id || "system"} · {event.time} min</li>)}</ul> : <p>No incidents recorded.</p>}</section>
        <section><label>OPERATOR NOTE</label><p>Closures disable adjacent graph edges. Agents without an available route remain counted and are marked stranded until a route becomes available.</p></section>
        <section><label>DECISION SUPPORT</label><DecisionSupport api={API} /></section>
      </aside>
    </main>
  </div>;
}

export default App;
