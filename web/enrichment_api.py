"""Live enrichment dashboard API."""
from fastapi import APIRouter, HTTPException

from enrichment_ops import fetch_dashboard

router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])


@router.get("/dashboard")
async def enrichment_dashboard():
    try:
        return fetch_dashboard()
    except Exception as e:
        raise HTTPException(503, f"Database error: {e}") from e
