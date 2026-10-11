"""Legal Notice Drafter: deterministic Jinja template; Claude (NOTICE_MODEL) only polishes the
facts paragraph. Drafts are for the citizen to review — not legal advice.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from agents.runner import AgentRun, Budget, Emit, run_llm, spec

TEMPLATE = (Path(__file__).parent / "prompts" / "notice_template.md.j2").read_text()


def _facts(case: dict) -> str:
    kind = case.get("kind")
    if kind == "exposure":
        n = len(case.get("exposed", []))
        lines = [f"On {case.get('found_on', date.today().isoformat())}, an automated audit found "
                 f"{n} identity document(s) published without masking on "
                 f"{case.get('site', 'your website')}."]
        for e in case.get("exposed", [])[:5]:
            lines.append(f"- {e.get('url')}: {', '.join(e.get('types', []))}")
        return "\n".join(lines)
    return (f"A copy of my identity document that I shared only for "
            f"\"{case.get('purpose', 'a stated purpose')}\" was altered and presented again. "
            f"Verification of the sealed copy reported: {case.get('detail', 'forgery detected')} "
            f"({case.get('attack_type', 'edit')}).")


def render(case: dict, facts: str | None = None) -> str:
    env = Environment(undefined=StrictUndefined, autoescape=False)
    return env.from_string(TEMPLATE).render(
        today=date.today().isoformat(), recipient=case.get("recipient", "the data fiduciary"),
        facts=facts or _facts(case), case_id=case.get("case_id", "-"),
        armor_id=case.get("armor_id"), masked=case.get("masked", []))


async def draft(case: dict, emit: Emit, budget: Budget) -> AgentRun:
    base = _facts(case)
    run = await run_llm(spec("notice"), f"Facts paragraph to polish:\n{base}",
                        {"facts": base}, emit, budget)
    facts = (run.output or {}).get("facts") if run else None
    if facts and re.search(r"\d{8,}", re.sub(r"[\s-]", "", facts)):
        facts = None  # never let a model put a long number into a notice
    text = render(case, facts)
    out = {"notice_markdown": text, "polished": bool(facts)}
    if run is None:
        emit({"agent": "notice", "type": "result", "output": {"polished": False},
              "deterministic": True})
        return AgentRun("notice", "deterministic", out)
    run.output = out
    return run
