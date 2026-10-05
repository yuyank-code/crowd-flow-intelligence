from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.geo.service import GeoProviderError, provider

router = APIRouter(prefix="/api/geo", tags=["Geospatial"])


class GeoContextRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_m: int = Field(1000, ge=100, le=5000)


@router.get("/search")
async def search(q: str = Query(min_length=2), limit: int = Query(5, ge=1, le=10)):
    try:
        return {"results": await provider.search(q, limit), "source": "Nominatim"}
    except GeoProviderError as exc:
        return {"results": [], "error": str(exc), "source": "Nominatim"}


@router.post("/context")
async def context(req: GeoContextRequest):
    try:
        return await provider.context(req.lat, req.lon, req.radius_m)
    except GeoProviderError as exc:
        return {
            "center": {"lat": req.lat, "lon": req.lon},
            "radius_m": req.radius_m,
            "source": "OpenStreetMap/Overpass",
            "features": [],
            "error": str(exc),
        }
