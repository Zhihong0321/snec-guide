"""
AI enrichment for snec26_exhibitors (parallel-safe via enrichment_status).

Status values:
  pending   — ready to claim
  DONE      — finished
  agent001  — (any agent id) currently locked by that worker

Run 10 parallel sessions (each with a unique agent id):
  python db_ai_enrich.py --agent=agent001
  python db_ai_enrich.py --agent=agent002
  ...

Requires DATABASE_URL and OPENAI_API_KEY (set in .env).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DB_URL = (os.environ.get("DATABASE_URL") or "").strip()
TABLE = "snec26_exhibitors"

STATUS_PENDING = "pending"
STATUS_DONE = "DONE"
RESERVED_STATUSES = frozenset({STATUS_PENDING, STATUS_DONE})

ROW_COLS = (
    "id, company_name_cn, company_name_en, products_services, website_url, "
    "country, state_province, address, company_profile, hall, booth, "
    "invite_company_info_id, enrichment_status"
)

SYSTEM_PROMPT = """You are a data enrichment specialist for SNEC PV+ 2026 (solar / PV / energy storage trade show, Shanghai NECC).

Improve THREE fields for one exhibitor using ONLY evidence you can justify. Prefer official sources (company website, SNEC exhibitor page, corporate registry). Do not invent facts.

Output rules (strict):
- Respond with a single JSON object only. No markdown, no prose outside JSON.
- Use null for any field you cannot verify with reasonable confidence.
- Never copy SNEC raw JSON blobs (strings containing %% or {"CN":) into products_services — normalize them.
- Do not use exhibitor email domains as the company website unless that domain is clearly the corporate homepage.
- website_url: official corporate homepage only (not SNEC, LinkedIn, B2B directories). Use https:// when known.
- company_name_en: legal or official English trade name (website header, annual report, SNEC English listing). Not a literal machine translation unless that is the official English name.
- products_services: 3–12 concise items, semicolon-separated (; ), English industry terms. Max ~600 characters.
- If existing values are already correct official data, keep them unchanged.

Confidence per field: "high" | "medium" | "low"
- high: official website or SNEC company page
- medium: strong secondary source
- low: inferred only — prefer null over guessing

OUTPUT SCHEMA:
{
  "company_name_en": string | null,
  "products_services": string | null,
  "website_url": string | null,
  "confidence": {
    "company_name_en": "high" | "medium" | "low",
    "products_services": "high" | "medium" | "low",
    "website_url": "high" | "medium" | "low"
  },
  "sources": [string],
  "enrichment_notes": string | null
}
"""

BLOCKED_WEBSITE_HOSTS = (
    "snec.org.cn",
    "linkedin.com",
    "facebook.com",
    "1688.com",
    "alibaba.com",
    "made-in-china.com",
    "globalsources.com",
)

SNEC_JSON_RE = re.compile(r'%%|"\s*CN\s*"')
AGENT_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

# Copy this to your AI chat session (Cursor, etc.) — worker must get ID from user first.
AGENT_SESSION_PROMPT = """
You are a SNEC PV+ 2026 exhibitor enrichment worker using PostgreSQL table `snec26_exhibitors`.

## STEP 1 — REQUIRED BEFORE ANYTHING ELSE
Ask the user once at the start of the session:

  "What is your agent ID? (Example: agent001 — must be unique if you run parallel sessions.)"

Do not query the database, claim rows, or enrich exhibitors until the user gives you an agent ID.
If they are unsure, suggest agent001 … agent010 for up to 10 parallel workers.

Confirm back: "Using agent ID: <id> for this session."

## STEP 2 — Rules for your agent ID
- While working on a row, `enrichment_status` must equal your agent ID (e.g. agent001).
- Only claim rows where `enrichment_status` = `pending` (atomic claim → your agent ID).
- When finished with a row, set `enrichment_status` = `DONE`.
- On failure, set back to `pending`.
- Never use another worker's agent ID. Never overwrite rows locked by a different ID.

## STEP 3 — Cursor workflow (no OPENAI_API_KEY — you are the LLM)
Use the shell tool / terminal; Cursor AI does the research and writing.

1. Claim next pending row (locks as your agent id):
   python db_ai_enrich.py --agent=<ID> --claim

2. Research exhibitor (web, SNEC page). Fill English name, products, official URL.

3. Save to DB and mark DONE:
   python db_ai_enrich.py --agent=<ID> --complete --id=<row_id> --json='{"company_name_en":"...","products_services":"...","website_url":"https://..."}'

   On failure, release the lock:
   python db_ai_enrich.py --agent=<ID> --release --id=<row_id>

Repeat from step 1 until --claim returns no rows.

## Optional: unattended batch (needs OPENAI_API_KEY in .env)
python db_ai_enrich.py --agent=<ID> --auto

## Fields to improve per exhibitor
- company_name_en (official English name)
- products_services (English, semicolon-separated)
- website_url (https corporate homepage only)

See SYSTEM_PROMPT in db_ai_enrich.py for per-row LLM JSON rules.
""".strip()

CLAIM_SQL = f"""
    WITH picked AS (
        SELECT id
        FROM {TABLE}
        WHERE enrichment_status = %(pending)s
        ORDER BY id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE {TABLE} e
    SET enrichment_status = %(agent_id)s,
        updated_at = CURRENT_TIMESTAMP
    FROM picked
    WHERE e.id = picked.id
    RETURNING e.*
"""

CLAIM_BY_ID_SQL = f"""
    UPDATE {TABLE}
    SET enrichment_status = %(agent_id)s,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = %(id)s
      AND enrichment_status = %(pending)s
    RETURNING *
"""

RECLAIM_OWNED_SQL = f"""
    SELECT {ROW_COLS}
    FROM {TABLE}
    WHERE id = %(id)s AND enrichment_status = %(agent_id)s
"""


def parse_args(argv: list[str]) -> dict:
    dry_run = "--dry-run" in argv
    use_web = "--no-web" not in argv
    reset_pending = "--reset-pending" in argv
    show_status = "--status" in argv
    claim = "--claim" in argv
    complete = "--complete" in argv
    release = "--release" in argv
    auto_batch = "--auto" in argv
    limit = None
    exhibitor_id = None
    agent_id = os.environ.get("AI_AGENT_ID", "").strip()
    stale_minutes = int(os.environ.get("AI_ENRICH_STALE_MINUTES", "90"))
    json_payload = None
    json_file = None
    worker_type = os.environ.get("AI_WORKER_TYPE", "cursor_ide").strip()

    for arg in argv[1:]:
        if arg.isdigit():
            limit = int(arg)
        elif arg.startswith("--agent="):
            agent_id = arg.split("=", 1)[1].strip()
        elif arg.startswith("--id="):
            exhibitor_id = int(arg.split("=", 1)[1])
        elif arg.startswith("--reclaim-stale="):
            stale_minutes = int(arg.split("=", 1)[1])
        elif arg.startswith("--json="):
            json_payload = arg.split("=", 1)[1]
        elif arg.startswith("--json-file="):
            json_file = arg.split("=", 1)[1]
        elif arg.startswith("--worker-type="):
            worker_type = arg.split("=", 1)[1].strip()

    return {
        "dry_run": dry_run,
        "use_web": use_web,
        "reset_pending": reset_pending,
        "show_status": show_status,
        "claim": claim,
        "complete": complete,
        "release": release,
        "auto_batch": auto_batch,
        "limit": limit,
        "exhibitor_id": exhibitor_id,
        "agent_id": agent_id,
        "stale_minutes": stale_minutes,
        "json_payload": json_payload,
        "json_file": json_file,
        "worker_type": worker_type,
    }


def validate_agent_id(agent_id: str) -> str:
    agent_id = (agent_id or "").strip()
    if not agent_id:
        raise SystemExit(
            "Agent id required. "
            "Use --agent=agent001, set AI_AGENT_ID, or run interactively in a terminal."
        )
    if agent_id in RESERVED_STATUSES:
        raise SystemExit(f"Agent id cannot be reserved value: {agent_id!r}")
    if not AGENT_ID_RE.match(agent_id):
        raise SystemExit(
            f"Invalid agent id {agent_id!r} (use letters, digits, _, -; start with a letter)."
        )
    return agent_id


def resolve_agent_id(agent_id: str) -> str:
    """CLI/env agent id, or ask the user interactively before work starts."""
    agent_id = (agent_id or "").strip()
    if not agent_id and sys.stdin.isatty():
        print("\n" + "=" * 60)
        print(AGENT_SESSION_PROMPT[: AGENT_SESSION_PROMPT.index("## STEP 2")].strip())
        print("=" * 60 + "\n")
        agent_id = input("Your agent ID (e.g. agent001): ").strip()
    agent_id = validate_agent_id(agent_id)
    print(f"[*] Session agent ID: {agent_id}")
    return agent_id


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
                f"""
                CREATE INDEX IF NOT EXISTS idx_snec26_exhibitors_enrichment_status
                ON {TABLE} (enrichment_status);
                """
            )
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(pending)s
            WHERE enrichment_status IS NULL OR TRIM(enrichment_status) = '';
            """,
            {"pending": STATUS_PENDING},
        )
    conn.commit()


def print_status(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT enrichment_status, COUNT(*)::int
            FROM {TABLE}
            GROUP BY enrichment_status
            ORDER BY enrichment_status
            """
        )
        rows = cur.fetchall()
    print("[*] enrichment_status counts:")
    for status, count in rows:
        print(f"    {status}: {count}")


def reclaim_stale_locks(conn, *, minutes: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(pending)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE enrichment_status NOT IN (%(pending)s, %(done)s)
              AND updated_at < CURRENT_TIMESTAMP - (%(mins)s || ' minutes')::interval
            """,
            {"pending": STATUS_PENDING, "done": STATUS_DONE, "mins": minutes},
        )
        n = cur.rowcount
    conn.commit()
    if n:
        print(f"[*] Reclaimed {n} stale lock(s) older than {minutes} min → pending")
    return n


def reset_all_pending(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(pending)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE enrichment_status <> %(done)s
            """,
            {"pending": STATUS_PENDING, "done": STATUS_DONE},
        )
        n = cur.rowcount
    conn.commit()
    print(f"[*] Reset {n} row(s) to pending (left DONE unchanged)")
    return n


def claim_next(conn, agent_id: str, *, exhibitor_id: int | None) -> dict | None:
    params = {"agent_id": agent_id, "pending": STATUS_PENDING}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if exhibitor_id is not None:
            cur.execute(CLAIM_BY_ID_SQL, {**params, "id": exhibitor_id})
            row = cur.fetchone()
            if row:
                conn.commit()
                return dict(row)
            cur.execute(RECLAIM_OWNED_SQL, {"id": exhibitor_id, "agent_id": agent_id})
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None

        cur.execute(CLAIM_SQL, params)
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def mark_done(conn, exhibitor_id: int, agent_id: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(done)s,
                enriched_at = COALESCE(enriched_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s AND enrichment_status = %(agent_id)s
            """,
            {"done": STATUS_DONE, "id": exhibitor_id, "agent_id": agent_id},
        )
        if cur.rowcount != 1:
            raise RuntimeError(
                f"mark_done: row {exhibitor_id} not owned by {agent_id} "
                f"(another agent may have taken it)"
            )
    conn.commit()


def release_pending(conn, exhibitor_id: int, agent_id: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE}
            SET enrichment_status = %(pending)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s AND enrichment_status = %(agent_id)s
            """,
            {"pending": STATUS_PENDING, "id": exhibitor_id, "agent_id": agent_id},
        )
    conn.commit()


def _openai_config():
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY is required for AI enrichment (set in .env).")
    base = os.environ.get("OPENAI_BASE_URL", "https://www.okaoi.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "MiniMax-M2.7")
    return key, base, model


def web_search_snippets(company_name_cn: str, company_name_en: str | None) -> str:
    if os.environ.get("ENABLE_WEB_SEARCH", "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return ""
    try:
        from web.web_search import search_snec_web
    except ImportError:
        return ""
    q = f"{company_name_cn} {company_name_en or ''} official website products solar PV"
    return search_snec_web(q, max_results=8, enabled=True)


def build_user_message(row: dict, web_block: str, agent_id: str) -> str:
    info_id = row.get("invite_company_info_id")
    snec_url = (
        f"https://pv.snec.org.cn/companyDetail/{info_id}" if info_id else None
    )
    payload = {
        "id": row["id"],
        "company_name_cn": row.get("company_name_cn"),
        "company_name_en_current": row.get("company_name_en"),
        "products_services_current": row.get("products_services"),
        "website_url_current": row.get("website_url"),
        "country": row.get("country"),
        "state_province": row.get("state_province"),
        "address": row.get("address"),
        "company_profile": row.get("company_profile"),
        "hall": row.get("hall"),
        "booth": row.get("booth"),
        "invite_company_info_id": str(info_id) if info_id else None,
        "snec_detail_url": snec_url,
        "enrichment_agent": agent_id,
    }
    parts = [
        f"You are agent {agent_id}. Enrich this SNEC 2026 exhibitor record.",
        "INPUT (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=2),
    ]
    if web_block:
        parts.append("WEB SEARCH SNIPPETS:\n" + web_block)
    return "\n\n".join(parts)


def call_llm(user_message: str) -> dict:
    key, base, model = _openai_config()
    url = f"{base}/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        raise RuntimeError(f"LLM HTTP {e.code}: {err[:500]}") from e

    content = (data["choices"][0]["message"]["content"] or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            raise ValueError("No JSON object in LLM response") from None
        return json.loads(m.group(0))


def normalize_website(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")
    host = re.sub(r"^https?://(www\.)?", "", url.lower()).split("/")[0]
    if any(b in host for b in BLOCKED_WEBSITE_HOSTS):
        return None
    return url[:500]


def valid_products(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    if SNEC_JSON_RE.search(text):
        return False
    return True


def should_apply(field: str, new_val: str | None, old_val: str | None, conf: str) -> bool:
    if not new_val or not str(new_val).strip():
        return False
    if conf not in ("high", "medium"):
        return False
    old = (old_val or "").strip()
    new = new_val.strip()
    if old == new:
        return False
    if field == "company_name_en" and old:
        has_latin = bool(re.search(r"[A-Za-z]{3}", old))
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", old))
        if has_latin and not has_cjk and conf != "high":
            return False
    if field == "products_services" and old:
        if SNEC_JSON_RE.search(old):
            return True
        if conf != "high" and len(old) > 24 and not SNEC_JSON_RE.search(old):
            return False
    if field == "website_url" and old and conf != "high":
        return False
    return True


def load_complete_payload(opts: dict) -> dict:
    if opts["json_payload"]:
        return json.loads(opts["json_payload"])
    if opts["json_file"]:
        return json.loads(Path(opts["json_file"]).read_text(encoding="utf-8"))
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            return json.loads(raw)
    raise SystemExit("--complete requires --json=..., --json-file=..., or JSON on stdin")


def apply_cursor_update(
    conn,
    exhibitor_id: int,
    agent_id: str,
    payload: dict,
) -> dict[str, str]:
    """Apply fields from Cursor agent (no external LLM / no confidence gate)."""
    updates: dict[str, str] = {}
    for field in ("company_name_en", "products_services", "website_url"):
        raw = payload.get(field)
        if raw is None:
            continue
        val = str(raw).strip()
        if not val:
            continue
        if field == "website_url":
            val = normalize_website(val)
            if not val:
                continue
        elif field == "products_services" and not valid_products(val):
            raise ValueError(f"Invalid products_services (SNEC JSON blob?): {val[:80]}...")
        updates[field] = val

    if updates:
        sets = ", ".join(f"{k} = %({k})s" for k in updates)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE} SET
                    {sets},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s AND enrichment_status = %(agent_id)s
                """,
                {**updates, "id": exhibitor_id, "agent_id": agent_id},
            )
            if cur.rowcount != 1:
                raise RuntimeError(
                    f"Row {exhibitor_id} is not locked by {agent_id} (claim it first)"
                )
        conn.commit()
    return updates


def print_usage() -> None:
    print(
        """
SNEC exhibitor enrichment

Cursor mode (uses Cursor AI — NO OPENAI_API_KEY):
  python db_ai_enrich.py --agent=agent001 --claim
  python db_ai_enrich.py --agent=agent001 --complete --id=123 --json='{"company_name_en":"..."}'
  python db_ai_enrich.py --agent=agent001 --release --id=123

Unattended batch (needs OPENAI_API_KEY in .env):
  python db_ai_enrich.py --agent=agent001 --auto

Other:
  python db_ai_enrich.py --status
  python db_ai_enrich.py --reset-pending
""".strip()
    )


def apply_enrichment(
    conn,
    row: dict,
    result: dict,
    agent_id: str,
    *,
    dry_run: bool,
) -> dict[str, str | None]:
    conf = result.get("confidence") or {}
    updates: dict[str, str | None] = {}

    for field, validator in (
        ("company_name_en", lambda v: bool(v and v.strip())),
        ("products_services", valid_products),
        ("website_url", lambda v: bool(normalize_website(v))),
    ):
        new_raw = result.get(field)
        if field == "website_url":
            new_val = normalize_website(new_raw if isinstance(new_raw, str) else None)
        else:
            new_val = (new_raw or "").strip() or None if isinstance(new_raw, str) else None

        if not validator(new_val):
            continue
        if not should_apply(field, new_val, row.get(field), conf.get(field, "low")):
            continue
        updates[field] = new_val

    if dry_run or not updates:
        return updates

    sets = ", ".join(f"{k} = %({k})s" for k in updates)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {TABLE} SET
                {sets},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s AND enrichment_status = %(agent_id)s
            """,
            {**updates, "id": row["id"], "agent_id": agent_id},
        )
        if cur.rowcount != 1:
            raise RuntimeError(
                f"apply_enrichment: lost lock on id={row['id']} (status changed)"
            )
    conn.commit()
    return updates


def _json_serial(obj):
    from datetime import date, datetime
    from uuid import UUID

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def enrich_one(
    conn,
    row: dict,
    *,
    agent_id: str,
    dry_run: bool,
    use_web: bool,
) -> None:
    name = row.get("company_name_cn") or "?"
    rid = row["id"]
    print(f"[*] [{agent_id}] id={rid} {name[:40]} (status={row.get('enrichment_status')})")

    web_block = ""
    if use_web:
        try:
            web_block = web_search_snippets(
                row.get("company_name_cn") or "",
                row.get("company_name_en"),
            )
        except Exception as e:
            print(f"    web search skipped: {e}")

    user_msg = build_user_message(row, web_block, agent_id)
    raw = call_llm(user_msg)
    updates = apply_enrichment(conn, row, raw, agent_id, dry_run=dry_run)
    notes = (raw.get("enrichment_notes") or "")[:120]
    if updates:
        print(f"    + {updates}  ({notes})")
    else:
        print(f"    (no field updates) conf={raw.get('confidence')} {notes}")


def main():
    if not DB_URL:
        raise SystemExit("DATABASE_URL is not set (add to .env).")

    opts = parse_args(sys.argv)

    cursor_cmd = opts["claim"] or opts["complete"] or opts["release"]
    if not cursor_cmd and not opts["auto_batch"] and not opts["show_status"] and not opts["reset_pending"]:
        print_usage()
        return

    with psycopg2.connect(DB_URL) as conn:
        ensure_schema(conn)

        if opts["show_status"]:
            print_status(conn)
            return

        if opts["reset_pending"]:
            reset_all_pending(conn)
            if not opts["limit"] and opts["exhibitor_id"] is None:
                return

        agent_id = resolve_agent_id(opts["agent_id"])
        reclaim_stale_locks(conn, minutes=opts["stale_minutes"])

        if opts["claim"]:
            import enrichment_ops as eops

            eops.register_worker(conn, agent_id, opts["worker_type"])
            row = eops.claim_next(
                conn, agent_id, opts["worker_type"], exhibitor_id=opts["exhibitor_id"]
            )
            if not row:
                print("[*] No pending rows to claim.")
                return
            print(json.dumps(row, ensure_ascii=False, indent=2, default=_json_serial))
            return

        if opts["release"]:
            import enrichment_ops as eops

            if opts["exhibitor_id"] is None:
                raise SystemExit("--release requires --id=<exhibitor_id>")
            eops.release_pending(conn, opts["exhibitor_id"], agent_id)
            print(f"[*] id={opts['exhibitor_id']} → enrichment_status=pending")
            return

        if opts["complete"]:
            payload = load_complete_payload(opts)
            rid = opts["exhibitor_id"] or payload.get("id")
            if rid is None:
                raise SystemExit("--complete requires --id= or \"id\" in JSON")
            rid = int(rid)
            updates = apply_cursor_update(conn, rid, agent_id, payload)
            mark_done(conn, rid, agent_id, dry_run=False)
            print(f"[+] id={rid} updated {list(updates.keys()) or '(no fields)'} → DONE")
            return

        if opts["dry_run"]:
            print(f"[*] DRY RUN — agent={agent_id} (no claim/DONE/release writes)")

        print(
            f"[*] agent={agent_id} | limit={opts['limit'] or '∞'} | "
            f"web={opts['use_web']} | stale_reclaim={opts['stale_minutes']}m"
        )

        delay = float(os.environ.get("AI_ENRICH_DELAY_SEC", "0.5"))
        batch_limit = opts["limit"] or (1 if opts["exhibitor_id"] else 10_000_000)
        processed = 0
        ok = 0
        target_id = opts["exhibitor_id"]

        while processed < batch_limit:
            if opts["dry_run"]:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if target_id is not None:
                        cur.execute(
                            f"SELECT {ROW_COLS} FROM {TABLE} WHERE id = %s",
                            (target_id,),
                        )
                        target_id = None
                    else:
                        cur.execute(
                            f"""
                            SELECT {ROW_COLS} FROM {TABLE}
                            WHERE enrichment_status = %(pending)s
                            ORDER BY id
                            OFFSET %(off)s LIMIT 1
                            """,
                            {"pending": STATUS_PENDING, "off": processed},
                        )
                    row = cur.fetchone()
                row = dict(row) if row else None
            else:
                row = claim_next(conn, agent_id, exhibitor_id=target_id)
                if target_id is not None:
                    target_id = None

            if not row:
                print("[*] No pending rows to claim.")
                break

            processed += 1
            rid = row["id"]
            try:
                enrich_one(
                    conn,
                    row,
                    agent_id=agent_id,
                    dry_run=opts["dry_run"],
                    use_web=opts["use_web"],
                )
                mark_done(conn, rid, agent_id, dry_run=opts["dry_run"])
                if not opts["dry_run"]:
                    print("    → enrichment_status=DONE")
                ok += 1
            except Exception as e:
                print(f"[-] id={rid} failed: {e}")
                release_pending(conn, rid, agent_id, dry_run=opts["dry_run"])
                if not opts["dry_run"]:
                    print("    → enrichment_status=pending (released)")

            if processed < batch_limit:
                time.sleep(delay)

        print_status(conn)
        print(f"[+] Agent {agent_id}: {ok}/{processed} succeeded")


if __name__ == "__main__":
    main()
