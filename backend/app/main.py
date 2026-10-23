import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .api.routes.geospatial import router as geospatial_router
from .api.routes.cctv import router as cctv_router
from .core.config import settings
from .core.security import (client_ip, geo_limiter, live_limiter, operator_guard, operator_limiter, require_operator, origin_allowed, parse_limiter,
                            ws_connections)
from .db.database import close_db, init_db
from .db.repository import history, prune, save_snapshot
from .live.store import store as live_store
from .cctv import repository as camera_repo
from .engine import CrowdEngine, Scenario, build_demo_venue
from .ai.service import explain as explain_snapshot, interpret as interpret_scenario

venue = build_demo_venue()
engine = CrowdEngine(venue, max_agents=settings.max_agents)
log = logging.getLogger("crowdflow")
SIMULATION_ID = venue.id


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # auth uses the X-API-Key header, never cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)
app.include_router(geospatial_router, dependencies=[Depends(geo_limiter)])
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
    kind: str = Field(min_length=1, max_length=40)
    node_id: str = Field(min_length=1, max_length=64)


class ClearRequest(BaseModel):
    node_id: str | None = Field(default=None, max_length=64)


class TextRequest(BaseModel):
    text: str = Field(default="", max_length=2000)


def full_snapshot() -> dict:
    """Simulation snapshot plus real camera-derived zones (clearly separate under "live")."""
    return engine.snapshot() | {"live": live_store.snapshot()}


class ObservationRequest(BaseModel):
    camera_id: str = Field(min_length=1, max_length=36)
    zone_id: str = Field(min_length=1, max_length=64)
    people: int = Field(ge=0, le=2000)
    view_area_m2: float = Field(gt=0, le=10000)


@app.post("/api/live/observations", dependencies=[Depends(require_operator), Depends(live_limiter)])
async def post_observation(req: ObservationRequest):
    """A browser (or other detector) reports how many people a registered camera sees in a venue zone."""
    if req.zone_id not in venue.nodes:
        raise HTTPException(status_code=404, detail="venue_node_not_found")
    if await camera_repo.get(req.camera_id) is None:
        raise HTTPException(status_code=404, detail="camera_not_found")
    live_store.record(req.zone_id, req.camera_id, req.people, req.view_area_m2)
    return {"live": live_store.snapshot()}


@app.get("/api/live")
def get_live():
    return {"live": live_store.snapshot()}


@app.delete("/api/live/{zone_id}", status_code=204, dependencies=[Depends(require_operator), Depends(operator_limiter)])
def clear_live_zone(zone_id: str):
    live_store.forget_zone(zone_id)


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version, "simulation": engine.state.status}


@app.get("/api/venues")
def venues():
    return [{"id": venue.id, "name": venue.name, "latitude": venue.latitude, "longitude": venue.longitude}]


@app.get("/api/venues/{venue_id}")
def venue_detail(venue_id: str):
    if venue_id != venue.id:
        raise HTTPException(status_code=404, detail="venue_not_found")
    return full_snapshot()


@app.get("/api/simulation")
def simulation():
    return full_snapshot()


@app.get("/api/simulation/history")
async def simulation_history(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0, le=1_000_000),
                             min_risk: float | None = Query(default=None, ge=0, le=100),
                             risk_level: str | None = Query(default=None, pattern="^(?i:low|moderate|high|critical)$")):
    return {"items": await history(SIMULATION_ID, limit, offset, min_risk, risk_level), "limit": limit, "offset": offset}


@app.post("/api/simulation/scenario", dependencies=operator_guard)
def set_scenario(req: ScenarioRequest):
    engine.scenario = Scenario(req.crowd_size, req.arrival_rate, req.exit_rate, req.entry_distribution)
    engine.reset()
    return engine.snapshot()


@app.post("/api/simulation/start", dependencies=operator_guard)
def start():
    engine.start()
    return {"status": engine.state.status}


@app.post("/api/simulation/pause", dependencies=operator_guard)
def pause():
    engine.pause()
    return {"status": engine.state.status}


@app.post("/api/simulation/reset", dependencies=operator_guard)
def reset():
    engine.reset()
    return engine.snapshot()


@app.post("/api/simulation/emergency", dependencies=operator_guard)
def emergency(req: EmergencyRequest):
    if req.node_id not in venue.nodes:
        raise HTTPException(status_code=404, detail="venue_node_not_found")
    engine.emergency(req.kind, req.node_id)
    return engine.snapshot()


@app.post("/api/simulation/emergency/clear", dependencies=operator_guard)
def clear_emergency(req: ClearRequest | None = None):
    node_id = req.node_id if req else None
    if node_id is not None and node_id not in engine.closed_nodes:
        raise HTTPException(status_code=404, detail="node_not_closed")
    engine.clear_emergency(node_id)
    return engine.snapshot()


@app.post("/api/scenarios/parse", dependencies=[Depends(parse_limiter)])
def parse_scenario(req: TextRequest):
    result = interpret_scenario(req.text)
    return {"crowd_size": result.crowd_size, "arrival_rate": result.arrival_rate, "exit_rate": result.exit_rate,
            "entry_distribution": result.entry_distribution,
            "explanation": "Operator language converted to structured simulation inputs. Risk and routing remain deterministic."}


@app.post("/api/scenarios/interpret", dependencies=[Depends(parse_limiter)])
def interpret(req: TextRequest):
    result = interpret_scenario(req.text)
    return {"crowd_size": result.crowd_size, "arrival_rate": result.arrival_rate, "exit_rate": result.exit_rate,
            "entry_distribution": result.entry_distribution, "assumptions": result.assumptions,
            "explanation": "Scenario interpretation is deterministic. Safety scoring remains in the risk engine."}


@app.get("/api/decision-support")
def decision_support():
    return explain_snapshot(engine.snapshot())


async def simulation_loop():
    """Tick the engine. Persistence is throttled and failures never stop the simulation."""
    last_saved = 0.0
    while True:
        await asyncio.sleep(1 / max(.5, settings.simulation_hz))
        try:
            snapshot = engine.tick(.5)
        except Exception:  # keep the loop alive; surface the problem in logs
            log.exception("simulation tick failed")
            continue
        now = time.monotonic()
        if engine.state.status == "running" and now - last_saved >= settings.snapshot_interval_sec:
            last_saved = now
            try:
                await save_snapshot(SIMULATION_ID, snapshot)
                await prune(SIMULATION_ID, settings.history_retention_rows)
            except Exception:
                log.exception("snapshot persistence failed")


@app.websocket("/ws/simulation")
async def ws_simulation(ws: WebSocket):
    if not origin_allowed(ws):
        await ws.close(code=1008)  # policy violation
        return
    ip = client_ip(ws)
    if not ws_connections.acquire(ip):
        await ws.close(code=1013)  # try again later
        return
    try:
        await ws.accept()
        while True:
            await ws.send_json(full_snapshot())
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        ws_connections.release(ip)
