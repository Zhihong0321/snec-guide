"""
One enrichment worker: claim row → Gemini CLI (headless) → write DB → DONE.

No OPENAI_API_KEY. Requires `gemini` on PATH (npm i -g @google/gemini-cli) and Google login.

Parallel (5 workers example):
  .\\run_gemini_workers.ps1 -Count 5

Single worker:
  python db_gemini_worker.py --agent=agent001
  python db_gemini_worker.py --agent=agent002 50
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time

import psycopg2

from db_ai_enrich import (
    SYSTEM_PROMPT,
    apply_enrichment,
    print_status,
    reclaim_stale_locks,
    resolve_agent_id,
)
from enrichment_ops import (
    DB_URL,
    claim_next,
    ensure_schema,
    mark_done,
    register_worker,
    release_pending,
    unregister_worker,
)

WORKER_TYPE = "gemini"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "").strip()
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT_SEC", "300"))
DELAY_SEC = float(os.environ.get("GEMINI_WORKER_DELAY_SEC", "2"))


def resolve_gemini_argv() -> list[str]:
    """Prefer node + gemini.js (reliable JSON on Windows; avoids .cmd + shell)."""
    override = os.environ.get("GEMINI_CMD", "").strip()
    if override:
        return override.split() if " " in override else [override]

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        bundle = os.path.join(
            appdata, "npm", "node_modules", "@google", "gemini-cli", "bundle", "gemini.js"
        )
        node = shutil.which("node") or shutil.which("node.exe")
        if node and os.path.isfile(bundle):
            return [node, bundle]

    for name in ("gemini.cmd", "gemini", "gemini.ps1"):
        path = shutil.which(name)
        if path:
            return [path]
    return ["gemini"]


def build_gemini_prompt(row: dict, agent_id: str) -> str:
    info_id = row.get("invite_company_info_id")
    snec = f"https://pv.snec.org.cn/companyDetail/{info_id}" if info_id else None
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
        "snec_detail_url": snec,
        "enrichment_agent": agent_id,
    }
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"You are worker {agent_id}.\n"
        "CRITICAL: Do not use tools, shell, or file search. "
        "Reply with ONLY one JSON object matching OUTPUT SCHEMA — no markdown, no explanation.\n"
        f"Enrich this exhibitor:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def parse_llm_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise ValueError("Gemini response had no JSON object") from None
        return json.loads(m.group(0))


def run_gemini_cli(prompt: str) -> dict:
    cmd = [
        *resolve_gemini_argv(),
        "--prompt",
        prompt,
        "--output-format",
        "json",
        "--skip-trust",
        "--approval-mode",
        "plan",
    ]
    if GEMINI_MODEL:
        cmd.extend(["-m", GEMINI_MODEL])
    env = os.environ.copy()
    env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GEMINI_TIMEOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=os.environ.get("GEMINI_WORKER_CWD") or None,
        )
    except FileNotFoundError as e:
        raise SystemExit(
            f"{cmd[0]!r} not found. Install: npm install -g @google/gemini-cli"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Gemini CLI timed out after {GEMINI_TIMEOUT}s") from e

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[:800]
        raise RuntimeError(f"gemini exit {proc.returncode}: {err}")

    raw = proc.stdout.strip()
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return parse_llm_json(raw)

    inner = outer.get("response") or outer.get("text") or raw
    if isinstance(inner, dict):
        return inner
    return parse_llm_json(str(inner))


def parse_args(argv: list[str]) -> tuple[str, int | None]:
    limit = None
    agent_id = os.environ.get("AI_AGENT_ID", "").strip()
    for arg in argv[1:]:
        if arg.isdigit():
            limit = int(arg)
        elif arg.startswith("--agent="):
            agent_id = arg.split("=", 1)[1].strip()
    return agent_id, limit


def main():
    agent_id, limit = parse_args(sys.argv)
    agent_id = resolve_agent_id(agent_id)
    batch = limit or 10_000_000

    print(
        f"[*] Gemini worker {agent_id} | cmd={' '.join(resolve_gemini_argv())} | "
        f"limit={limit or '∞'}"
    )

    ok = 0
    with psycopg2.connect(DB_URL) as conn:
        ensure_schema(conn)
        reclaim_stale_locks(conn, minutes=int(os.environ.get("AI_ENRICH_STALE_MINUTES", "90")))
        register_worker(conn, agent_id, WORKER_TYPE)

        try:
            for n in range(batch):
                row = claim_next(conn, agent_id, WORKER_TYPE, exhibitor_id=None)
                if not row:
                    print("[*] No pending rows.")
                    break

                rid = row["id"]
                name = (row.get("company_name_cn") or "")[:40]
                print(f"[*] [{agent_id}] id={rid} {name}")

                try:
                    result = run_gemini_cli(build_gemini_prompt(row, agent_id))
                    updates = apply_enrichment(conn, row, result, agent_id, dry_run=False)
                    mark_done(conn, rid, agent_id)
                    print(f"    + {list(updates.keys()) or '(no changes)'} → DONE")
                    ok += 1
                except Exception as e:
                    print(f"[-] id={rid} failed: {e}")
                    release_pending(conn, rid, agent_id)
                    print("    → pending (released)")

                time.sleep(DELAY_SEC)
        finally:
            unregister_worker(conn, agent_id)

        print_status(conn)

    print(f"[+] {agent_id}: {ok} succeeded")


if __name__ == "__main__":
    main()
