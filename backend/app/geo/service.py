from __future__ import annotations

import asyncio
import time

import httpx

from app.core.config import settings


class GeoProviderError(RuntimeError):
    """Raised when a public geospatial provider cannot be reached or parsed."""


class PublicGeoProvider:
    def __init__(self) -> None:
        self._last = 0.0

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        await self._throttle()
        params = {"q": query, "format": "jsonv2", "limit": max(1, min(limit, 10))}
        try:
            async with httpx.AsyncClient(
                timeout=settings.geo_timeout_sec,
                headers={"User-Agent": settings.geo_user_agent},
            ) as client:
                response = await client.get(settings.geo_search_url, params=params)
                response.raise_for_status()
                data = response.json()
            self._last = time.monotonic()
            return [
                {
                    "display_name": item.get("display_name"),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "type": item.get("type"),
                }
                for item in data
            ]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise GeoProviderError("geocoding provider request failed") from exc

    async def context(self, lat: float, lon: float, radius_m: int = 1000) -> dict:
        radius_m = max(100, min(radius_m, settings.geo_max_radius_m))
        await self._throttle()
        query = (
            f'[out:json][timeout:10];'
            f'(nwr(around:{radius_m},{lat},{lon})[highway];'
            f'nwr(around:{radius_m},{lat},{lon})[public_transport];'
            f'nwr(around:{radius_m},{lat},{lon})[amenity~"hospital|police|fire_station"];);'
            "out center tags 80;"
        )
        try:
            async with httpx.AsyncClient(
                timeout=settings.geo_timeout_sec,
                headers={"User-Agent": settings.geo_user_agent},
            ) as client:
                response = await client.post(settings.geo_overpass_url, data=query)
                response.raise_for_status()
                data = response.json()
            self._last = time.monotonic()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GeoProviderError("geospatial context provider request failed") from exc

        features = []
        for element in data.get("elements", []):
            tags = element.get("tags", {})
            center = element.get("center", {})
            item_lat = element.get("lat", center.get("lat"))
            item_lon = element.get("lon", center.get("lon"))
            if item_lat is None or item_lon is None:
                continue
            features.append(
                {
                    "id": f"{element.get('type')}:{element.get('id')}",
                    "lat": item_lat,
                    "lon": item_lon,
                    "name": tags.get("name"),
                    "highway": tags.get("highway"),
                    "amenity": tags.get("amenity"),
                    "public_transport": tags.get("public_transport"),
                }
            )
        return {
            "center": {"lat": lat, "lon": lon},
            "radius_m": radius_m,
            "source": "OpenStreetMap/Overpass",
            "attribution": "© OpenStreetMap contributors",
            "features": features,
            "fetched_at": time.time(),
        }

    async def _throttle(self) -> None:
        wait = settings.geo_min_request_interval_sec - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)


provider = PublicGeoProvider()
