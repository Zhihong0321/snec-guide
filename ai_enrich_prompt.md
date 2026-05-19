# SNEC exhibitor AI enrichment

Reference for Cursor agents and operators. Code: `db_ai_enrich.py`, `db_gemini_worker.py`, `enrichment_ops.py`, dashboard at `/enrich`.

---

## Ways to enrich

| Mode | Command | Who does the AI? | API key? | Shows on dashboard as |
|------|---------|------------------|----------|------------------------|
| **Cursor IDE** | `db_ai_enrich.py --claim` / `--complete` | You + Cursor Agent in chat | No | Cursor IDE |
| **Gemini CLI workers** | `db_gemini_worker.py` | `gemini` headless (× N terminals) | No — Google CLI login | Gemini CLI |
| **Batch auto** | `db_ai_enrich.py --auto` | Python → OpenAI/MiniMax | Yes — `OPENAI_API_KEY` | OpenAI auto |

All modes use **`enrichment_status`** locks (`pending` → `agent001` → `DONE`) so parallel workers never overwrite the same row.

---

## Prerequisites

1. **`DATABASE_URL`** in project `.env` (PostgreSQL / Railway).
2. **Web dashboard (optional):** `python run_web.py` — keep terminal open → **http://127.0.0.1:8080/enrich** (or next free port printed in terminal).  
   Or double-click `start_enrich.bat` (Windows).
3. **Gemini CLI (only for `db_gemini_worker.py`):** `npm install -g @google/gemini-cli`, then run `gemini` once to log in.

---

## Agent session prompt (paste into Cursor first)

**Ask the user for an agent ID before any database work.**

```
You are a SNEC PV+ 2026 exhibitor enrichment worker using PostgreSQL table `snec26_exhibitors`.

## STEP 1 — REQUIRED BEFORE ANYTHING ELSE
Ask the user once at the start of the session:

  "What is your agent ID? (Example: agent001 — must be unique if you run parallel sessions.)"

Do not query the database, claim rows, or enrich exhibitors until the user gives you an agent ID.
Confirm back: "Using agent ID: <id> for this session."

## STEP 2 — Locking rules
- Claim only rows with enrichment_status = pending → set to your agent ID.
- When done: enrichment_status = DONE.
- On failure: back to pending (--release).
- Never touch rows locked by another agent ID.

## STEP 3 — Cursor IDE workflow (no OPENAI_API_KEY)
Use worker type cursor_ide so the live dashboard shows the correct engine.

Loop:

1. Claim (locks row + registers you on dashboard):
   python db_ai_enrich.py --agent=<ID> --claim --worker-type=cursor_ide

2. Research: official English name, products/services (English; semicolon-separated), corporate https URL.

3. Complete:
   python db_ai_enrich.py --agent=<ID> --complete --id=<row_id> --json='{"company_name_en":"...","products_services":"a; b; c","website_url":"https://..."}'

   On failure:
   python db_ai_enrich.py --agent=<ID> --release --id=<row_id>

Repeat until --claim returns no rows.

## Monitor
- Browser: http://127.0.0.1:8080/enrich (requires python run_web.py in another terminal)
- CLI: python db_ai_enrich.py --status

## Fields to improve
- company_name_en
- products_services (English, ; separated)
- website_url (official homepage, https)
```

Same rules as `SYSTEM_PROMPT` in `db_ai_enrich.py` for JSON quality (no SNEC `%%` JSON blobs, confidence for auto mode only).

---

## Live dashboard

| Item | Detail |
|------|--------|
| URL | `http://127.0.0.1:8080/enrich` (port may be 8081+ if busy — read terminal) |
| Start | `python run_web.py` or `start_enrich.bat` |
| API | `GET /api/enrichment/dashboard` (poll every 3s on page) |
| Shows | Queue counts, registered workers, engine type, exhibitor currently updating, recent DONE |

**Tables:** `snec26_exhibitors` (`enrichment_status`, `worker_type`) + `snec26_enrichment_workers` (heartbeat registry).

---

## Cursor IDE workflow (manual / chat)

Default worker type: `cursor_ide` (or set `AI_WORKER_TYPE=cursor_ide`).

```bash
python db_ai_enrich.py --agent=agent001 --claim --worker-type=cursor_ide
python db_ai_enrich.py --agent=agent001 --complete --id=592 --json='{"company_name_en":"Acme Ltd","products_services":"Solar modules; Inverters","website_url":"https://www.acme.com"}'
python db_ai_enrich.py --agent=agent001 --release --id=592
python db_ai_enrich.py --status
```

Ten parallel Cursor chats → `agent001` … `agent010`, each with a **unique** `--agent=` id.

Running `python db_ai_enrich.py` alone prints usage (needs `--claim`, `--complete`, `--release`, `--auto`, or `--status`).

---

## Parallel Gemini CLI (no OPENAI_API_KEY)

Registers as **`gemini`** on the dashboard automatically.

**One-time:**

```bash
npm install -g @google/gemini-cli
gemini    # log in with Google once
```

**Start workers:**

```powershell
.\run_gemini_workers.ps1 -Count 5
# optional limit per worker: .\run_gemini_workers.ps1 -Count 5 -Limit 200
```

Or one terminal per agent:

```bash
python db_gemini_worker.py --agent=agent001
python db_gemini_worker.py --agent=agent002 100
```

**Notes:**

- Windows: worker uses `node` + `@google/gemini-cli` bundle; sets `GEMINI_CLI_TRUST_WORKSPACE=true`.
- Shared Google account rate limit (~60 req/min free tier) — **3–5 workers** safer than 10.
- Env: `GEMINI_MODEL`, `GEMINI_WORKER_DELAY_SEC`, `AI_ENRICH_STALE_MINUTES` (stale lock reclaim).

---

## Batch auto (needs OPENAI_API_KEY)

```bash
python db_ai_enrich.py --agent=agent001 --auto
python db_ai_enrich.py --agent=agent001 --auto 100
```

Dashboard shows worker type **OpenAI auto**. Per-row rules: `SYSTEM_PROMPT` in `db_ai_enrich.py`.

---

## enrichment_status & worker_type

| `enrichment_status` | Meaning |
|---------------------|---------|
| `pending` | Ready to claim |
| `agent001` … | Locked by that worker (any unique agent id) |
| `DONE` | Finished |

| `worker_type` | Dashboard label |
|---------------|-----------------|
| `gemini` | Gemini CLI |
| `cursor_ide` | Cursor IDE |
| `cursor_cli` | Cursor CLI (if used later) |
| `manual` | Manual / script |
| `auto` | OpenAI auto |

---

## Cursor CLI (`agent` command)

Not wired in this repo yet. For headless Cursor, you would need `agent -p "..." --print` plus the same `--claim` / `--complete` loop. Today use **Cursor IDE workflow** or **Gemini CLI workers** instead.

---

## Other CLI

```bash
python db_ai_enrich.py --reset-pending    # non-DONE → pending (keeps DONE)
python db_ai_enrich.py --agent=agent001 --reclaim-stale=90   # with --auto or workers
```

Env: `AI_AGENT_ID`, `DATABASE_URL`, `OPENAI_API_KEY` (auto only), `AI_WORKER_TYPE` (default `cursor_ide` for claim).
