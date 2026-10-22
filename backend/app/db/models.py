from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
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


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(16))              # rtsp | onvif | usb
    zone_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)   # never contains credentials
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    local_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credential_enc: Mapped[str | None] = mapped_column(Text, nullable=True)    # Fernet token; never returned by the API
    playback_path: Mapped[str | None] = mapped_column(String(120), nullable=True)  # path on the media gateway
    status: Mapped[str] = mapped_column(String(24), default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=False)    # stored only; no analytics exist yet
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CameraAudit(Base):
    __tablename__ = "camera_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(String(200), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
