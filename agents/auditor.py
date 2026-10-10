"""Auditor URL guard and deterministic fallback entry point."""
from __future__ import annotations

import sys
from urllib.parse import urlparse

from mcp.client.stdio import StdioServerParameters

from .bulk_crawl import crawl
from .runner import playwright_spec, run_claude_agent

DEFAULT_ALLOWLIST = {"localhost:8100", "127.0.0.1:8100"}


def validate_browser_url(url: str, allowlist: set[str] | None = None) -> str:
    """Reject navigation before it reaches Playwright or any HTTP client."""
    parsed = urlparse(url)
    allowed = allowlist or DEFAULT_ALLOWLIST
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in allowed:
        raise ValueError(f"browser host is not allowlisted: {parsed.netloc}")
    return url


def audit(sro: str = "", year_from: int = 2018, year_to: int = 2020, max_docs: int = 15, emit=None) -> list[dict]:
    """Run the deterministic local audit; live demos may replace it with Playwright MCP."""
    validate_browser_url("http://127.0.0.1:8100")
    return crawl("http://127.0.0.1:8100", sro, year_from, year_to, max_docs, emit=emit)


async def live_audit(sro: str = "", year_from: int = 2018, year_to: int = 2020, max_docs: int = 15, events=None) -> dict:
    """Use Claude plus local Playwright MCP when explicitly enabled; never silently bypass the fallback."""
    specs = {
        "playwright": playwright_spec(),
        "casestore": StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.casestore_server"]),
        "scanner": StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.scanner_server"]),
    }
    prompt = f"Audit only the local synthetic portal at http://127.0.0.1:8100. Search SRO '{sro or 'all'}' from {year_from} to {year_to}, page through results, stop at {max_docs} deeds, use casestore.fetch_pdf, register each PDF, and scanner.scan_pdf. Never navigate to another host. Return a concise JSON-like summary."
    system = "You are a defensive ThumbShield auditor. Synthetic data only. You may find and scan records, never extract or export fingerprint images, and never claim a document is safe when uncertain."
    return await run_claude_agent(system, prompt, specs, __import__('os').getenv('WORKER_MODEL', 'claude-opus-5-5'), 'low', events)
