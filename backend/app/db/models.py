from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class SimulationSnapshot(Base):
    __tablename__ = "simulation_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sim_time_min: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(32), default="LOW")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
