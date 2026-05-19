"""Official PDF downloads + floor plan catalog for the maps page."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from web.env import ROOT
from web.floor_plans import list_floor_plan_catalog

router = APIRouter()

OFFICIAL_PDFS = [
    {
        "id": "commercial",
        "filename": "official_commercial_guide.pdf",
        "title": "Commercial guide",
        "description": "Official SNEC commercial and trade-visitor information.",
    },
    {
        "id": "venue",
        "filename": "official_2026_venue_guide.pdf",
        "title": "2026 venue entry guide",
        "description": "NECC access, entrances, and on-site venue orientation.",
    },
]

ALLOWED_PDF_NAMES = {d["filename"] for d in OFFICIAL_PDFS}


def _size_label(num_bytes: int) -> str:
    if num_bytes >= 1_000_000:
        return f"{num_bytes / 1_000_000:.1f} MB"
    return f"{max(1, num_bytes // 1000)} KB"


@router.get("/api/maps")
async def maps_catalog():
    pdfs = []
    for doc in OFFICIAL_PDFS:
        path = ROOT / doc["filename"]
        if not path.is_file():
            continue
        size = path.stat().st_size
        pdfs.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "description": doc["description"],
                "filename": doc["filename"],
                "url": f"/official/{doc['filename']}",
                "size_bytes": size,
                "size_label": _size_label(size),
            }
        )
    return {"pdfs": pdfs, "floor_plans": list_floor_plan_catalog()}


@router.get("/official/{filename}")
async def download_official_pdf(filename: str):
    if filename not in ALLOWED_PDF_NAMES:
        raise HTTPException(404, "Unknown document")
    path = ROOT / filename
    if not path.is_file():
        raise HTTPException(404, "File not found on server")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
