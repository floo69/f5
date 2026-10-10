from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from mcp_servers.casestore_server import save_mission_report

from .auditor import audit, live_audit
from .notice import draft_notices
from .reviewer import review_page

Emit = Callable[[str, str, dict], Awaitable[None]]


async def run_mission(mission: str, sro: str = "", year_from: int = 2018, year_to: int = 2020, max_docs: int = 15, emit: Emit | None = None, live_agent: bool = False) -> dict:
    """Run Auditor -> Reviewer -> Notice with bounded documents and fail-closed reviews."""
    async def step(agent: str, message: str, **extra):
        if emit: await emit(agent, message, extra)
    max_docs = min(max_docs, 120)
    await step("Orchestrator", "Mission accepted", mission=mission)
    try:
        await step("Auditor", "Auditing allowlisted synthetic portal", max_docs=max_docs)
        live_result = None
        if live_agent:
            await step("Auditor", "Claude + Playwright MCP live mode enabled")
            live_result = await live_audit(sro, year_from, year_to, max_docs)
            await step("Auditor", "Live agent completed; deterministic scanner remains authoritative", live_ok=live_result.get("ok", False))
        rows = await asyncio.to_thread(audit, sro, year_from, year_to, max_docs)
    except Exception as exc:  # noqa: BLE001
        rows = []
        await step("Auditor", f"Auditor failed safely: {exc}", error=True)
    reviews = []
    for row in rows:
        if row.get("decision") == "BLOCK_FOR_REVIEW":
            review = review_page(row.get("doc_id", ""), 0, "Pipeline returned BLOCK_FOR_REVIEW")
            reviews.append(review)
            await step("Reviewer", review["card"], doc_id=row.get("doc_id"))
    await step("Notice", "Drafting human-reviewable bilingual notices", affected=len(rows))
    notices = draft_notices(rows) if rows else {"drafts": [], "saved": []}
    report = "# ThumbShield mission report\n\n" + f"Mission: {mission}\n\nAudited documents: {len(rows)}\nReviews: {len(reviews)}\nNotices drafted: {len(notices['drafts'])}\n\nAll actions are synthetic, local, and require human review before external use."
    saved = save_mission_report(mission, report)
    await step("Orchestrator", "Mission complete", documents=len(rows), reviews=len(reviews), notices=len(notices["drafts"]))
    return {"mission": mission, "rows": rows, "reviews": reviews, "notices": notices["drafts"], "report": report, "report_saved": saved, "live_agent": live_result}
