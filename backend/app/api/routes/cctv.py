from __future__ import annotations

import hmac

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.cctv import manager, repository as repo, streams
from app.cctv.schemas import CameraCreate, CameraUpdate, PtzCommand
from app.cctv.security import EndpointRejected, SecretStorageUnavailable, verify_playback_token
from app.cctv.service import CCTVAdapterError, health, source_catalog
from app.core.config import settings
from app.live.store import store as live_store
from app.core.security import operator_limiter

router = APIRouter(prefix="/api/cctv", tags=["CCTV"])


def require_operator(x_api_key: str | None = Header(default=None)) -> str:
    """Single shared operator key. Fail-closed: no configured key -> mutating/control routes are disabled."""
    if not settings.operator_api_key:
        raise HTTPException(503, "operator_auth_not_configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.operator_api_key):
        raise HTTPException(401, "operator_key_required")
    return "operator"


async def _camera(camera_id: str):
    cam = await repo.get(camera_id)
    if cam is None:
        raise HTTPException(404, "camera_not_found")
    return cam


def _config_items() -> list[dict]:
    try:
        return [i | {"origin": "config", "status": "unknown"} for i in source_catalog()]
    except CCTVAdapterError as exc:
        raise HTTPException(503, str(exc)) from exc


# ---- read (no secrets are ever returned) ------------------------------------
@router.get("/sources")
async def sources():
    registered = [manager.to_out(c) for c in await repo.list_all()]
    return {"items": _config_items() + registered, "policy": "Only operator-configured or operator-registered sources are used.",
            "gateway_configured": streams.gateway_configured(), "operator_auth_configured": bool(settings.operator_api_key)}


@router.get("/sources/{source_id}")
async def source_detail(source_id: str):
    cam = await repo.get(source_id)
    if cam:
        return manager.to_out(cam) | {"audit": await repo.audit_log(cam.id, 20)}
    for item in _config_items():
        if item["id"] == source_id:
            return item
    raise HTTPException(404, "camera_not_found")


@router.get("/sources/{source_id}/health")
async def source_health(source_id: str):
    cam = await repo.get(source_id)
    if cam:  # stored status from the last explicit test; no probing on a read
        return {"id": cam.id, "status": cam.status, "last_seen_at": cam.last_seen_at, "last_error_code": cam.last_error_code, "probed": False}
    try:
        return await health(source_id)
    except CCTVAdapterError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---- registration / management (operator key required) ----------------------
@router.post("/sources", status_code=201, dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def register_camera(req: CameraCreate):
    try:
        cam = await manager.register(req)
    except EndpointRejected as exc:
        raise HTTPException(422, f"endpoint_rejected: {exc}") from exc
    except SecretStorageUnavailable as exc:
        raise HTTPException(422, f"credential_storage_not_configured: {exc}") from exc
    return manager.to_out(cam)


@router.patch("/sources/{source_id}", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def update_camera(source_id: str, req: CameraUpdate):
    cam = await _camera(source_id)
    changes = req.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(cam, k, v)
    cam = await repo.save(cam)
    await repo.audit(cam.id, "update", ",".join(changes))
    return manager.to_out(cam)


@router.delete("/sources/{source_id}", status_code=204, dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def delete_camera(source_id: str):
    cam = await _camera(source_id)
    streams.stop(cam.id)
    live_store.forget_camera(cam.id)
    await repo.remove(cam.id)
    await repo.audit(cam.id, "delete", cam.name)


@router.post("/sources/{source_id}/test", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def test_camera(source_id: str):
    cam = await _camera(source_id)
    cam, result = await manager.run_test(cam)
    return manager.to_out(cam) | {"diagnostic": result.detail}


# ---- streams / playback ----------------------------------------------------
@router.post("/sources/{source_id}/stream/start", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def start_stream(source_id: str):
    cam = await _camera(source_id)
    if cam.source_type == "usb":
        raise HTTPException(409, "local_agent_required")
    cam, result = await manager.run_test(cam)
    if result.status != "online":
        raise HTTPException(409, f"camera_not_reachable: {result.status}")
    try:
        await streams.start(cam.id, cam.playback_path)
    except streams.StreamError as exc:
        raise HTTPException(exc.status, f"{exc.code}: {exc.detail}") from exc
    await repo.audit(cam.id, "stream_start")
    return manager.to_out(cam)


@router.post("/sources/{source_id}/stream/stop", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def stop_stream(source_id: str):
    cam = await _camera(source_id)
    streams.stop(cam.id)
    await repo.audit(cam.id, "stream_stop")
    return manager.to_out(cam)


@router.get("/sources/{source_id}/playback", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def playback(source_id: str):
    cam = await _camera(source_id)
    try:
        return streams.playback_reference(cam.id)
    except streams.StreamError as exc:
        raise HTTPException(exc.status, f"{exc.code}: {exc.detail}") from exc
    except SecretStorageUnavailable as exc:
        raise HTTPException(503, f"playback_signing_not_configured: {exc}") from exc


# ---- capability-gated controls ----------------------------------------------
@router.post("/sources/{source_id}/snapshot", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def snapshot(source_id: str):
    cam = await _camera(source_id)
    await repo.audit(cam.id, "snapshot_attempt")
    if not manager.capabilities(cam)["snapshot"]:
        raise HTTPException(409, "capability_unsupported: snapshot is not implemented for this camera type")
    raise HTTPException(501, "not_implemented")


@router.post("/sources/{source_id}/ptz", dependencies=[Depends(require_operator), Depends(operator_limiter)])
async def ptz(source_id: str, cmd: PtzCommand):
    cam = await _camera(source_id)
    await repo.audit(cam.id, "ptz_attempt", cmd.action)
    if not manager.capabilities(cam)["ptz"]:
        raise HTTPException(409, "capability_unsupported: PTZ is not available for this camera")
    raise HTTPException(501, "not_implemented")



# ---- media gateway auth hook --------------------------------------------------
@router.post("/gateway/auth")
async def gateway_auth(request: Request):
    """Called by the media gateway (MediaMTX `authMethod: http`) for every request it receives.

    200 = allow, 401 = deny. Publishing needs the configured publisher credentials. Only HLS *reads* of a path with an active stream and a valid, unexpired
    playback token (bound to that camera and path) are allowed. Everything else (publish, API, metrics,
    other protocols) is denied. The token is the credential, so this route needs no operator key.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(401, "bad_request")
    if not isinstance(body, dict):
        raise HTTPException(401, "bad_request")
    if body.get("action") == "publish":
        # Only a local publisher that knows the configured credentials may send video in (laptop webcam mode).
        user, pw = settings.gateway_publish_user, settings.gateway_publish_password
        ok = (bool(user) and bool(pw) and body.get("protocol") == "rtsp"
              and hmac.compare_digest(str(body.get("user") or ""), user)
              and hmac.compare_digest(str(body.get("password") or ""), pw))
        if not ok:
            raise HTTPException(401, "publish_not_allowed")
        return {"ok": True}
    if body.get("action") != "read" or body.get("protocol") != "hls":
        raise HTTPException(401, "not_allowed")
    path = str(body.get("path") or "")
    tokens = parse_qs(str(body.get("query") or "")).get("token", [])
    cam = await repo.get_by_playback_path(path) if path else None
    if not cam or not streams.may_play(cam.id) or not tokens or not verify_playback_token(cam.id, path, tokens[0]):
        raise HTTPException(401, "invalid_playback_token")
    return {"ok": True}
