from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from app.geo.service import provider
router=APIRouter(prefix="/api/geo", tags=["Geospatial"])
class GeoContextRequest(BaseModel):
    lat: float=Field(...,ge=-90,le=90)
    lon: float=Field(...,ge=-180,le=180)
    radius_m: int=Field(1000,ge=100,le=5000)
@router.get("/search")
async def search(q: str=Query(min_length=2), limit: int=Query(5,ge=1,le=10)):
    try: return {"results": await provider.search(q,limit)}
    except Exception as exc: return {"results":[],"error":f"geospatial provider unavailable: {type(exc).__name__}"}
@router.post("/context")
async def context(req: GeoContextRequest):
    return await provider.context(req.lat,req.lon,req.radius_m)
