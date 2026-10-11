"""MCP server (official SDK, MCPServer — FastMCP in mcp<2): on-device identity scanner.

    uv run python -m mcp_servers.scanner_server

Tools return bboxes, types and masked values only — never images, never full numbers,
never QR payloads. URL fetches are limited to the host allowlist (default: the mock portal).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

from mcp.server.mcpserver import MCPServer

from backend.app.core import allowlist, id_detect
from backend.app.core.preprocess import UnreadableInput, prepare

mcp = MCPServer("surakshit-scanner")
LOCAL_ROOTS = (Path("data/inbox").resolve(), Path("data/armor/out").resolve())
EXPOSING = {"AADHAAR", "VID", "PAN", "QR", "FINGERPRINT"}


def _summary(data: bytes) -> dict:
    try:
        prep = prepare(data)
    except UnreadableInput as e:
        return {"readable": False, "error": str(e)}
    sc = id_detect.scan(prep.rgb, prep.dpi, prep.doc_kind)
    found = [f for f in sc.findings if f.type not in ("NUMBER", "BADGE")]
    counts: dict[str, int] = {}
    for f in found:
        counts[f.type] = counts.get(f.type, 0) + 1
    badge = any(f.type == "BADGE" for f in sc.findings)
    return {
        "readable": True,
        "doc_kind": prep.doc_kind,
        "ocr_quality": round(sc.ocr_quality, 3),
        "findings": [{"type": f.type, "bbox_px": list(f.bbox_px), "value_masked": f.value_masked}
                     for f in found],
        "counts": counts,
        "surakshit_badge": badge,
        "exposed": bool(EXPOSING.intersection(counts)),
    }


def scan_bytes(data: bytes) -> dict:
    return _summary(data)


@mcp.tool()
def scan_url(url: str) -> dict:
    """Download an image/PDF from an ALLOWLISTED host and scan it for exposed identity data
    (unmasked Aadhaar/VID, PAN, Aadhaar QR, thumb impressions). Returns types, pixel bboxes and
    masked values only."""
    try:
        r = allowlist.fetch(url)
    except allowlist.BlockedHost as e:
        return {"error": str(e), "blocked": True}
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    return {"url": url, **_summary(r.content)}


@mcp.tool()
def scan_file(path: str) -> dict:
    """Scan a local file under data/inbox or data/armor/out."""
    p = Path(path).resolve()
    if not any(p.is_relative_to(root) for root in LOCAL_ROOTS) or not p.is_file():
        return {"error": "path not allowed"}
    return {"path": str(p), **_summary(p.read_bytes())}


@mcp.tool()
def list_page_assets(url: str) -> dict:
    """List same-host links and image/PDF URLs on an allowlisted page (no JavaScript)."""
    try:
        r = allowlist.fetch(url)
    except allowlist.BlockedHost as e:
        return {"error": str(e), "blocked": True}
    html = r.text
    refs = re.findall(r'(?:href|src)\s*=\s*"([^"#]+)"', html)
    links, assets = [], []
    for ref in refs:
        full = urljoin(url, ref)
        if not allowlist.allowed(full):
            continue
        (assets if re.search(r"\.(jpe?g|png|webp|pdf)(\?|$)", full, re.I) else links).append(full)
    return {"url": url, "links": sorted(set(links)), "assets": sorted(set(assets))}


if __name__ == "__main__":
    mcp.run()
