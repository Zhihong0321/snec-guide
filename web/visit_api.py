"""Cookie-based visitor identity + per-exhibitor notes & image uploads."""
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from web.env import database_url

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
COOKIE_NAME = "snec_uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

router = APIRouter()

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _db_url() -> str:
    url = database_url()
    if not url:
        raise HTTPException(503, "DATABASE_URL not configured")
    return url


def _conn():
    return psycopg2.connect(_db_url())


def _ensure_user_row(user_id: str) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snec26_web_users (id, display_name)
                VALUES (%s::uuid, '')
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id,),
            )


def _get_user(user_id: str) -> dict | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id::text AS id, display_name FROM snec26_web_users WHERE id = %s::uuid",
                (user_id,),
            )
            return cur.fetchone()


def _set_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=user_id,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _get_or_create_user(request: Request, response: Response) -> dict:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        try:
            uuid.UUID(raw)
        except ValueError:
            raw = None
    if not raw:
        raw = str(uuid.uuid4())
        _ensure_user_row(raw)
        _set_cookie(response, raw)
    else:
        _ensure_user_row(raw)

    u = _get_user(raw)
    if not u:
        u = {"id": raw, "display_name": ""}
    name = (u["display_name"] or "").strip()
    return {
        "user_id": u["id"],
        "display_name": name,
        "registered": bool(name),
    }


@router.get("/api/me")
async def get_me(request: Request, response: Response):
    return _get_or_create_user(request, response)


class MeUpdate(BaseModel):
    display_name: str = Field("", max_length=100)


@router.post("/api/me")
async def post_me(request: Request, response: Response, body: MeUpdate):
    user = _get_or_create_user(request, response)
    name = body.display_name.strip() or "Anonymous"
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE snec26_web_users
                SET display_name = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s::uuid
                """,
                (name, user["user_id"]),
            )
    return {
        "user_id": user["user_id"],
        "display_name": name,
        "registered": True,
    }


@router.get("/api/feed")
async def get_feed(limit: int = Query(40, ge=1, le=100)):
    """Latest notes and images across all exhibitors, merged by time."""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM (
                    SELECT
                        'note' AS type,
                        n.id,
                        n.created_at,
                        COALESCE(NULLIF(TRIM(u.display_name), ''), n.author_name) AS author,
                        n.note_detail AS body,
                        NULL::text AS image_url,
                        NULL::text AS image_path,
                        NULL::text AS caption,
                        e.id AS exhibitor_id,
                        e.company_name_cn,
                        e.company_name_en,
                        e.hall,
                        e.booth,
                        e.booth_display
                    FROM snec26_notes n
                    JOIN snec26_exhibitors e ON e.id = n.exhibitor_id
                    LEFT JOIN snec26_web_users u ON u.id = n.web_user_id
                    UNION ALL
                    SELECT
                        'image' AS type,
                        i.id,
                        i.created_at,
                        COALESCE(NULLIF(TRIM(u.display_name), ''), 'Anonymous') AS author,
                        NULL::text AS body,
                        i.image_url,
                        i.image_path,
                        i.caption,
                        e.id AS exhibitor_id,
                        e.company_name_cn,
                        e.company_name_en,
                        e.hall,
                        e.booth,
                        e.booth_display
                    FROM snec26_exhibitor_images i
                    JOIN snec26_exhibitors e ON e.id = i.exhibitor_id
                    LEFT JOIN snec26_web_users u ON u.id = i.web_user_id
                ) feed
                ORDER BY created_at DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    items = []
    for row in rows:
        ex = {
            "id": row["exhibitor_id"],
            "company_name_cn": row["company_name_cn"],
            "company_name_en": row["company_name_en"],
            "hall": row["hall"],
            "booth": row["booth"],
            "booth_display": row["booth_display"],
        }
        item = {
            "type": row["type"],
            "id": row["id"],
            "created_at": row["created_at"],
            "author": row["author"],
            "exhibitor": ex,
        }
        if row["type"] == "note":
            item["body"] = row["body"]
        else:
            item["image_url"] = row["image_url"] or row["image_path"]
            item["image_path"] = row["image_path"]
            item["caption"] = row["caption"]
        items.append(item)

    return {"items": items}


@router.get("/api/exhibitors/search")
async def search_exhibitors(q: str = Query("", min_length=1, max_length=200), limit: int = 25):
    pattern = f"%{q.strip()}%"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, company_name_cn, company_name_en, hall, booth, booth_display
                FROM snec26_exhibitors
                WHERE company_name_cn ILIKE %s OR company_name_en ILIKE %s
                ORDER BY
                    CASE WHEN hall IS NOT NULL AND hall <> '' THEN 0 ELSE 1 END,
                    company_name_cn
                LIMIT %s
                """,
                (pattern, pattern, min(limit, 50)),
            )
            return {"results": cur.fetchall()}


@router.get("/api/exhibitor/{exhibitor_id:int}")
async def get_exhibitor(exhibitor_id: int):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, company_name_cn, company_name_en, hall, booth, booth_display,
                       products_services, country, state_province
                FROM snec26_exhibitors WHERE id = %s
                """,
                (exhibitor_id,),
            )
            ex = cur.fetchone()
            if not ex:
                raise HTTPException(404, "Exhibitor not found")

            cur.execute(
                """
                SELECT i.id, i.image_path, i.image_url, i.caption, i.created_at,
                       COALESCE(u.display_name, '') AS uploader_name
                FROM snec26_exhibitor_images i
                LEFT JOIN snec26_web_users u ON u.id = i.web_user_id
                WHERE i.exhibitor_id = %s
                ORDER BY i.created_at DESC
                """,
                (exhibitor_id,),
            )
            images = cur.fetchall()

            cur.execute(
                """
                SELECT n.id, n.author_name, n.note_detail, n.created_at,
                       COALESCE(u.display_name, n.author_name) AS display_author
                FROM snec26_notes n
                LEFT JOIN snec26_web_users u ON u.id = n.web_user_id
                WHERE n.exhibitor_id = %s
                ORDER BY n.created_at DESC
                """,
                (exhibitor_id,),
            )
            notes = cur.fetchall()

    return {"exhibitor": ex, "images": images, "notes": notes}


class NoteCreate(BaseModel):
    note_detail: str = Field(..., min_length=1, max_length=8000)


@router.post("/api/exhibitor/{exhibitor_id:int}/notes")
async def add_note(
    exhibitor_id: int, request: Request, response: Response, body: NoteCreate
):
    user = _get_or_create_user(request, response)
    author = user["display_name"].strip() or "Anonymous"

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM snec26_exhibitors WHERE id = %s", (exhibitor_id,))
            if not cur.fetchone():
                raise HTTPException(404, "Exhibitor not found")
            cur.execute(
                """
                INSERT INTO snec26_notes (exhibitor_id, author_name, note_detail, web_user_id)
                VALUES (%s, %s, %s, %s::uuid)
                RETURNING id, created_at
                """,
                (exhibitor_id, author, body.note_detail.strip(), user["user_id"]),
            )
            nid, created = cur.fetchone()

    return {
        "id": nid,
        "author_name": author,
        "note_detail": body.note_detail.strip(),
        "created_at": created.isoformat() if isinstance(created, datetime) else str(created),
        "display_author": author,
    }


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)[:120]
    return base or "upload.bin"


@router.post("/api/exhibitor/{exhibitor_id:int}/images")
async def upload_image(
    exhibitor_id: int,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    caption: str = Form(""),
):
    user = _get_or_create_user(request, response)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXT:
        raise HTTPException(
            400, f"Allowed image types: {', '.join(sorted(ALLOWED_IMAGE_EXT))}"
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 8 MB)")

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM snec26_exhibitors WHERE id = %s", (exhibitor_id,))
            if not cur.fetchone():
                raise HTTPException(404, "Exhibitor not found")

    user_dir = UPLOAD_DIR / user["user_id"]
    user_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
    dest = user_dir / _safe_filename(fname)
    dest.write_bytes(data)

    rel_path = f"/uploads/{user['user_id']}/{dest.name}"

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snec26_exhibitor_images (
                    exhibitor_id, image_path, image_url, caption, web_user_id, captured_at
                ) VALUES (%s, %s, %s, %s, %s::uuid, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (
                    exhibitor_id,
                    rel_path,
                    rel_path,
                    (caption or "").strip()[:500] or None,
                    user["user_id"],
                ),
            )
            iid = cur.fetchone()[0]

    return {"id": iid, "image_url": rel_path, "caption": caption}
