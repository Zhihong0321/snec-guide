# SNEC exhibitor AI enrichment

## Ways to enrich

| Mode | Who does the AI? | API key? |
|------|------------------|----------|
| **Cursor chat** | You + Cursor Agent | No (Cursor subscription) |
| **Parallel Gemini CLI** | `gemini` headless × N workers | No `OPENAI_API_KEY` — uses Google/Gemini CLI login |
| **Batch `--auto`** | Python → OpenAI/MiniMax API | Yes — `OPENAI_API_KEY` |

Parallel Gemini CLI uses the same `enrichment_status` locks (`agent001` …) so workers never overwrite each other.

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
- On failure: back to pending.
- Never touch rows locked by another agent ID.

## STEP 3 — Cursor workflow (no OPENAI_API_KEY)
Loop:

1. Claim:
   python db_ai_enrich.py --agent=<ID> --claim

2. You (Cursor) research: official English name, products/services (English; ), corporate https URL.

3. Complete:
   python db_ai_enrich.py --agent=<ID> --complete --id=<row_id> --json='{"company_name_en":"...","products_services":"a; b; c","website_url":"https://..."}'

   Or release on failure:
   python db_ai_enrich.py --agent=<ID> --release --id=<row_id>

## Fields to improve
- company_name_en
- products_services (English, semicolon-separated)
- website_url (official homepage, https)
```

---

**PostgreSQL (Railway):**

```
postgresql://postgres:PASSWORD@host:port/railway
```

**Table:** `snec26_exhibitors`

**Live dashboard (localhost):** start the app with `python run_web.py` → opens **http://127.0.0.1:8080/enrich**

Shows: active agents, engine type (Gemini CLI / Cursor IDE), exhibitor being updated, queue counts. Auto-refreshes every 3s.

---

## Cursor CLI (no API key)

```bash
python db_ai_enrich.py --agent=agent001 --claim
python db_ai_enrich.py --agent=agent001 --complete --id=592 --json='{"company_name_en":"Acme Ltd","products_services":"Solar modules; Inverters","website_url":"https://www.acme.com"}'
python db_ai_enrich.py --agent=agent001 --release --id=592
python db_ai_enrich.py --status
```

Ten parallel Cursor chats → `agent001` … `agent010`, each running the loop above.

---

## Parallel Gemini CLI (faster, no OPENAI_API_KEY)

**Yes — Cursor can start multiple workers**, each running `gemini` in headless mode. The repo script handles claim → Gemini → DB → DONE.

**One-time setup:**

```bash
npm install -g @google/gemini-cli
gemini    # log in with Google once
```

**Start 5 workers (5 separate terminal windows on Windows):**

```powershell
.\run_gemini_workers.ps1 -Count 5
```

Or manually in 5 terminals:

```bash
python db_gemini_worker.py --agent=agent001
python db_gemini_worker.py --agent=agent002
# …
```

**Monitor queue:**

```bash
python db_ai_enrich.py --status
```

**Limits (important):**

- All workers usually share **one Google account** → shared rate limit (~60 req/min on free tier). **5 workers** is safer than 10.
- Each worker must use a **unique** `--agent=` id.
- Cursor Agent can run `.\run_gemini_workers.ps1` for you via the terminal tool.

Optional env: `GEMINI_CMD=gemini`, `GEMINI_MODEL=...`, `GEMINI_WORKER_DELAY_SEC=2`.

---

## Batch CLI (needs OPENAI_API_KEY)

```bash
python db_ai_enrich.py --agent=agent001 --auto
python db_ai_enrich.py --agent=agent001 --auto 100
```

Per-row LLM rules: `SYSTEM_PROMPT` in `db_ai_enrich.py`.

---

## enrichment_status

| Value | Meaning |
|-------|---------|
| `pending` | Ready |
| `agent001` | Locked by that worker |
| `DONE` | Finished |
