"""SNEC 2026 AI Guide — FastAPI chat (MiniMax / Gemini)."""
import os

import web.env  # noqa: F401 — load .env before other web imports

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.chat_models import DEFAULT_CHAT_MODEL, models_for_api, resolve_model
from web.llm import stream_chat
from web.env import ROOT
from web.maps_api import router as maps_router
from web.visit_api import router as visit_router
from web.web_search import server_web_search_enabled

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SNEC 2026 Guide", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
FLOOR_PLANS_DIR = ROOT / "floor_plans"
if FLOOR_PLANS_DIR.is_dir():
    app.mount("/floor_plans", StaticFiles(directory=str(FLOOR_PLANS_DIR)), name="floor_plans")
app.include_router(visit_router)
app.include_router(maps_router)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    model: str | None = Field(default=None, max_length=128)
    web_search: bool | None = None


def resolve_web_search(user_wants: bool | None) -> bool:
    if not server_web_search_enabled():
        return False
    if user_wants is None:
        return True
    return user_wants


@app.get("/")
async def home_page():
    return FileResponse(STATIC_DIR / "home.html")


@app.get("/chat")
async def chat_page():
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/maps")
async def maps_page():
    return FileResponse(STATIC_DIR / "maps.html")


@app.get("/exhibitor/{exhibitor_id:int}")
async def exhibitor_page_by_id(exhibitor_id: int):
    """Canonical visit-log URL: /exhibitor/<numeric_id> (same SPA as /exhibitor)."""
    return FileResponse(STATIC_DIR / "exhibitor.html")


@app.get("/exhibitor")
async def exhibitor_page(id: int | None = None):
    """Search hub; ?id= redirects to canonical /exhibitor/{id}."""
    if id is not None:
        return RedirectResponse(url=f"/exhibitor/{id}", status_code=302)
    return FileResponse(STATIC_DIR / "exhibitor.html")


@app.get("/api/health")
async def health():
    web_ok = False
    try:
        from web.web_search import _ddgs_class

        web_ok = _ddgs_class() is not None
    except Exception:
        web_ok = False

    return {
        "ok": True,
        "uniapi_configured": bool(os.environ.get("UNIAPI_KEY")),
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL", "https://www.okaoi.com/v1"),
        "database_configured": bool(os.environ.get("DATABASE_URL")),
        "web_search": {
            "server_enabled": server_web_search_enabled(),
            "engine_ready": web_ok,
            "default_on": server_web_search_enabled(),
        },
        "default_model": DEFAULT_CHAT_MODEL,
        "models": models_for_api(),
        "floor_plans": {
            "count": len(
                [
                    p
                    for p in (ROOT / "floor_plans").glob("*")
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                ]
            )
            if (ROOT / "floor_plans").is_dir()
            else 0,
        },
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        resolve_model(req.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    history = [{"role": m.role, "content": m.content} for m in req.history]
    user_message = req.message.strip()
    use_web_search = resolve_web_search(req.web_search)

    async def event_stream():
        try:
            async for token in stream_chat(
                req.model, history, user_message, web_search=use_web_search
            ):
                yield token
        except Exception as e:
            yield f"\n\n⚠️ {e}"

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")
