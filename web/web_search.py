"""DuckDuckGo text search for SNEC-related questions (no API key).

Uses the `ddgs` package (recommended successor to `duckduckgo_search`).
"""
import os
from typing import List


def server_web_search_enabled() -> bool:
    """Global switch from ENABLE_WEB_SEARCH env (admin default)."""
    v = os.environ.get("ENABLE_WEB_SEARCH", "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def _enabled() -> bool:
    return server_web_search_enabled()


def _ddgs_class():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except ImportError:
            return None


def search_snec_web(user_message: str, max_results: int = 10, *, enabled: bool = True) -> str:
    """
    Run lightweight web search, biased toward SNEC 2026 / pv.snec.org.cn context.
    Returns markdown-ish text for injection into the LLM system prompt.
    """
    if not enabled:
        return "(Web search off for this message — using database + static context only.)"
    if not server_web_search_enabled():
        return "(Web search disabled on server via ENABLE_WEB_SEARCH.)"

    DDGS = _ddgs_class()
    if DDGS is None:
        return (
            "(Web search unavailable: `pip install ddgs`.) "
            "Continue with database + static context only."
        )

    qbase = (user_message or "").strip()
    if len(qbase) > 240:
        qbase = qbase[:240] + "…"

    queries: List[str] = [
        f"{qbase} SNEC 2026 Shanghai NECC photovoltaic",
        f"SNEC PV+ 2026 {qbase} exhibitor hall booth",
        f"site:pv.snec.org.cn {qbase}",
    ]

    lines: List[str] = []
    seen: set[str] = set()

    try:
        ddgs = DDGS()
        per_q = max(3, min(6, max_results // len(queries) + 1))
        for q in queries:
            for r in ddgs.text(q, region="wt-wt", safesearch="moderate", max_results=per_q):
                href = (r.get("href") or r.get("url") or "").strip()
                if not href or href in seen:
                    continue
                seen.add(href)
                title = (r.get("title") or "Untitled")[:140]
                body = (r.get("body") or "")[:320]
                lines.append(
                    f"- **{title}**\n  URL: {href}\n  Snippet: {body}"
                )
                if len(lines) >= max_results:
                    break
            if len(lines) >= max_results:
                break
    except Exception as e:
        return f"(Web search failed: {e!s}. Use database + official site.)"

    if not lines:
        return "(No web snippets returned; rely on DATABASE blocks and https://pv.snec.org.cn/.)"

    return "\n".join(lines)
