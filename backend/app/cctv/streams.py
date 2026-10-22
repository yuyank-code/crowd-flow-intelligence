"""Stream sessions + playback references.

A session is 'live' only when the media gateway is actually serving the camera's HLS manifest.
CrowdFlow does not transcode or relay video itself; it never hands the browser a raw RTSP URL or credentials.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.core.config import settings

from .security import SecretStorageUnavailable, make_playback_token


class StreamError(RuntimeError):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


@dataclass
class StreamSession:
    camera_id: str
    playback_path: str
    state: str = "live"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_sessions: dict[str, StreamSession] = {}
# Cameras whose manifest the backend is probing right now. The gateway auth hook accepts their tokens
# even though no session exists yet; stopping a stream removes access immediately.
_probing: set[str] = set()


def may_play(camera_id: str) -> bool:
    return camera_id in _sessions or camera_id in _probing


def active() -> dict[str, StreamSession]:
    return _sessions


def gateway_configured() -> bool:
    return bool(settings.media_gateway_base_url)


def manifest_url(path: str, public: bool = False) -> str:
    base = (settings.media_gateway_public_url if public else "") or settings.media_gateway_base_url
    return f"{base.rstrip('/')}/{path.strip('/')}/index.m3u8"


async def gateway_serving(camera_id: str, path: str) -> bool:
    """True if the gateway serves the HLS manifest. The probe carries its own short-lived token because the gateway enforces them."""
    try:
        token, _ = make_playback_token(camera_id, path, ttl=15)
        _probing.add(camera_id)
        async with httpx.AsyncClient(timeout=settings.cctv_timeout_sec, follow_redirects=False) as c:
            return (await c.get(f"{manifest_url(path)}?token={token}")).status_code == 200
    except httpx.HTTPError:
        return False
    finally:
        _probing.discard(camera_id)


async def start(camera_id: str, playback_path: str | None) -> StreamSession:
    if camera_id in _sessions:
        return _sessions[camera_id]
    if not gateway_configured():
        raise StreamError("media_gateway_not_configured", "Set MEDIA_GATEWAY_BASE_URL to a gateway that ingests this camera.")
    if not playback_path:
        raise StreamError("playback_path_missing", "Set the camera's playback path on the media gateway first.")
    if len(_sessions) >= settings.cctv_max_sessions:
        raise StreamError("session_limit", f"At most {settings.cctv_max_sessions} concurrent streams.", 429)
    if not settings.playback_signing_key:
        raise StreamError("playback_signing_not_configured", "Set PLAYBACK_SIGNING_KEY; the gateway enforces signed tokens.", 503)
    if not await gateway_serving(camera_id, playback_path):
        raise StreamError("gateway_stream_unavailable", "The media gateway is not serving this path yet (no HLS manifest).")
    _sessions[camera_id] = StreamSession(camera_id, playback_path)
    return _sessions[camera_id]


def stop(camera_id: str) -> bool:
    return _sessions.pop(camera_id, None) is not None


def playback_reference(camera_id: str) -> dict:
    sess = _sessions.get(camera_id)
    if not sess:
        raise StreamError("no_active_stream", "Start the stream first.")
    token, exp = make_playback_token(camera_id, sess.playback_path)
    return {"format": "hls", "url": f"{manifest_url(sess.playback_path, public=True)}?token={token}",
            "expires_at": datetime.fromtimestamp(exp, timezone.utc).isoformat()}
