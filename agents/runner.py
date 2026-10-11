"""Shared agent runtime: model per role, LLM_MODE (live | replay | off), cost cap, cassettes.

- live:   calls Claude (tool runner for tool-using agents), records every agent run to
          agents/cassettes/<key>.json (committed, so a fresh clone can replay).
- replay: serves recordings back with zero API calls; a missing recording falls back to the
          agent's deterministic implementation (and says so in the timeline).
- off:    agents disabled; deterministic implementations only.

Safety rules enforced here, not just in prompts:
- prompt caching on every system prompt (+ top-level auto-cache for the growing transcript);
- `output_config.effort` set explicitly on every call; no thinking budget, no forced
  tool_choice (both 400 on Sonnet 5.5 / Opus 5.5);
- `stop_reason == "refusal"` is checked before content is read; Sonnet/Opus calls on the
  Claude API opt into server-side refusal fallback (`fallbacks="default"`);
- the summed cost of `response.usage` is checked after every call; over MAX_USD_PER_RUN the
  run aborts cleanly (BudgetExceeded).
Agents never receive full Aadhaar numbers or unpixelated fingerprints (callers pass masked
values / pixelated images only), and their output can only escalate a decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.settings import PRICES_PER_MTOK, settings

CASSETTES = Path(__file__).parent / "cassettes"
PROMPTS = Path(__file__).parent / "prompts"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

Emit = Callable[[dict], None]


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    limit_usd: float = field(default_factory=lambda: settings.max_usd_per_run)
    spent_usd: float = 0.0
    calls: int = 0

    def add(self, model: str, usage: Any) -> float:
        base = model.removeprefix("anthropic.")
        p_in, p_out, p_cache = PRICES_PER_MTOK.get(base, PRICES_PER_MTOK["claude-opus-5-5"])
        u = usage if isinstance(usage, dict) else usage.model_dump()
        cost = (
            (u.get("input_tokens") or 0) * p_in
            + (u.get("cache_creation_input_tokens") or 0) * p_in * 1.25
            + (u.get("cache_read_input_tokens") or 0) * p_cache
            + (u.get("output_tokens") or 0) * p_out
        ) / 1e6
        self.spent_usd += cost
        self.calls += 1
        if self.spent_usd > self.limit_usd:
            raise BudgetExceeded(
                f"run cost ${self.spent_usd:.3f} exceeded MAX_USD_PER_RUN=${self.limit_usd:.2f}")
        return cost


@dataclass(frozen=True)
class AgentSpec:
    name: str  # orchestrator | auditor | reviewer | notice
    model: str
    effort: str
    prompt_file: str
    max_turns: int = 12

    @property
    def system(self) -> str:
        return (PROMPTS / self.prompt_file).read_text()


def spec(name: str) -> AgentSpec:
    models = {"orchestrator": settings.orchestrator_model, "auditor": settings.auditor_model,
              "reviewer": settings.reviewer_model, "notice": settings.notice_model}
    effort = {"orchestrator": "medium", "auditor": "medium", "reviewer": "medium",
              "notice": "low"}
    turns = {"orchestrator": 8, "auditor": 25, "reviewer": 1, "notice": 1}
    return AgentSpec(name, models[name], effort[name], f"{name}.md", turns[name])


def model_id(model: str) -> str:
    return f"anthropic.{model}" if settings.llm_provider == "bedrock" else model


def make_client():
    """Async client for the configured provider (cloud credits can pay for Claude)."""
    import anthropic

    if settings.llm_provider == "bedrock":
        return anthropic.AsyncAnthropicBedrockMantle(aws_region=settings.aws_region or None)
    if settings.llm_provider == "foundry":
        return anthropic.AsyncAnthropicFoundry()
    return anthropic.AsyncAnthropic()


def _fallback_kwargs(model: str) -> dict:
    """Server-side refusal fallback: Claude API only, Sonnet/Opus only (Haiku has none)."""
    if settings.llm_provider == "anthropic" and not model.startswith("claude-haiku"):
        return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    return {}


def cassette_key(agent: str, model: str, payload: Any) -> str:
    raw = json.dumps({"agent": agent, "model": model, "payload": payload}, sort_keys=True,
                     default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def load_cassette(key: str) -> dict | None:
    p = CASSETTES / f"{key}.json"
    return json.loads(p.read_text()) if p.exists() else None


def save_cassette(key: str, data: dict) -> None:
    CASSETTES.mkdir(parents=True, exist_ok=True)
    (CASSETTES / f"{key}.json").write_text(json.dumps(data, indent=1, default=str))


_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def parse_json_tail(text: str) -> dict | None:
    """The agents end with a ```json {...}``` block; take the last one."""
    blocks = _JSON_FENCE.findall(text or "")
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            continue
    return None


@dataclass
class AgentRun:
    agent: str
    mode: str  # live | replay | deterministic
    output: dict | None
    text: str = ""
    events: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0


async def run_llm(
    sp: AgentSpec,
    user_content: list[dict] | str,
    payload_for_key: Any,
    emit: Emit,
    budget: Budget,
    tools: list | None = None,
    recorder: list[dict] | None = None,
    finalize: Callable[[dict | None], dict | None] | None = None,
) -> AgentRun | None:
    """Run one agent through Claude (live) or its recording (replay). Returns None when the
    caller should use its deterministic implementation (LLM_MODE=off or no recording).

    `recorder`: an external event list that `emit` already appends to (the orchestrator uses
    it so sub-agent events land in its cassette). `finalize` post-processes the output
    before it is recorded."""
    mode = settings.llm_mode
    key = cassette_key(sp.name, sp.model, payload_for_key)
    if mode == "off":
        return None
    if mode == "replay":
        rec = load_cassette(key)
        if rec is None:
            emit({"agent": sp.name, "type": "note",
                  "text": "No recording for this input (replay mode): deterministic fallback"})
            return None
        for ev in rec["events"]:
            emit({**ev, "replayed": True})
        return AgentRun(sp.name, "replay", rec.get("output"), rec.get("text", ""), rec["events"])

    client = make_client()
    events: list[dict] = recorder if recorder is not None else []

    def record(ev: dict) -> None:
        if recorder is None:
            events.append(ev)
        emit(ev)

    system = [{"type": "text", "text": sp.system, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": user_content}]
    common = dict(model=model_id(sp.model), max_tokens=8000, system=system, messages=messages,
                  output_config={"effort": sp.effort}, cache_control={"type": "ephemeral"},
                  **_fallback_kwargs(sp.model))
    record({"agent": sp.name, "type": "start", "model": sp.model, "effort": sp.effort})
    spent0 = budget.spent_usd
    text = ""
    if tools:
        runner = client.beta.messages.tool_runner(tools=tools, max_iterations=sp.max_turns,
                                                  **common)
        async for message in runner:
            budget.add(sp.model, message.usage)
            if message.stop_reason == "refusal":
                record({"agent": sp.name, "type": "refusal",
                        "text": "Model declined; deterministic fallback used"})
                return None
            for b in message.content:
                if b.type == "text" and b.text.strip():
                    text = b.text
                    record({"agent": sp.name, "type": "text", "text": b.text[:2000]})
                elif b.type == "tool_use":
                    record({"agent": sp.name, "type": "tool", "tool": b.name,
                            "input": _redact_input(b.input)})
    else:
        resp = await client.beta.messages.create(**common)
        budget.add(sp.model, resp.usage)
        if resp.stop_reason == "refusal":
            record({"agent": sp.name, "type": "refusal",
                    "text": "Model declined; deterministic fallback used"})
            return None
        text = "".join(b.text for b in resp.content if b.type == "text")
        record({"agent": sp.name, "type": "text", "text": text[:2000]})
    out = parse_json_tail(text)
    if finalize is not None:
        out = finalize(out)
    record({"agent": sp.name, "type": "result", "output": out})
    save_cassette(key, {"agent": sp.name, "model": sp.model, "events": events, "text": text,
                        "output": out})
    return AgentRun(sp.name, "live", out, text, events, budget.spent_usd - spent0)


def _redact_input(inp: Any) -> Any:
    """Timeline copies of tool inputs: drop anything that looks like a long digit run."""
    s = json.dumps(inp, default=str)
    s = re.sub(r"\d{8,}", lambda m: "X" * (len(m.group()) - 4) + m.group()[-4:], s)
    return json.loads(s)
