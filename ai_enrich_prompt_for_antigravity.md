# SNEC Exhibitor AI Enrichment (Antigravity Edition)

This is the official reference and execution prompt optimized specifically for **Antigravity**—a powerful agentic AI coding assistant. 

Unlike standard text chats or basic IDE agents, Antigravity has full access to terminal execution, web searching, web browsing, and local file systems. This allows for an entirely autonomous or highly interactive **claim → research → write → complete** loop.

---

## Ways to Enrich

| Mode | Command | Who does the AI? | Dashboard Label |
|------|---------|------------------|-----------------|
| **Antigravity Agent** | `db_ai_enrich.py --claim` / `--complete` | **Antigravity** (runs terminal commands, searches web, browse sites, autocompletes) | **Antigravity Agent** |
| **Gemini CLI workers** | `db_gemini_worker.py` | `gemini` headless CLI workers | Gemini CLI |
| **Batch auto** | `db_ai_enrich.py --auto` | Python Script → OpenAI / MiniMax | OpenAI auto |

All modes use **`enrichment_status`** locks (`pending` → `<agent_id>` → `DONE`) so parallel workers never overwrite the same row.

---

## Prerequisites

1. **`DATABASE_URL`** must be active in `.env` (PostgreSQL / Railway).
2. **Web Dashboard:** Ensure the local server is running or start it using:
   ```bash
   python run_web.py
   ```
   Access the live dashboard at: **http://127.0.0.1:8080/enrich**
3. **Official Worker Type:** The `antigravity` worker type is officially added in `enrichment_ops.py` and displays as **"Antigravity Agent"** on the dashboard.

---

## Antigravity Agent Session Prompt (Paste to Start)

If you are starting a new session to enrich exhibitors, ingest and follow this system instruction:

```markdown
You are a SNEC PV+ 2026 exhibitor enrichment agent using the PostgreSQL table `snec26_exhibitors`.
You have full tool-use access: shell commands (`run_command`), search engine (`search_web`), browser (`browser_subagent`), and file system tools.

### STEP 1 — Initialize & Ask for Agent ID
Ask the user at the start of your session:
"What is your agent ID? (Example: antigravity_001 — must be unique for parallel sessions)"

Do not query the database, claim rows, or start research until the user provides or confirms an Agent ID.
Confirm back: "Using agent ID: <agent_id> for this session."

### STEP 2 — The Autonomous Loop (Claim → Research → Complete)
Use worker type `antigravity` so the dashboard registers you as a premium agent.

Loop:

1. **Claim the next pending row:**
   Execute the terminal command:
   ```bash
   python db_ai_enrich.py --agent=<AGENT_ID> --claim --worker-type=antigravity
   ```
   *Note: If no row is returned, stop the loop and notify the user.*

2. **Analyze and Research:**
   Extract from the claimed row:
   - `id`: The row ID.
   - `company_name_cn`: The Chinese name (e.g. "常州天合光能有限公司").
   - `company_name_en`: The existing English name (often blank or machine-translated).
   - `invite_company_info_id` / `snec_detail_url`: SNEC official venue detail page.
   
   Perform web research to find high-confidence official data:
   - Run `search_web` query: `"<company_name_cn>" official website products solar PV`
   - If needed, use `browser_subagent` to visit the official website or the `snec_detail_url` to inspect headers, products page, and "About Us".

3. **Verify and Format the Enrichment Fields:**
   - **`company_name_en`**: Official legal/trade English name. Prefer what is written on their website or official SNEC English listing. Never make up literal translations unless verified.
   - **`products_services`**: English industry terms (semicolon-separated). Clear and clean. No `%%` or raw JSON blobs from SNEC databases.
   - **`website_url`**: Official homepage starting with `https://`. Do not use B2B portals (Alibaba, Made-in-China, LinkedIn) or temporary domains.

4. **Submit and Complete:**
   Execute the terminal command:
   ```bash
   python db_ai_enrich.py --agent=<AGENT_ID> --complete --id=<id> --json='{"company_name_en":"...","products_services":"...","website_url":"https://..."}'
   ```

   **Handling Failure:**
   If research yields no results or is of extremely low confidence, release the lock:
   ```bash
   python db_ai_enrich.py --agent=<AGENT_ID> --release --id=<id>
   ```

Repeat until all rows are finished or you hit the batch limit designated by the user.
```

---

## Command Reference Cheat Sheet

### Interactive / Autonomous Execution
Always run under `--worker-type=antigravity` so the dashboard shows the state-of-the-art engine:

```bash
# Claim next pending row and lock under your agent name
python db_ai_enrich.py --agent=antigravity_001 --claim --worker-type=antigravity

# Complete the enrichment with official data
python db_ai_enrich.py --agent=antigravity_001 --complete --id=592 --json='{"company_name_en":"Trina Solar Co., Ltd.","products_services":"Solar modules; PV trackers; Smart energy storage solutions","website_url":"https://www.trinasolar.com"}'

# Release the lock back to pending if info cannot be verified
python db_ai_enrich.py --agent=antigravity_001 --release --id=592
```

### Queue Monitoring
Check the current distribution of rows in the terminal:
```bash
python db_ai_enrich.py --status
```

### Safety & Maintenance
If a terminal worker crashes or loses connection, locks can be safely managed:

```bash
# Reset all non-DONE rows back to pending
python db_ai_enrich.py --reset-pending

# Reclaim stale locks that haven't updated in 90 minutes
python db_ai_enrich.py --agent=antigravity_001 --reclaim-stale=90
```

---

## Enrichment Database Fields

| Database Field | Type | Expected Format / Rules |
|----------------|------|-------------------------|
| `enrichment_status` | `VARCHAR` | `pending` (unclaimed), `<agent_id>` (locked), or `DONE` (completed). |
| `worker_type` | `VARCHAR` | `antigravity` (registers you), `cursor_ide` (Cursor), `gemini` (Gemini CLI), or `auto` (OpenAI). |
| `company_name_en` | `VARCHAR` | Legal/trade English name (no literal translations unless official). |
| `products_services`| `VARCHAR` | Semicolon-separated (`; `) concise English industry terms. |
| `website_url` | `VARCHAR` | Official corporate homepage starting with `https://`. No B2B lists/socials. |
