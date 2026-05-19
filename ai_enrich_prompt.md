# SNEC exhibitor AI enrichment

## Two ways to enrich

| Mode | Who does the AI work? | API key? |
|------|------------------------|----------|
| **Cursor (recommended)** | You + Cursor Agent in chat | **No** — uses your Cursor subscription |
| **Batch `--auto`** | Python script calls OpenAI/MiniMax API | **Yes** — `OPENAI_API_KEY` in `.env` |

`db_ai_enrich.py` was originally built for unattended batch (`--auto`). For parallel Cursor sessions, use **`--claim` / `--complete` / `--release`** only.

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
