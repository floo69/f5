"""Agent timelines over server-sent events.

GET /api/agents/run?case=audit[&start_url=...]          Auditor → Notice
GET /api/agents/run?case=forgery&attack_id=...           Reviewer → escalate → Notice
GET /api/agents/config                                   mode, models, budget, allowlist

LLM_MODE decides whether Claude is called (live), recordings are served (replay, default)
or only the deterministic specialists run (off). Events never contain full ID numbers.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from agents import auditor
from agents.orchestrator import run_case
from agents.runner import spec
from backend.app.api.armor import attack_context
from backend.app.core import allowlist
from backend.app.settings import settings

router = APIRouter(prefix="/api/agents")
DEFAULT_PORTAL = "http://localhost:8100/"


@router.get("/config")
def config() -> dict:
    return {"mode": settings.llm_mode, "provider": settings.llm_provider,
            "budget_usd": settings.max_usd_per_run, "allowlist": settings.allowed_hosts,
            "models": {k: spec(k).model for k in ("orchestrator", "auditor", "reviewer",
                                                  "notice")}}


@router.get("/thumb/{tid}.jpg")
def thumb(tid: str) -> Response:
    data = auditor.THUMBS.get(tid)
    if data is None:
        raise HTTPException(404, "unknown thumbnail")
    return Response(data, media_type="image/jpeg")


@router.get("/run")
async def run(case: str, start_url: str = DEFAULT_PORTAL, attack_id: str = ""):
    ctx: dict = {}
    if case == "audit":
        if not allowlist.allowed(start_url):
            raise HTTPException(403, "start_url is not in the allowlist")
        c = {"kind": "audit", "start_url": start_url}
    elif case == "forgery":
        found = attack_context(attack_id)
        if found is None:
            raise HTTPException(404, "unknown attack; run an attack in the Inspector first")
        report, rgb, faces = found
        c = {"kind": "forgery", "report": report, "recipient": report.get("recipient")}
        ctx = {"image": rgb, "faces": faces}
    else:
        raise HTTPException(400, "case must be audit|forgery")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(ev: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    async def work() -> None:
        try:
            await run_case(c, emit, ctx)
        except Exception as e:  # surface, never crash the stream
            emit({"agent": "orchestrator", "type": "error", "text": type(e).__name__})
            emit({"agent": "orchestrator", "type": "done", "result": {"error": True}})

    async def stream():
        task = asyncio.create_task(work())
        while True:
            ev = await queue.get()
            yield {"event": ev.get("type", "message"), "data": json.dumps(ev, default=str)}
            if ev.get("type") == "done":
                break
        await task

    return EventSourceResponse(stream())
