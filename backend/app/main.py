import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .core.config import settings
from .engine import CrowdEngine, Scenario, build_demo_venue

venue = build_demo_venue()
engine = CrowdEngine(venue)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()

app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ScenarioRequest(BaseModel):
    crowd_size: int = Field(20000, ge=0, le=1000000)
    arrival_rate: int = Field(600, ge=0, le=100000)
    exit_rate: int = Field(800, ge=0, le=100000)
    entry_distribution: dict[str,float] = Field(default_factory=lambda: {"gate-e":.55,"gate-w":.30,"gate-s":.15})

class EmergencyRequest(BaseModel):
    kind: str
    node_id: str

@app.get("/health")
def health(): return {"status":"ok","version":settings.app_version,"simulation":engine.state.status}

@app.get("/api/venues")
def venues(): return [{"id":venue.id,"name":venue.name,"latitude":venue.latitude,"longitude":venue.longitude}]

@app.get("/api/venues/{venue_id}")
def venue_detail(venue_id: str):
    if venue_id != venue.id: return {"error":"venue_not_found"}
    return engine.snapshot()

@app.get("/api/simulation")
def simulation(): return engine.snapshot()

@app.post("/api/simulation/scenario")
def set_scenario(req: ScenarioRequest):
    engine.scenario = Scenario(req.crowd_size, req.arrival_rate, req.exit_rate, req.entry_distribution)
    engine.reset()
    return engine.snapshot()

@app.post("/api/simulation/start")
def start(): engine.start(); return {"status":engine.state.status}

@app.post("/api/simulation/pause")
def pause(): engine.pause(); return {"status":engine.state.status}

@app.post("/api/simulation/reset")
def reset(): engine.reset(); return engine.snapshot()

@app.post("/api/simulation/emergency")
def emergency(req: EmergencyRequest):
    engine.emergency(req.kind, req.node_id); return engine.snapshot()

@app.post("/api/simulation/emergency/clear")
def clear_emergency(): engine.clear_emergency(); return engine.snapshot()

@app.post("/api/scenarios/parse")
def parse_scenario(payload: dict):
    text = str(payload.get("text","")).lower()
    crowd = 20000
    for token in text.replace(",","").split():
        if token.isdigit(): crowd = int(token); break
    return {"crowd_size":crowd,"arrival_rate":600,"exit_rate":800,"entry_distribution":{"gate-e":.55,"gate-w":.30,"gate-s":.15}, "explanation":"Structured scenario generated from operator text. Deterministic simulation remains the source of risk calculations."}

async def simulation_loop():
    while True:
        await asyncio.sleep(1 / max(.5, settings.simulation_hz))
        engine.tick(.5)

@app.websocket("/ws/simulation")
async def ws_simulation(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(engine.snapshot())
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, RuntimeError):
        return
