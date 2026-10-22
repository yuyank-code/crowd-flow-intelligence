from __future__ import annotations

from sqlalchemy import delete, func, select

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


async def prune(simulation_id: str, keep: int) -> int:
    """Delete all but the newest `keep` rows for a simulation. Returns rows removed."""
    async with SessionLocal() as session:
        cutoff = (await session.execute(
            select(SimulationSnapshot.id).where(SimulationSnapshot.simulation_id == simulation_id)
            .order_by(SimulationSnapshot.id.desc()).offset(keep).limit(1))).scalar()
        if cutoff is None:
            return 0
        res = await session.execute(delete(SimulationSnapshot).where(
            SimulationSnapshot.simulation_id == simulation_id, SimulationSnapshot.id <= cutoff))
        await session.commit()
        return res.rowcount or 0


async def count(simulation_id: str) -> int:
    async with SessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(SimulationSnapshot)
                .where(SimulationSnapshot.simulation_id == simulation_id))).scalar_one()


async def history(simulation_id: str | None = None, limit: int = 50, offset: int = 0,
                  min_risk: float | None = None, risk_level: str | None = None) -> list[dict]:
    """Newest first. Ordering is by insertion id (monotonic); created_at is wall-clock UTC, sim_time_min is simulated time."""
    safe_limit = max(1, min(limit, 500))
    async with SessionLocal() as session:
        stmt = select(SimulationSnapshot)
        if simulation_id:
            stmt = stmt.where(SimulationSnapshot.simulation_id == simulation_id)
        if min_risk is not None:
            stmt = stmt.where(SimulationSnapshot.risk_score >= min_risk)
        if risk_level:
            stmt = stmt.where(SimulationSnapshot.risk_level == risk_level.upper())
        stmt = stmt.order_by(SimulationSnapshot.id.desc()).offset(max(0, offset)).limit(safe_limit)
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
