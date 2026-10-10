"""Local stdio MCP lifecycle helper used by the auditor demo."""
from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from backend.app.settings import settings


@dataclass
class ToolEvent:
    kind: str
    message: str


def _guard_value(value: object, allowlist: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"url", "href", "origin"} and isinstance(child, str):
                parsed = urlparse(child)
                if parsed.netloc and parsed.netloc not in allowlist:
                    raise ValueError(f"browser URL host is not allowlisted: {parsed.netloc}")
            _guard_value(child, allowlist)
    elif isinstance(value, list):
        for child in value: _guard_value(child, allowlist)


class GuardedSession:
    """Proxy a Playwright MCP session and reject unsafe URL arguments before forwarding."""
    def __init__(self, session: ClientSession, allowlist: set[str]): self.session, self.allowlist = session, allowlist
    async def call_tool(self, name: str, arguments: dict | None = None):
        _guard_value(arguments or {}, self.allowlist)
        return await self.session.call_tool(name, arguments)


@asynccontextmanager
async def local_mcp_servers(specs: dict[str, StdioServerParameters], events: asyncio.Queue | None = None):
    """Start local stdio MCP servers, initialize sessions, and expose their tool lists."""
    async with AsyncExitStack() as stack:
        sessions = {}
        for name, params in specs.items():
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = await session.list_tools()
            sessions[name] = {"session": session, "tools": tools.tools}
            if events: await events.put(ToolEvent("server", f"{name}: {len(tools.tools)} tools"))
        yield sessions


def playwright_spec() -> StdioServerParameters:
    """Start Playwright MCP with host and origin restrictions for the mock portal."""
    return StdioServerParameters(command="npx.cmd", args=["@playwright/mcp@latest", "--headless", "--allowed-hosts", "127.0.0.1,localhost", "--allowed-origins", "http://127.0.0.1:8100;http://localhost:8100"])


async def run_claude_agent(system: str, prompt: str, specs: dict[str, StdioServerParameters], model: str, effort: str = "low", events: asyncio.Queue | None = None) -> dict:
    """Run Claude's local MCP tool runner. Missing credentials/refusals return structured errors."""
    api_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key: return {"ok": False, "error": "ANTHROPIC_API_KEY is not configured"}
    allowlist = {"127.0.0.1:8100", "localhost:8100"}
    try:
        async with local_mcp_servers(specs, events) as servers:
            tools = []
            for name, bundle in servers.items():
                client = GuardedSession(bundle["session"], allowlist) if name == "playwright" else bundle["session"]
                for tool in bundle["tools"]:
                    tools.append(async_mcp_tool(tool, client, cache_control={"type": "ephemeral"}))
            client = AsyncAnthropic(api_key=api_key)
            kwargs = {"max_tokens": 16000, "model": model, "tools": tools, "messages": [{"role": "user", "content": prompt}], "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}], "output_config": {"effort": effort}, "fallbacks": "default", "betas": ["server-side-fallback-2026-07-01"]}
            runner = client.beta.messages.tool_runner(**kwargs)
            last = None
            async for message in runner:
                last = message
                if events: await events.put(ToolEvent("model", getattr(message, "stop_reason", "tool step")))
            if last is None: return {"ok": False, "error": "Claude returned no message"}
            stop_reason = getattr(last, "stop_reason", None)
            if stop_reason == "refusal": return {"ok": False, "error": "Claude refused the mission"}
            return {"ok": True, "stop_reason": stop_reason, "response": last}
    except Exception as exc:  # noqa: BLE001 - agent failures fall back safely
        return {"ok": False, "error": str(exc)}
