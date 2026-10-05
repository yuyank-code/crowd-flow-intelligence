import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .api.routes.geospatial import router as geospatial_router
from .api.routes.cctv import router as cctv_router
from .core.config import settings
from .db.database import close_db, init_db
from .db.repository import history, save_snapshot
from .engine import CrowdEngine, Scenario, build_demo_venue
from .ai.service import explain as explain_snapshot, interpret as interpret_scenario

venue = build_demo_venue()
engine = CrowdEngine(venue)
SIMULATION_ID = venue.id


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()
    await close_db()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(geospatial_router)
app.include_router(cctv_router)


class ScenarioRequest(BaseModel):
    crowd_size: int = Field(20000, ge=0, le=1000000)
    arrival_rate: int = Field(600, ge=0, le=100000)
    exit_rate: int = Field(800, ge=0, le=100000)
    entry_distribution: dict[str, float] = Field(
        default_factory=lambda: {"gate-e": .55, "gate-w": .30, "gate-s": .15}
    )

    @field_validator("entry_distribution")
    @classmethod
    def validate_distribution(cls, value: dict[str, float]):
        if not value or any(v < 0 for v in value.values()):
            raise ValueError("entry_distribution must contain non-negative fractions")
        total = sum(value.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError("entry_distribution fractions must sum to 1.0")
        return value


class EmergencyRequest(BaseModel):
    kind: str
    node_id: str


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version, "simulation": engine.state.status}


@app.get("/api/venues")
def venues():
    return [{"id": venue.id, "name": venue.name, "latitude": venue.latitude, "longitude": venue.longitude}]


@app.get("/api/venues/{venue_id}")
def venue_detail(venue_id: str):
    if venue_id != venue.id:
        return {"error": "venue_not_found"}
    return engine.snapshot()


@app.get("/api/simulation")
def simulation():
    return engine.snapshot()


@app.get("/api/simulation/history")
async def simulation_history(limit: int = 50):
    return {"items": await history(SIMULATION_ID, limit)}


@app.post("/api/simulation/scenario")
def set_scenario(req: ScenarioRequest):
    engine.scenario = Scenario(req.crowd_size, req.arrival_rate, req.exit_rate, req.entry_distribution)
    engine.reset()
    return engine.snapshot()


@app.post("/api/simulation/start")
def start():
    engine.start()
    return {"status": engine.state.status}


@app.post("/api/simulation/pause")
def pause():
    engine.pause()
    return {"status": engine.state.status}


@app.post("/api/simulation/reset")
def reset():
    engine.reset()
    return engine.snapshot()


@app.post("/api/simulation/emergency")
def emergency(req: EmergencyRequest):
    engine.emergency(req.kind, req.node_id)
    return engine.snapshot()


@app.post("/api/simulation/emergency/clear")
def clear_emergency():
    engine.clear_emergency()
    return engine.snapshot()


def parse_operator_scenario(text: str) -> dict:
    import re
    t = text.lower().replace(",", "")
    crowd = 20000
    match = re.search(r"(\d+(?:\.\d+)?)\s*(million|m|thousand|k)?\s*(?:people|persons|crowd)?", t)
    if match:
        value = float(match.group(1))
        unit = match.group(2) or ""
        if unit in ("million", "m"):
            value *= 1_000_000
        elif unit in ("thousand", "k"):
            value *= 1_000
        crowd = max(0, min(1_000_000, int(value)))

    arrival = 600
    match = re.search(r"(?:arriv(?:al|ing)|entry|entering)[^0-9]{0,20}(\d+)", t)
    if match:
        arrival = max(0, min(100_000, int(match.group(1))))

    exit_rate = 800
    match = re.search(r"(?:exit|exiting|leav(?:e|ing))[^0-9]{0,20}(\d+)", t)
    if match:
        exit_rate = max(0, min(100_000, int(match.group(1))))

    return {
        "crowd_size": crowd,
        "arrival_rate": arrival,
        "exit_rate": exit_rate,
        "entry_distribution": {"gate-e": .55, "gate-w": .30, "gate-s": .15},
        "explanation": "Operator language converted to structured simulation inputs. Risk and routing remain deterministic.",
    }


@app.post("/api/scenarios/parse")
def parse_scenario(payload: dict):
    return parse_operator_scenario(str(payload.get("text", "")))


@app.post("/api/scenarios/interpret")
def interpret(payload: dict):
    result = interpret_scenario(str(payload.get("text", "")))
    return {"crowd_size": result.crowd_size, "arrival_rate": result.arrival_rate, "exit_rate": result.exit_rate,
            "entry_distribution": result.entry_distribution, "assumptions": result.assumptions,
            "explanation": "Scenario interpretation is deterministic. Safety scoring remains in the risk engine."}


@app.get("/api/decision-support")
def decision_support():
    return explain_snapshot(engine.snapshot())


async def simulation_loop():
    while True:
        await asyncio.sleep(1 / max(.5, settings.simulation_hz))
        snapshot = engine.tick(.5)
        if engine.state.status == "running":
            await save_snapshot(SIMULATION_ID, snapshot)


@app.websocket("/ws/simulation")
async def ws_simulation(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(engine.snapshot())
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, RuntimeError):
        return
