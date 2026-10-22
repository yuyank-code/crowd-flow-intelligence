"""Camera registration, status and capability logic (no HTTP concerns)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core.config import settings
from app.db.models import Camera

from . import repository as repo
from . import streams
from .adapters import ADAPTERS
from .schemas import CameraCreate, CameraOut
from .security import decrypt_credentials, encrypt_credentials, validate_endpoint


def capabilities(cam: Camera) -> dict:
    base = ADAPTERS[cam.source_type].capabilities
    return {
        # preview needs a gateway path; we can't offer it for USB until a local agent exists
        "preview": cam.source_type != "usb" and streams.gateway_configured() and bool(cam.playback_path),
        "snapshot": base.snapshot, "ptz": base.ptz, "discovery": base.discovery,
        "playback_formats": ["hls"] if streams.gateway_configured() else [],
        "source_formats": list(base.formats),
    }


def to_out(cam: Camera) -> dict:
    host = None
    if cam.endpoint:
        p = urlsplit(cam.endpoint)
        host = f"{p.hostname}:{p.port}" if p.port else p.hostname
    return CameraOut(
        id=cam.id, name=cam.name, source_type=cam.source_type, zone_id=cam.zone_id, endpoint_host=host,
        status=cam.status, last_seen_at=cam.last_seen_at, last_error_code=cam.last_error_code,
        capabilities=capabilities(cam), has_credentials=bool(cam.credential_enc),
        configured=bool(cam.endpoint), created_at=cam.created_at, updated_at=cam.updated_at,
    ).model_dump(mode="json") | {"stream_active": cam.id in streams.active()}


async def register(data: CameraCreate) -> Camera:
    endpoint = validate_endpoint(data.source_type, data.endpoint) if data.endpoint else None
    cred = encrypt_credentials(data.username, data.password.get_secret_value()) if data.username and data.password else None
    now = datetime.now(timezone.utc)
    cam = Camera(id=str(uuid.uuid4()), name=data.name.strip(), source_type=data.source_type, zone_id=data.zone_id,
                 endpoint=endpoint, device_label=data.device_label, local_agent_id=data.local_agent_id,
                 credential_enc=cred, playback_path=data.playback_path, status="unknown",
                 created_at=now, updated_at=now)
    await repo.add(cam)
    await repo.audit(cam.id, "create", f"{cam.source_type} '{cam.name}'")
    return cam


async def run_test(cam: Camera):
    adapter = ADAPTERS[cam.source_type]
    result = await adapter.test(cam.endpoint, decrypt_credentials(cam.credential_enc), settings.cctv_timeout_sec)
    cam.status, cam.last_error_code = result.status, result.code
    if result.status == "online":
        cam.last_seen_at = datetime.now(timezone.utc)
    cam = await repo.save(cam)
    await repo.audit(cam.id, "test", f"{result.status} {result.code or ''}".strip())
    return cam, result
