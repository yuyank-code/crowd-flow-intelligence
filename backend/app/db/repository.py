from __future__ import annotations

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import SimulationSnapshot


async def save_snapshot(simulation_id: str, snapshot: dict) -> None:
    state = snapshot.get("state", {})
    async with SessionLocal() as session:
        session.add(
            SimulationSnapshot(
                simulation_id=simulation_id,
                sim_time_min=float(state.get("sim_time_min", 0)),
                risk_score=float(state.get("risk_score", 0)),
                risk_level=str(state.get("risk_level", "LOW")),
                payload=snapshot,
            )
        )
        await session.commit()


async def history(simulation_id: str | None = None, limit: int = 50) -> list[dict]:
    safe_limit = max(1, min(limit, 500))
    async with SessionLocal() as session:
        stmt = select(SimulationSnapshot)
        if simulation_id:
            stmt = stmt.where(SimulationSnapshot.simulation_id == simulation_id)
        stmt = stmt.order_by(SimulationSnapshot.id.desc()).limit(safe_limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": row.id,
                "simulation_id": row.simulation_id,
                "created_at": row.created_at.isoformat(),
                "sim_time_min": row.sim_time_min,
                "risk_score": row.risk_score,
                "risk_level": row.risk_level,
                "snapshot": row.payload,
            }
            for row in rows
        ]
