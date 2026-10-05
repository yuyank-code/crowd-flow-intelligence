from fastapi import APIRouter, HTTPException

from app.cctv.service import CCTVAdapterError, health, source_catalog

router = APIRouter(prefix="/api/cctv", tags=["CCTV"])

@router.get("/sources")
def sources():
    try:
        return {"items": source_catalog(), "policy": "Only operator-configured sources are used."}
    except CCTVAdapterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@router.get("/sources/{source_id}/health")
async def source_health(source_id: str):
    try:
        return await health(source_id)
    except CCTVAdapterError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc