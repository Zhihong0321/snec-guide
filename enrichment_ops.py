"""Shared enrichment DB: locks, worker registry, dashboard queries."""
from __future__ import annotations

import os
import socket
from datetime import datetime
from typing import Any

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

DB_URL = (os.environ.get("DATABASE_URL") or "").strip()


def require_db_url() -> str:
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not set (add to .env).")
    return DB_URL
TABLE = "snec26_exhibitors"
WORKERS_TABLE = "snec26_enrichment_workers"

STATUS_PENDING = "pending"
STATUS_DONE = "DONE"
RESERVED = frozenset({STATUS_PENDING, STATUS_DONE})

WORKER_LABELS = {
    "gemini": "Gemini CLI",
    "cursor_cli": "Cursor CLI",
    "cursor_ide": "Cursor IDE",
    "manual": "Manual / script",
    "auto": "OpenAI auto",
}

ROW_COLS = (
    "id, company_name_cn, company_name_en, products_services, website_url, "
    "country, state_province, hall, booth, booth_display, enrichment_status, worker_type"
)


def connect():
    return psycopg2.connect(require_db_url())


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'enrichment_status'
            """,
            (TABLE,),
        )
        if not cur.fetchone():
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN enrichment_status VARCHAR(100) NOT NULL DEFAULT 'pending';
                """
            )
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'worker_type'
            """,
            (TABLE,),
        )
        if not cur.fetchone():
            cur.execute(
                f"ALTER TABLE {TABLE} ADD COLUMN worker_type VARCHAR(32);"
            )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {WORKERS_TABLE} (
                agent_id VARCHAR(100) PRIMARY KEY,
                worker_type VARCHAR(32) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'idle',
                current_exhibitor_id INTEGER
                    REFERENCES {TABLE}(id) ON DELETE SET NULL,
                pid INTEGER,
                hostname VARCHAR(255),
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_snec26_workers_last_seen
            ON {WORKERS_TABLE} (last_seen_at DESC);
            """
        )
    conn.commit()


def register_worker(
    conn,
    agent_id: str,
    worker_type: str,
    *,
    pid: int | None = None,
) -> None:
    pid = pid if pid is not None else os.getpid()
    host = socket.gethostname()[:255]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {WORKERS_TABLE}
                (agent_id, worker_type, status, pid, hostname, started_at, last_seen_at)
            VALUES (%(agent)s, %(wtype)s, 'idle', %(pid)s, %(host)s,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (agent_id) DO UPDATE SET
                worker_type = EXCLUDED.worker_type,
                pid = EXCLUDED.pid,
                hostname = EXCLUDED.hostname,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            {"agent": agent_id, "wtype": worker_type, "pid": pid, "host": host},
        )
    conn.commit()


def touch_worker(
    conn,
    agent_id: str,
    *,
    status: str,
    exhibitor_id: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {WORKERS_TABLE}
            SET status = %(status)s,
                current_exhibitor_id = %(eid)s,
                last_seen_at = CURRENT_TIMESTAMP,
                pid = COALESCE(%(pid)s, pid)
            WHERE agent_id = %(agent)s
            """,
            {
                "status": status,
                "eid": exhibitor_id,
                "agent": agent_id,
                "pid": os.getpid(),
            },
        )
    conn.commit()


def unregister_worker(conn, agent_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {WORKERS_TABLE} WHERE agent_id = %(agent)s", {"agent": agent_id})
    conn.commit()


def claim_next(
    conn,
    agent_id: str,
    worker_type: str,
    *,
    exhibitor_id: int | None = None,
) -> dict | None:
    params = {
        "agent_id": agent_id,
        "pending": STATUS_PENDING,
        "wtype": worker_type,
    }
    claim_set = """
        enrichment_status = %(agent_id)s,
        worker_type = %(wtype)s,
        updated_at = CURRENT_TIMESTAMP
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if exhibitor_id is not None:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET {claim_set}
                WHERE id = %(id)s AND enrichment_status = %(pending)s
                RETURNING {ROW_COLS}
                """,
                {**params, "id": exhibitor_id},
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    f"""
                    SELECT {ROW_COLS} FROM {TABLE}
                    WHERE id = %(id)s AND enrichment_status = %(agent_id)s
                    """,
                    {"id": exhibitor_id, "agent_id": agent_id},
                )
                row = cur.fetchone()
        else:
            cur.execute(
                f"""
                WITH picked AS (
                    SELECT id FROM {TABLE}
                    WHERE enrichment_status = %(pending)s
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE {TABLE} e
                SET {claim_set}
                FROM picked
                WHERE e.id = picked.id
                RETURNING {ROW_COLS}
                """,
                params,
            )
            row = cur.fetchone()

        if row:
            touch_worker(conn, agent_id, status="working", exhibitor_id=row["id"])
        conn.commit()
        return dict(row) if row else None


def release_pending(conn, exhibitor_id: int, agent_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(pending)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s AND enrichment_status = %(agent)s
            """,
            {"pending": STATUS_PENDING, "id": exhibitor_id, "agent": agent_id},
        )
    touch_worker(conn, agent_id, status="idle", exhibitor_id=None)
    conn.commit()


def mark_done(conn, exhibitor_id: int, agent_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(done)s,
                enriched_at = COALESCE(enriched_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s AND enrichment_status = %(agent)s
            """,
            {"done": STATUS_DONE, "id": exhibitor_id, "agent": agent_id},
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"mark_done: id={exhibitor_id} not locked by {agent_id}")
    touch_worker(conn, agent_id, status="idle", exhibitor_id=None)
    conn.commit()


def _serialize_dt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def fetch_dashboard(stale_seconds: int = 120) -> dict:
    with connect() as conn:
        ensure_schema(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT enrichment_status, COUNT(*)::int AS n
                FROM {TABLE}
                GROUP BY enrichment_status
                """
            )
            counts_raw = {r["enrichment_status"]: r["n"] for r in cur.fetchall()}
            pending = counts_raw.get(STATUS_PENDING, 0)
            done = counts_raw.get(STATUS_DONE, 0)
            in_progress = sum(
                n for k, n in counts_raw.items() if k not in RESERVED
            )

            cur.execute(
                f"""
                SELECT w.agent_id, w.worker_type, w.status, w.current_exhibitor_id,
                       w.pid, w.hostname, w.started_at, w.last_seen_at,
                       e.company_name_cn, e.company_name_en, e.hall, e.booth,
                       e.booth_display, e.enrichment_status
                FROM {WORKERS_TABLE} w
                LEFT JOIN {TABLE} e ON e.id = w.current_exhibitor_id
                ORDER BY w.last_seen_at DESC
                """
            )
            workers = []
            now = datetime.utcnow()
            for r in cur.fetchall():
                last = r["last_seen_at"]
                stale = False
                if last:
                    stale = (now - last.replace(tzinfo=None)).total_seconds() > stale_seconds
                workers.append(
                    {
                        "agent_id": r["agent_id"],
                        "worker_type": r["worker_type"],
                        "worker_label": WORKER_LABELS.get(
                            r["worker_type"], r["worker_type"]
                        ),
                        "status": r["status"],
                        "stale": stale,
                        "pid": r["pid"],
                        "hostname": r["hostname"],
                        "started_at": _serialize_dt(r["started_at"]),
                        "last_seen_at": _serialize_dt(r["last_seen_at"]),
                        "exhibitor": (
                            {
                                "id": r["current_exhibitor_id"],
                                "company_name_cn": r["company_name_cn"],
                                "company_name_en": r["company_name_en"],
                                "hall": r["hall"],
                                "booth": r["booth"],
                                "booth_display": r["booth_display"],
                            }
                            if r["current_exhibitor_id"]
                            else None
                        ),
                    }
                )

            cur.execute(
                f"""
                SELECT id, company_name_cn, company_name_en, worker_type,
                       enrichment_status, updated_at
                FROM {TABLE}
                WHERE enrichment_status NOT IN (%(pending)s, %(done)s)
                ORDER BY updated_at DESC
                LIMIT 30
                """,
                {"pending": STATUS_PENDING, "done": STATUS_DONE},
            )
            locked_rows = [
                {
                    **dict(r),
                    "worker_label": WORKER_LABELS.get(
                        r.get("worker_type") or "", r.get("worker_type") or "—"
                    ),
                    "updated_at": _serialize_dt(r.get("updated_at")),
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                f"""
                SELECT id, company_name_cn, company_name_en, worker_type, enriched_at
                FROM {TABLE}
                WHERE enrichment_status = %(done)s
                ORDER BY enriched_at DESC NULLS LAST, updated_at DESC
                LIMIT 15
                """,
                {"done": STATUS_DONE},
            )
            recent_done = [
                {
                    **dict(r),
                    "worker_label": WORKER_LABELS.get(
                        r.get("worker_type") or "", r.get("worker_type") or "—"
                    ),
                    "enriched_at": _serialize_dt(r.get("enriched_at")),
                }
                for r in cur.fetchall()
            ]

    return {
        "summary": {
            "pending": pending,
            "done": done,
            "in_progress": in_progress,
            "total": pending + done + in_progress,
        },
        "workers": workers,
        "locked_exhibitors": locked_rows,
        "recent_done": recent_done,
        "worker_type_labels": WORKER_LABELS,
    }
