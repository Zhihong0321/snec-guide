"""Build SNEC 2026 context for the LLM from static docs + PostgreSQL exhibitors."""
import os
import re
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from web.env import database_url
from web.floor_plans import format_floor_plans_for_prompt
from web.web_search import search_snec_web

ROOT = Path(__file__).resolve().parent.parent

STATIC_SNEC_BRIEF = """
SNEC PV+ 2026 (19th edition) — International Photovoltaic & Smart Energy Exhibition, Shanghai.
Dates: 3–5 June 2026 (visitors 09:00–17:00, last day until 14:00).
Venue: National Exhibition and Convention Center (NECC), four-leaf clover, 14 halls.
Co-located: SNEC ES+ (storage). Metro: Line 2 East Xujing / Line 17 Zhuguang Road.
Official site: https://pv.snec.org.cn/

Hall orientation (typical):
- 1.1H/1.2H: PV production equipment
- 2.1H/2.2H: silicon, wafers, materials
- 3H: trackers / mounting
- 4.1H/5.1H/8.1H: inverters & energy storage
- 5.2H/7.2H/8.2H: cells & modules (tier-1)
- 6.1H/6.2H: smart energy / digital grid
- 7.1H: battery cells & packs
""".strip()

# Words that match product text but not company names — keep out of token OR search
TOKEN_STOP = {
    "the", "and", "for", "what", "where", "when", "which", "about", "snec",
    "2026", "show", "tell", "please", "company", "exhibitor", "exhibitors",
    "around", "near", "next", "who", "whom", "whose", "booth", "booths",
    "hall", "halls", "same", "other", "others", "nearby", "beside", "between",
    "list", "give", "show", "find", "search", "any", "some", "many", "how",
    "why", "are", "was", "were", "is", "this", "that", "with", "from", "into",
    "there", "here", "they", "them", "their", "also", "like", "such", "each",
    "every", "all", "both", "either", "neighbors", "neighbours", "neighbor",
    "neighbour", "close", "closest", "near", "besides", "including", "except",
}

# Halls on NECC 0m / 16m layers (for "hall 8" style questions)
HALL_8_LEAF = ("8.1H", "8.2H")
HALL_7_LEAF = ("7.1H", "7.2H")
HALL_6_LEAF = ("6.1H", "6.2H")
HALL_5_LEAF = ("5.1H", "5.2H")
HALL_4_LEAF = ("4.1H", "4.2H")
HALL_2_LEAF = ("2.1H", "2.2H")
HALL_1_LEAF = ("1.1H", "1.2H")


def _read_doc(name: str, max_chars: int = 4000) -> str:
    path = ROOT / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _query_tokens(message: str) -> list[str]:
    raw = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", message)
    out = []
    for t in raw:
        low = t.lower()
        if low in TOKEN_STOP or len(t) < 2:
            continue
        out.append(t)
    return out[:10]


def _db():
    return database_url()


def _select_cols() -> str:
    return """
        id, company_name_cn, company_name_en, hall, booth, booth_display,
        products_services, country, state_province, website_url, contact_email
    """


def search_exhibitors_by_tokens(message: str, limit: int = 18) -> list[dict]:
    url = _db()
    if not url:
        return []

    tokens = _query_tokens(message)
    if not tokens:
        return []

    conditions = []
    params: list = []
    for tok in tokens:
        conditions.append(
            "(company_name_cn ILIKE %s OR company_name_en ILIKE %s "
            "OR products_services ILIKE %s OR hall ILIKE %s)"
        )
        p = f"%{tok}%"
        params.extend([p, p, p, p])

    sql = f"""
        SELECT {_select_cols()}
        FROM snec26_exhibitors
        WHERE ({' OR '.join(conditions)})
        ORDER BY CASE WHEN hall IS NOT NULL AND hall <> '' THEN 0 ELSE 1 END,
                 company_name_cn
        LIMIT %s
    """
    params.append(limit)

    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except Exception:
        return []


def find_anchor_exhibitors_by_name(message: str, per_token: int = 4, max_total: int = 8) -> list[dict]:
    """Resolve company names (tokens) against name columns only — for 'around LONGi' style."""
    url = _db()
    if not url:
        return []

    tokens = _query_tokens(message)
    seen: set[int] = set()
    rows: list[dict] = []

    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                for tok in tokens:
                    if len(tok) < 3 and not re.search(r"[\u4e00-\u9fff]", tok):
                        continue
                    p = f"%{tok}%"
                    cur.execute(
                        f"""
                        SELECT {_select_cols()}
                        FROM snec26_exhibitors
                        WHERE company_name_cn ILIKE %s OR company_name_en ILIKE %s
                        ORDER BY
                            CASE WHEN hall IS NOT NULL AND hall <> '' THEN 0 ELSE 1 END,
                            LENGTH(COALESCE(company_name_en, company_name_cn)),
                            company_name_cn
                        LIMIT %s
                        """,
                        (p, p, per_token),
                    )
                    for r in cur.fetchall():
                        rid = r["id"]
                        if rid not in seen:
                            seen.add(rid)
                            rows.append(r)
                            if len(rows) >= max_total:
                                return rows
    except Exception:
        return []

    return rows


def parse_explicit_halls(message: str) -> list[str]:
    """Extract hall codes like 8.2H, 7.1H, 3H from the user message."""
    text = message
    found = set(re.findall(r"\b(\d+\.\d+H)\b", text, flags=re.I))
    found.update(re.findall(r"\b(3H|NH)\b", text, flags=re.I))
    low = text.lower()
    # "hall 8" / 8馆 → both leaves on digit 8
    if re.search(r"\bhall\s*8\b|8\s*号馆|展馆\s*8|8\s*馆\b", text, re.I):
        found.update(HALL_8_LEAF)
    if re.search(r"\bhall\s*7\b|7\s*号馆", text, re.I):
        found.update(HALL_7_LEAF)
    if re.search(r"\bhall\s*6\b|6\s*号馆", text, re.I):
        found.update(HALL_6_LEAF)
    if re.search(r"\bhall\s*5\b|5\s*号馆", text, re.I):
        found.update(HALL_5_LEAF)
    if re.search(r"\bhall\s*4\b|4\s*号馆", text, re.I):
        found.update(HALL_4_LEAF)
    if re.search(r"\bhall\s*2\b|2\s*号馆", text, re.I):
        found.update(HALL_2_LEAF)
    if re.search(r"\bhall\s*1\b|1\s*号馆", text, re.I):
        found.update(HALL_1_LEAF)
    return sorted(found)


def wants_hall8_family(message: str, anchor_halls: list[str]) -> bool:
    if any(h.upper().startswith("8.") for h in anchor_halls):
        return True
    if re.search(r"\bhall\s*8\b|8\s*号馆|展馆\s*8|leaf\s*8|8\s*馆", message, re.I):
        return True
    return False


def fetch_exhibitors_in_halls(halls: list[str], limit: int = 55) -> list[dict]:
    if not halls:
        return []
    url = _db()
    if not url:
        return []
    halls = [h for h in halls if h]
    if not halls:
        return []

    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT {_select_cols()}
                    FROM snec26_exhibitors
                    WHERE hall IS NOT NULL AND hall <> ''
                      AND hall = ANY(%s)
                    ORDER BY hall, booth NULLS LAST, company_name_cn
                    LIMIT %s
                    """,
                    (halls, limit),
                )
                return list(cur.fetchall())
    except Exception:
        return []


def fetch_same_hall_as_anchor(anchor_row: dict, limit: int = 42) -> list[dict]:
    hall = (anchor_row.get("hall") or "").strip()
    if not hall:
        return []
    return fetch_exhibitors_in_halls([hall], limit=limit)


def format_exhibitors(rows: list[dict], title: str = "") -> str:
    if not rows:
        return f"({title} — no rows.)" if title else "(No matching exhibitors.)"

    lines = []
    if title:
        lines.append(f"**{title}** ({len(rows)} rows)")
    for r in rows:
        booth = r.get("booth_display") or f"{r.get('hall') or ''} {r.get('booth') or ''}".strip()
        booth = booth or "booth TBD"
        products = (r.get("products_services") or "")[:180]
        loc = r.get("state_province") or r.get("country") or ""
        extra = " | ".join(x for x in [loc, r.get("website_url"), r.get("contact_email")] if x)
        lines.append(
            f"- **id={r['id']}** → visit log path **`/exhibitor/{r['id']}`** — "
            f"{r['company_name_cn']} ({r.get('company_name_en') or ''}) "
            f"[{booth}] {products}{(' — ' + extra) if extra else ''}"
        )
    return "\n".join(lines)


NAVIGATOR_URL_RULES = """
=== IN-APP VISIT LOG (navigator — use with chat answers) ===
This web app includes a **Visit log** page per exhibitor (personal notes & booth photos).
- **Canonical URL path (required format):** `/exhibitor/<NUMERIC_ID>` where `<NUMERIC_ID>` is the database `id` (integer) shown on each DATABASE line as `id=…`.
- Use **relative** links only (start with `/`) so they work on any host, e.g. Markdown: `[Visit log](/exhibitor/2288)` or plain: `/exhibitor/2288`.
- Whenever you mention a specific exhibitor that appears in a DATABASE block with an `id`, add a short **Visit log** link using that path so the user can jump from chat to the page.
- Do not invent ids; only use ids present in the context lists.
""".strip()

FLOOR_PLAN_RULES = """
=== FLOOR PLANS (booth maps — share when asked) ===
- This app hosts **per-hall floor plan images** at `/floor_plans/<file>.jpg` (see **FLOOR PLAN CATALOG** below).
- When the user asks for **directions, wayfinding, hall layout, booth map, 平面图, 展位图**, or **which hall / how to walk**, include the **relevant map image(s)** in Markdown, e.g. `![Hall 8.2H floor plan](/floor_plans/8.2H.jpg)`.
- For **venue-wide** navigation (metro, east/west entrance, clover leaves, leaf A–D), include the **NECC overview**: `![NECC overview](/floor_plans/00_overview_NECC_clover.jpg)`.
- When discussing a **specific hall** (from DATABASE or the question), show that hall's map. If multiple halls (e.g. hall 8 = 8.1H + 8.2H), show each leaf map.
- Use **relative** paths only (`/floor_plans/...`). Do not invent filenames — only paths from the catalog.
- Maps are official **2025 NECC geometry** (valid for 2026 show layout); booth numbers in DB may still be incomplete until organizers publish assignments.
""".strip()

REASONING_RULES = """
=== HOW TO COMBINE WEB + DATABASE (important) ===
1. **Read WEB_SEARCH_SNIPPETS first** for fresher press / recap / unofficial lists; treat as noisy (spam or SEO pages possible) — cross-check with DATABASE when possible.
2. **DATABASE blocks are structured ground truth** for exhibitor names, halls, booths, products (from our snapshot). Prefer them for "who is in hall X / around company Y" when rows exist.
3. For "around X", "near X", "same hall": **must** list concrete names from **DATABASE_SAME_HALL_FOR_ANCHOR** when that block has rows — do not replace with generic "Tier-1 hub" prose. Add web-found names only if snippets clearly name additional exhibitors.
4. **Tier-1 / major PV**: SNEC has **thousands of exhibitors** across many halls (modules also in 5.2H, 7.2H, 8.2H, etc.). Never imply only a few Tier-1 firms exist; if the user asks how many / who are Tier-1, cite scale from EVENT FACTS + sector notes + counts from DATABASE lists when relevant.
5. If **DATABASE_HALL_8_LEAF** appears, use it for hall-8 questions; combine with same-hall anchor data when applicable.
6. If web and DB disagree on a booth, mention both and say the **official floor map on pv.snec.org.cn** wins on show week.
7. If a section says "(no rows)" or search failed, say so — do not invent booth neighbors.
""".strip()


def build_system_prompt(user_message: str, *, web_search: bool = True) -> str:
    web_block = search_snec_web(user_message, max_results=10, enabled=web_search)

    guide = _read_doc("expo_map_guide.md", 3500)
    sections = _read_doc("sections_analysis.md", 2500)

    token_hits = search_exhibitors_by_tokens(user_message, limit=18)
    anchors = find_anchor_exhibitors_by_name(user_message)

    anchor_halls: list[str] = []
    for a in anchors:
        h = (a.get("hall") or "").strip()
        if h and h not in anchor_halls:
            anchor_halls.append(h)

    explicit_halls = parse_explicit_halls(user_message)
    same_hall_blocks: list[str] = []

    for a in anchors[:3]:
        block_rows = fetch_same_hall_as_anchor(a, limit=40)
        if block_rows:
            short = (a.get("company_name_en") or a.get("company_name_cn") or "ANCHOR")[:36]
            short = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", short).strip("_")
            same_hall_blocks.append(
                format_exhibitors(
                    block_rows,
                    title=f"DATABASE_SAME_HALL_FOR_ANCHOR_{short} — hall {(a.get('hall') or '').strip()}",
                )
            )

    hall8_block = ""
    hall8_rows: list[dict] = []
    if wants_hall8_family(user_message, anchor_halls):
        hall8_rows = fetch_exhibitors_in_halls(list(HALL_8_LEAF), limit=50)
        hall8_block = format_exhibitors(
            hall8_rows, title="DATABASE_HALL_8_LEAF (8.1H + 8.2H, from DB)"
        )

    explicit_block = ""
    if explicit_halls:
        ex_rows = fetch_exhibitors_in_halls(explicit_halls, limit=55)
        explicit_block = format_exhibitors(
            ex_rows, title=f"EXHIBITORS_IN_MENTIONED_HALLS ({', '.join(explicit_halls)})"
        )

    anchor_block = format_exhibitors(anchors, title="ANCHOR_MATCHES (resolved company names)")
    token_block = format_exhibitors(token_hits, title="TOKEN_SEARCH (broader text match)")

    floor_plans_block = format_floor_plans_for_prompt(
        user_message, anchor_halls, explicit_halls
    )

    return f"""You are SNEC Guide, an expert assistant for visitors to SNEC PV+ 2026 in Shanghai.
Answer using the context below (web snippets + database + static notes). If unsure, say so and suggest https://pv.snec.org.cn/.

{NAVIGATOR_URL_RULES}

{FLOOR_PLAN_RULES}

=== WEB_SEARCH_SNIPPETS (fetched for this question; check before DB-only answers) ===
{web_block}

{REASONING_RULES}

=== EVENT FACTS ===
{STATIC_SNEC_BRIEF}

=== VENUE / NAVIGATION ===
{guide or '(not loaded)'}

{floor_plans_block}

=== SECTOR NOTES ===
{sections or '(not loaded)'}

{anchor_block}

{"\n".join(same_hall_blocks) if same_hall_blocks else "**DATABASE_SAME_HALL_FOR_ANCHOR** — (no anchor with assigned hall, or no co-exhibitors in DB for that hall.)"}

{hall8_block if hall8_block else ""}

{explicit_block if explicit_block else ""}

{token_block}
"""


def build_messages(history: list[dict], user_message: str, *, web_search: bool = True) -> list[dict]:
    system = build_system_prompt(user_message, web_search=web_search)
    contents = [
        {
            "role": "user",
            "parts": [
                {
                    "text": system
                    + "\n\n---\nYou are SNEC Guide. Answer visitor questions about SNEC 2026."
                }
            ],
        },
        {
            "role": "model",
            "parts": [{"text": "Ready to help with SNEC PV+ 2026 Shanghai."}],
        },
    ]

    for turn in history[-10:]:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


# MiniMax / OKAI gateway rejects multimodal messages with no text part (error 2013).
_IMAGE_ONLY_TEXT = "Please analyze the attached image(s)."


def _openai_user_content(text: str, images: list[str] | None = None) -> str | list[dict]:
    imgs = [u for u in (images or []) if u]
    if not imgs:
        return text
    body = (text or "").strip() or _IMAGE_ONLY_TEXT
    parts: list[dict] = [{"type": "text", "text": body}]
    for url in imgs:
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def build_openai_messages(
    history: list[dict],
    user_message: str,
    *,
    web_search: bool = True,
    images: list[str] | None = None,
) -> list[dict]:
    system = build_system_prompt(user_message, web_search=web_search)
    messages: list[dict] = [{"role": "system", "content": system}]
    for turn in history[-10:]:
        role = turn.get("role", "user")
        if role == "assistant":
            role = "assistant"
        elif role != "user":
            role = "user"
        content = turn.get("content", "")
        if role == "user" and turn.get("images"):
            content = _openai_user_content(content, turn["images"])
        messages.append({"role": role, "content": content})
    messages.append(
        {"role": "user", "content": _openai_user_content(user_message, images)},
    )
    return messages
