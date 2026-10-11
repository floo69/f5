"""MCP server: SurakshitID armor (detect → destroy → watermark → verify → seal), stdio.

    uv run python -m mcp_servers.redactor_server

Input files must live under data/inbox; armored PNGs go to data/armor/out. Returns the
decision, reasons, masks and badge, never image bytes.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from backend.app.armor_pipeline import armor
from backend.app.core.badge import Sealer
from backend.app.core.presets import PRESETS
from backend.app.settings import settings

mcp = MCPServer("surakshit-redactor")
INBOX = Path("data/inbox").resolve()
OUT = Path(settings.armor_dir) / "out"


def armor_path(path: str, preset: str, recipient: str, valid_days: int) -> dict:
    p = Path(path).resolve()
    if not p.is_relative_to(INBOX) or not p.is_file():
        return {"error": "input must be a file under data/inbox"}
    o = armor(p.read_bytes(), preset, recipient, valid_days, Sealer(settings.armor_dir))
    r = o.result
    out = {k: r[k] for k in ("armor_id", "decision", "reasons", "decision_us", "masks_px",
                             "watermark_text", "expires_at")}
    out["findings"] = [{k: f[k] for k in ("type", "action", "value_masked")}
                       for f in r["findings"]]
    out["verification"] = r["verification"]["status"]
    if o.png is not None:
        OUT.mkdir(parents=True, exist_ok=True)
        dest = OUT / f"{r['armor_id']}.png"
        dest.write_bytes(o.png)
        out["armored_png"] = str(dest)
        out["block_hash"] = r["badge"]["block_hash"]
    return out


@mcp.tool()
def list_presets() -> list[dict]:
    """Purpose presets and what each one masks / keeps."""
    return [p.public() for p in PRESETS.values()]


@mcp.tool()
def armor_file(path: str, preset: str, recipient: str, valid_days: int) -> dict:
    """Purpose-lock an identity document under data/inbox. Sensitive pixels are overwritten
    with 0x00, a purpose watermark is burned in, the export is re-verified and sealed.
    Deterministic rules decide; blurry/unreadable input returns BLOCK_FOR_REVIEW."""
    return armor_path(path, preset, recipient, valid_days)


if __name__ == "__main__":
    mcp.run()
