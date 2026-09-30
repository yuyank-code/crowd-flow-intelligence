from __future__ import annotations
import time
import httpx
from app.core.config import settings

class PublicGeoProvider:
    def __init__(self) -> None:
        self._last = 0.0

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        await self._throttle()
        params = {"q": query, "format": "jsonv2", "limit": max(1, min(limit, 10))}
        headers = {"User-Agent": settings.geo_user_agent}
        async with httpx.AsyncClient(timeout=settings.geo_timeout_sec, headers=headers) as client:
            r = await client.get(settings.geo_search_url, params=params)
            r.raise_for_status()
            data = r.json()
        self._last = time.monotonic()
        return [{"display_name": x.get("display_name"), "lat": float(x["lat"]), "lon": float(x["lon"]), "type": x.get("type")} for x in data]

    async def context(self, lat: float, lon: float, radius_m: int = 1000) -> dict:
        radius_m = max(100, min(radius_m, settings.geo_max_radius_m))
        await self._throttle()
        query = f"[out:json][timeout:10];(nwr(around:{radius_m},{lat},{lon})[highway];nwr(around:{radius_m},{lat},{lon})[public_transport];nwr(around:{radius_m},{lat},{lon})[amenity~\"hospital|police|fire_station\"];);out center tags 80;"
        async with httpx.AsyncClient(timeout=settings.geo_timeout_sec, headers={"User-Agent": settings.geo_user_agent}) as client:
            r = await client.post(settings.geo_overpass_url, data=query)
            r.raise_for_status()
            data = r.json()
        self._last = time.monotonic()
        features=[]
        for e in data.get("elements", []):
            tags=e.get("tags", {})
            center=e.get("center", {})
            features.append({"id":f"{e.get('type')}:{e.get('id')}","lat":e.get("lat", center.get("lat")),"lon":e.get("lon", center.get("lon")),"name":tags.get("name"),"highway":tags.get("highway"),"amenity":tags.get("amenity"),"public_transport":tags.get("public_transport")})
        return {"center":{"lat":lat,"lon":lon},"radius_m":radius_m,"source":"OpenStreetMap/Overpass","attribution":"© OpenStreetMap contributors","features":features,"fetched_at":time.time()}

    async def _throttle(self):
        wait=settings.geo_min_request_interval_sec-(time.monotonic()-self._last)
        if wait>0:
            import asyncio
            await asyncio.sleep(wait)

provider=PublicGeoProvider()
