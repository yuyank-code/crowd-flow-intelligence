from __future__ import annotations

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Camera, CameraAudit


async def add(cam: Camera) -> Camera:
    async with SessionLocal() as s:
        s.add(cam)
        await s.commit()
    return cam


async def get(camera_id: str) -> Camera | None:
    async with SessionLocal() as s:
        return await s.get(Camera, camera_id)


async def get_by_playback_path(path: str) -> Camera | None:
    async with SessionLocal() as s:
        return (await s.execute(select(Camera).where(Camera.playback_path == path).limit(1))).scalars().first()


async def list_all() -> list[Camera]:
    async with SessionLocal() as s:
        return list((await s.execute(select(Camera).order_by(Camera.created_at))).scalars())


async def save(cam: Camera) -> Camera:
    async with SessionLocal() as s:
        merged = await s.merge(cam)
        await s.commit()
        return merged


async def remove(camera_id: str) -> bool:
    async with SessionLocal() as s:
        res = await s.execute(delete(Camera).where(Camera.id == camera_id))
        await s.commit()
        return bool(res.rowcount)


async def audit(camera_id: str, action: str, detail: str = "") -> None:
    async with SessionLocal() as s:
        s.add(CameraAudit(camera_id=camera_id, action=action, detail=detail[:200]))
        await s.commit()


async def audit_log(camera_id: str, limit: int = 50) -> list[dict]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(CameraAudit).where(CameraAudit.camera_id == camera_id)
                .order_by(CameraAudit.id.desc()).limit(limit))).scalars()
        return [{"action": r.action, "detail": r.detail, "at": r.at.isoformat()} for r in rows]
