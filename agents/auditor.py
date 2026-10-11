"""Auditor: finds identity documents a portal published without masking.

Live (LLM_MODE=live): Claude drives Playwright MCP (`npx @playwright/mcp@latest`, headless,
isolated, `--allowed-origins` = allowlist) plus our scanner MCP server, via the tool runner.
The allowlist is enforced in code three times: Playwright's own origin filter, a guard around
every MCP tool call (navigate targets and the resulting page URL), and the scanner's fetch.
Only a safe subset of browser tools is exposed (no screenshots, no file upload, no JS eval).

Deterministic (off / replay without a recording): crawl with the same scanner functions.
"""

from __future__ import annotations

import re
import sys
import uuid
from collections import OrderedDict
from contextlib import AsyncExitStack
from datetime import date
from urllib.parse import urljoin, urlsplit

import cv2

from agents.runner import AgentRun, Budget, Emit, run_llm, spec
from backend.app.core import allowlist, id_detect
from backend.app.core.preprocess import prepare
from backend.app.settings import settings
from mcp_servers import scanner_server

BROWSER_TOOLS = {"browser_navigate", "browser_navigate_back", "browser_snapshot",
                 "browser_click", "browser_type", "browser_wait_for", "browser_close"}
_PAGE_URL = re.compile(r"Page URL:\s*(\S+)")


class GuardedSession:
    """Wraps an MCP ClientSession: refuses calls that would leave the allowlist."""

    def __init__(self, session, emit: Emit):
        self._s, self._emit = session, emit

    def __getattr__(self, name):
        return getattr(self._s, name)

    def _refuse(self, why: str):
        from mcp.types import CallToolResult, TextContent

        self._emit({"agent": "auditor", "type": "blocked", "text": why})
        return CallToolResult(content=[TextContent(type="text", text=f"REFUSED: {why}")],
                              is_error=True)

    async def call_tool(self, name: str, arguments: dict | None = None, **kw):
        args = arguments or {}
        if name == "browser_navigate" and not allowlist.allowed(str(args.get("url", ""))):
            return self._refuse(f"{args.get('url')} is not in the allowlist")
        if name == "scan_url" and not allowlist.allowed(str(args.get("url", ""))):
            return self._refuse(f"{args.get('url')} is not in the allowlist")
        if name == "browser_type" and re.fullmatch(r"\s*\d{6,}\s*", str(args.get("text", ""))):
            return self._refuse("typing long numbers (OTPs, full ID numbers) is not allowed")
        res = await self._s.call_tool(name=name, arguments=args, **kw)
        for c in getattr(res, "content", []) or []:
            m = _PAGE_URL.search(getattr(c, "text", "") or "")
            if m and not allowlist.allowed(m.group(1)) and not m.group(1).startswith("about:"):
                await self._s.call_tool(name="browser_navigate_back", arguments={})
                return self._refuse(f"page left the allowlist ({m.group(1)}); navigated back")
        return res


# Masked thumbnails of leaked documents for the UI (memory only, bounded).
THUMBS: OrderedDict[str, bytes] = OrderedDict()
_KIND_WORDS = {"AADHAAR": "Aadhaar number", "VID": "Aadhaar VID", "PAN": "PAN number",
               "QR": "Aadhaar QR code", "FINGERPRINT": "thumbprint", "DOB": "date of birth",
               "ADDRESS": "home address", "FACE": "photo"}
_HIDE_IN_THUMB = {"AADHAAR", "VID", "PAN", "QR", "FINGERPRINT", "DOB", "MASKED_AADHAAR"}


def _masked_thumb(data: bytes) -> str | None:
    """Leaked image with every sensitive part blacked out, downscaled. Never the original."""
    try:
        prep = prepare(data)
    except Exception:
        return None
    img = prep.rgb.copy()
    for f in id_detect.scan(prep.rgb, prep.dpi, prep.doc_kind).findings:
        if f.type in _HIDE_IN_THUMB:
            x0, y0, x1, y1 = f.bbox_px
            img[max(0, y0 - 4) : y1 + 4, max(0, x0 - 4) : x1 + 4] = 0
    s = 420 / max(img.shape[:2])
    img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    tid = uuid.uuid4().hex[:10]
    THUMBS[tid] = buf.tobytes()
    while len(THUMBS) > 24:
        THUMBS.popitem(last=False)
    return f"/api/agents/thumb/{tid}.jpg"


def deterministic(start_url: str, include_uidai: bool, emit: Emit, max_pages: int = 25) -> dict:
    allowlist.check(start_url)
    host = urlsplit(start_url).netloc
    emit({"agent": "auditor", "type": "tool", "tool": "open", "step": "scan",
          "say": f"Opening the website {host} (a demo hotel's guest archive)…"})
    seen, queue, scanned, exposed = set(), [start_url], set(), []
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen or "uidai-mock" in url:
            continue
        seen.add(url)
        page = scanner_server.list_page_assets(url)
        if page.get("assets"):
            emit({"agent": "auditor", "type": "tool", "tool": "list_page_assets", "step": "scan",
                  "say": f"Checking {urlsplit(url).path or '/'} — {len(page['assets'])} "
                         "image(s) on this page", "input": {"url": url}})
        for a in page.get("assets", []):
            if a in scanned:
                continue
            scanned.add(a)
            r = scanner_server.scan_url(a)
            if r.get("exposed"):
                kinds = [_KIND_WORDS.get(k, k.lower()) for k in sorted(r["counts"])
                         if k in _KIND_WORDS]
                masked = [f["value_masked"] for f in r["findings"] if f.get("value_masked")
                          and f["type"] in ("AADHAAR", "VID", "PAN")]
                thumb = _masked_thumb(allowlist.fetch(a).content)
                exposed.append({"url": a, "page_url": url, "types": sorted(r["counts"]),
                                "masked_values": masked})
                emit({"agent": "auditor", "type": "found", "step": "found",
                      "say": f"Exposed ID found on {urlsplit(url).path}: "
                             + ", ".join(kinds[:4]) + " visible to anyone",
                      "finding": {"page_url": url, "kinds": kinds, "masked": masked,
                                  "thumb_url": thumb}})
            else:
                emit({"agent": "auditor", "type": "tool", "tool": "scan_url", "step": "scan",
                      "say": f"{urlsplit(a).path.rsplit('/', 1)[-1]} is properly masked — OK",
                      "input": {"url": a}, "exposed": False})
        queue.extend(x for x in page.get("links", []) if x not in seen)
    otp = _uidai_mock(start_url, emit) if include_uidai else False
    return {"pages_visited": len(seen), "documents_scanned": len(scanned), "exposed": exposed,
            "uidai_mock_reached_otp_step": otp}


def _uidai_mock(start_url: str, emit: Emit) -> bool:
    """Walk the MOCK lock flow to the OTP step and stop (the OTP is a human-only step)."""
    lock = urljoin(start_url, "/uidai-mock/lock")
    emit({"agent": "auditor", "type": "tool", "tool": "uidai_mock_lock", "step": "lock",
          "say": "Opening the (mock) UIDAI page to lock your fingerprints…",
          "input": {"url": lock}})
    page = allowlist.fetch(lock).text
    m = re.search(r"Captcha:\s*<strong>(\w+)</strong>", page)
    if not m:
        return False
    # synthetic last-4 only; the agent never handles a full number
    r = allowlist.fetch(lock, data={"uid_last4": "0000", "captcha": m.group(1)})
    reached = "HUMAN STEP" in r.text
    emit({"agent": "auditor", "type": "handover", "step": "lock",
          "say": "Biometric lock is ready — your turn: enter the OTP sent to your phone. "
                 "(Agents never type OTPs.)" if reached else "Couldn't open the lock page"})
    return reached


async def _live(start_url: str, include_uidai: bool, emit: Emit, budget: Budget,
                recorder: list | None) -> AgentRun | None:
    from anthropic.lib.tools.mcp import async_mcp_tool
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    pw = StdioServerParameters(command="npx", args=[
        "-y", "@playwright/mcp@latest", "--headless", "--isolated",
        "--allowed-origins", allowlist.origins()])
    sc = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers.scanner_server"])
    async with AsyncExitStack() as stack:
        tools = []
        for params, keep in ((pw, BROWSER_TOOLS), (sc, {"scan_url"})):
            r, w = await stack.enter_async_context(stdio_client(params))
            sess = await stack.enter_async_context(ClientSession(r, w))
            await sess.initialize()
            guarded = GuardedSession(sess, emit)
            listed = await sess.list_tools()
            tools += [async_mcp_tool(t, guarded) for t in listed.tools if t.name in keep]
        task = (f"Start URL: {start_url}\nAudit every guest/record page and scan each ID image."
                + ("\nThen open the mock UIDAI biometric-lock flow and stop at the OTP step."
                   if include_uidai else ""))
        return await run_llm(spec("auditor"), task,
                             {"start": start_url, "uidai": include_uidai}, emit, budget,
                             tools=tools, recorder=recorder)


async def audit(start_url: str, emit: Emit, budget: Budget, include_uidai: bool = True,
                recorder: list | None = None) -> AgentRun:
    allowlist.check(start_url)
    sp = spec("auditor")
    if settings.llm_mode == "live":
        run = await _live(start_url, include_uidai, emit, budget, recorder)
    else:
        run = await run_llm(sp, "", {"start": start_url, "uidai": include_uidai}, emit, budget)
    if run is None or not run.output:
        out = deterministic(start_url, include_uidai, emit)
        out["site"], out["found_on"] = start_url, date.today().isoformat()
        emit({"agent": "auditor", "type": "result", "output": out, "deterministic": True})
        return AgentRun("auditor", "deterministic", out)
    run.output.setdefault("site", start_url)
    return run
