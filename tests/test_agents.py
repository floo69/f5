"""Agent layer without API calls: allowlist, budget, cassettes, guards, deterministic agents,
a fake Claude client for the live plumbing, and a real stdio MCP round trip."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agents import auditor, orchestrator, runner
from backend.app.core import allowlist
from backend.app.settings import settings
from mock_portal.app import app as portal_app


@pytest.fixture()
def portal(monkeypatch):
    """Route allowlisted fetches to the in-process mock portal."""
    monkeypatch.setattr(allowlist, "_client",
                        lambda: TestClient(portal_app, base_url="http://localhost:8100"))


@pytest.fixture()
def mode(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "CASSETTES", tmp_path / "cassettes")

    def set_mode(m: str) -> None:
        monkeypatch.setattr(settings, "llm_mode", m)

    return set_mode


def test_allowlist_enforced_in_code():
    assert allowlist.allowed("http://localhost:8100/guests/1")
    assert allowlist.allowed("http://127.0.0.1:8100/")
    for bad in ("https://uidai.gov.in/", "http://localhost:8000/", "file:///etc/passwd",
                "http://localhost:8100.evil.com/", "javascript:alert(1)"):
        assert not allowlist.allowed(bad), bad
        with pytest.raises(allowlist.BlockedHost):
            allowlist.fetch(bad)


def test_budget_aborts_run():
    b = runner.Budget(limit_usd=0.01)
    cost = b.add("claude-sonnet-5-5", {"input_tokens": 1000, "output_tokens": 200,
                                       "cache_read_input_tokens": 10000})
    assert cost == pytest.approx((1000 * 2 + 200 * 10 + 10000 * 0.2) / 1e6)
    with pytest.raises(runner.BudgetExceeded):
        b.add("claude-sonnet-5-5", {"input_tokens": 10000, "output_tokens": 2000})


def test_fallback_only_where_supported(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    assert runner._fallback_kwargs("claude-sonnet-5-5")["fallbacks"] == "default"
    assert runner._fallback_kwargs("claude-haiku-5-5") == {}
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    assert runner._fallback_kwargs("claude-sonnet-5-5") == {}
    assert runner.model_id("claude-sonnet-5-5") == "anthropic.claude-sonnet-5-5"


class _FakeMessages:
    def __init__(self, text: str, stop: str = "end_turn"):
        self.text, self.stop, self.calls = text, stop, []

    async def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)],
            usage={"input_tokens": 500, "output_tokens": 80, "cache_read_input_tokens": 0,
                   "cache_creation_input_tokens": 400})


def test_live_plumbing_with_fake_client_then_replay(monkeypatch, mode):
    fake = _FakeMessages('Done.\n```json\n{"attack_type": "crop", '
                         '"explanation": "cut", "recommend_escalation": false}\n```')
    monkeypatch.setattr(runner, "make_client",
                        lambda: SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    mode("live")
    events: list[dict] = []
    b = runner.Budget()
    run = asyncio.run(runner.run_llm(runner.spec("reviewer"), "x", {"k": 1}, events.append, b))
    kw = fake.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["output_config"] == {"effort": "medium"}
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["fallbacks"] == "default" and "thinking" not in kw and "tool_choice" not in kw
    assert run.output["attack_type"] == "crop" and b.spent_usd > 0
    # replay serves the recording with zero calls
    mode("replay")
    fake.calls.clear()
    replayed: list[dict] = []
    r2 = asyncio.run(runner.run_llm(runner.spec("reviewer"), "x", {"k": 1}, replayed.append,
                                    runner.Budget()))
    assert r2.mode == "replay" and r2.output == run.output and not fake.calls
    assert all(e.get("replayed") for e in replayed)


def test_refusal_falls_back(monkeypatch, mode):
    fake = _FakeMessages("", stop="refusal")
    monkeypatch.setattr(runner, "make_client",
                        lambda: SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    mode("live")
    events: list[dict] = []
    assert asyncio.run(runner.run_llm(runner.spec("notice"), "x", {}, events.append,
                                      runner.Budget())) is None
    assert events[-1]["type"] == "refusal"
    assert "fallbacks" not in fake.calls[0]  # Haiku: no server-side fallback


def test_guarded_session_blocks():
    calls = []

    class S:
        async def call_tool(self, name, arguments=None, **kw):
            calls.append(name)
            text = "Page URL: https://uidai.gov.in/" if name == "browser_click" else "ok"
            return SimpleNamespace(content=[SimpleNamespace(text=text)])

    events: list[dict] = []
    g = auditor.GuardedSession(S(), events.append)
    r = asyncio.run(g.call_tool("browser_navigate", {"url": "https://uidai.gov.in/"}))
    assert r.is_error and calls == []
    r = asyncio.run(g.call_tool("browser_type", {"text": "482913"}))
    assert r.is_error
    r = asyncio.run(g.call_tool("browser_click", {"ref": "e1"}))
    assert r.is_error and calls == ["browser_click", "browser_navigate_back"]
    assert sum(e["type"] == "blocked" for e in events) == 3


def test_deterministic_audit_finds_leaks_and_stops_at_otp(portal, mode):
    mode("off")
    events: list[dict] = []
    res = asyncio.run(orchestrator.run_case({"kind": "audit",
                                             "start_url": "http://localhost:8100/"},
                                            events.append))
    exposed = res["audit"]["exposed"]
    urls = sorted(e["url"].rsplit("/", 1)[-1] for e in exposed)
    assert urls == ["kyc_101.jpg", "kyc_102.jpg", "kyc_103.jpg"]  # 104 is properly masked
    assert res["audit"]["uidai_mock_reached_otp_step"] is True
    assert any(e["type"] == "handover" for e in events)
    assert "DPDP" in res["notice"] and res["escalated"] and res["cost_usd"] == 0
    blob = json.dumps(events) + res["notice"]
    assert not re.search(r"\d{12}", re.sub(r"[\s-]", "", blob.replace("0000", "")))


def test_forgery_case_escalates(mode):
    mode("off")
    report = {"status": "FORGERY_DETECTED", "armor_id": "SKID-AAAA-BBBB",
              "purpose": "HOTEL CHECK-IN ONLY", "altered_regions": [[32, 64, 160, 192]],
              "altered_tiles": 16, "total_tiles": 600, "detail": "16 of 600 tiles altered",
              "width": 1011, "height": 800, "tile_px": 32}
    events: list[dict] = []
    res = asyncio.run(orchestrator.run_case({"kind": "forgery", "report": report},
                                            events.append, {"faces": [[40, 60, 200, 220]]}))
    assert res["review"]["attack_type"] == "photo_substitution"
    assert res["decision"] == "BLOCK_FOR_REVIEW" and res["escalated"]
    assert "SKID-AAAA-BBBB" in res["notice"]


def test_scanner_mcp_server_over_stdio():
    from anthropic.lib.tools.mcp import async_mcp_tool
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "mcp_servers.scanner_server"])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            names = {t.name for t in tools}
            converted = [async_mcp_tool(t, s) for t in tools]
            res = await s.call_tool(name="scan_url", arguments={"url": "https://uidai.gov.in/x"})
            return names, converted, res

    names, converted, res = asyncio.run(go())
    assert {"scan_url", "scan_file", "list_page_assets"} <= names
    assert len(converted) == len(names)
    assert "allowlist" in res.content[0].text


def test_agents_sse_endpoint(portal, mode):
    from backend.app import main

    mode("off")
    with TestClient(main.app) as c:
        assert c.get("/api/agents/config").json()["models"]["notice"] == "claude-haiku-5-5"
        assert c.get("/api/agents/run", params={"case": "audit",
                                                "start_url": "https://uidai.gov.in/"}
                     ).status_code == 403
        with c.stream("GET", "/api/agents/run", params={"case": "audit"}) as r:
            body = "".join(r.iter_text())
    assert "event: done" in body and "kyc_101.jpg" in body
