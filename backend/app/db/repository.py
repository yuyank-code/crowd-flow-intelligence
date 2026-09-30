from __future__ import annotations
from sqlalchemy import select
from app.db.database import SessionLocal
from app.db.models import SimulationSnapshot

async def save_snapshot(simulation_id: str, snapshot: dict) -> None:
    state = snapshot.get("state", {})
    async with SessionLocal() as session:
        session.add(SimulationSnapshot(
            simulation_id=simulation_id,
            sim_time_min=float(state.get("sim_time_min", 0)),
            risk_score=float(state.get("risk_score", 0)),
            risk_level=str(state.get("risk_level", "LOW")),
            payload=snapshot,
        ))
        await session.commit()

async def history(simulation_id: str | None = None, limit: int = 50) -> list[dict]:
    async with SessionLocal() as session:
        stmt = select(SimulationSnapshot).order_by(SimulationSnapshot.id.desc()).limit(max(1, min(limit, 500)))
        if simulation_id:
            stmt = stmt.where(SimulationSnapshot.simulation_id == simulation_id)
        rows = (await session.execute(stmt)).scalars().all()
        return [{"id": r.id, "simulation_id": r.simulation_id, "created_at": r.created_at.isoformat(), "sim_time_min": r.sim_time_min, "risk_score": r.risk_score, "risk_level": r.risk_level, "snapshot": r.payload} for r in rows]
