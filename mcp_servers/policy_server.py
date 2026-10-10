from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("thumbshield-policy")
POLICIES = {"default": {"redact": ["FINGERPRINT", "AADHAAR", "VID"], "fingerprint_padding_pt": 8, "number_padding_pt": 2, "fail_closed": True, "llm_can_only": "ESCALATE"}}


@mcp.tool()
def get_policy(name: str = "default") -> dict:
    """Return the deterministic defensive redaction policy."""
    if name not in POLICIES: raise ValueError("unknown policy")
    return POLICIES[name]


@mcp.tool()
def legal_references() -> str:
    """Return labelled legal-reference summaries; verify current wording before legal reliance."""
    path = Path("docs/legal_refs.md")
    return path.read_text(encoding="utf-8") if path.exists() else "No legal references configured. Verify current wording before reliance."


if __name__ == "__main__": mcp.run()
