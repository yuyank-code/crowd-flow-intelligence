from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import settings

@dataclass(frozen=True)
class CameraSource:
    id: str
    name: str
    kind: str
    url: str | None = None
    zone: str | None = None

class CCTVAdapterError(RuntimeError):
    pass

def configured_sources() -> list[CameraSource]:
    try:
        raw = json.loads(settings.cctv_sources_json)
    except json.JSONDecodeError as exc:
        raise CCTVAdapterError("CCTV source configuration is invalid JSON") from exc
    if not isinstance(raw, list):
        raise CCTVAdapterError("CCTV source configuration must be a JSON list")
    sources: list[CameraSource] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        url = item.get("url")
        if url:
            parsed = urlparse(str(url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise CCTVAdapterError(f"invalid CCTV URL for source {item["id"]}")
        sources.append(CameraSource(id=str(item["id"]), name=str(item["name"]), kind=str(item.get("kind", "metadata")), url=str(url) if url else None, zone=str(item["zone"]) if item.get("zone") else None))
    return sources

def source_catalog() -> list[dict]:
    return [{"id": s.id, "name": s.name, "kind": s.kind, "zone": s.zone, "configured": bool(s.url), "access_policy": "operator-configured"} for s in configured_sources()]

async def health(source_id: str) -> dict:
    source = next((item for item in configured_sources() if item.id == source_id), None)
    if source is None:
        raise CCTVAdapterError("camera source not found")
    if not source.url:
        return {"id": source.id, "status": "metadata-only", "reachable": None}
    try:
        async with httpx.AsyncClient(timeout=settings.cctv_timeout_sec) as client:
            response = await client.head(source.url, follow_redirects=False)
        return {"id": source.id, "status": "online" if response.is_success else "unavailable", "reachable": response.is_success, "http_status": response.status_code}
    except httpx.HTTPError:
        return {"id": source.id, "status": "unavailable", "reachable": False}