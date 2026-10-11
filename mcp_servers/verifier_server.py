"""MCP server: SurakshitID verifier + policy gate (stdio).

    uv run python -m mcp_servers.verifier_server

`verify_file` checks a sealed copy tile by tile and reports exact altered coordinates.
`escalate` lets an agent make a decision STRICTER, never looser (hard rule).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from mcp.server.mcpserver import MCPServer

from backend.app.core import badge
from backend.app.core.decision import GateResult
from backend.app.core.decision import escalate as gate_escalate
from backend.app.core.verify_raster import pdf_pixels
from backend.app.settings import settings

mcp = MCPServer("surakshit-verifier")
ROOTS = (Path("data/inbox").resolve(), (Path(settings.armor_dir) / "out").resolve())


def verify_bytes(data: bytes) -> dict:
    if data[:5] == b"%PDF-":
        rgb = pdf_pixels(data)
        if rgb is None:
            return {"status": "NO_BADGE", "detail": "PDF is not a single sealed image"}
    else:
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return {"error": "not a readable image"}
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return badge.verify_image(rgb, badge.Sealer(settings.armor_dir))


@mcp.tool()
def verify_file(path: str) -> dict:
    """Verify a SurakshitID sealed copy (PNG/PDF) under data/inbox or data/armor/out.
    Returns AUTHENTIC | FORGERY_DETECTED (with altered pixel regions) | EXPIRED |
    UNKNOWN_BADGE | NO_BADGE."""
    p = Path(path).resolve()
    if not any(p.is_relative_to(r) for r in ROOTS) or not p.is_file():
        return {"error": "path not allowed"}
    return verify_bytes(p.read_bytes())


@mcp.tool()
def ledger_status() -> dict:
    """Whether the append-only badge ledger's hash chain is intact."""
    s = badge.Sealer(settings.armor_dir)
    n = len(s.ledger.read_text().splitlines()) if s.ledger.exists() else 0
    return {"entries": n, "chain_intact": s.ledger_ok()}


@mcp.tool()
def escalate(current_decision: str, proposed_decision: str, reason: str) -> dict:
    """Propose a stricter decision (e.g. BLOCK_FOR_REVIEW). Requests to relax a decision are
    ignored: deterministic rules decide what is safe."""
    g = gate_escalate(GateResult(current_decision, ()), proposed_decision, reason)
    return {"decision": g.decision, "applied": g.decision != current_decision}


if __name__ == "__main__":
    mcp.run()
