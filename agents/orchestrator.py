"""Orchestrator: plans a case and delegates to Auditor / Forensic Tamper Reviewer / Notice.

Cases:
- {"kind": "audit", "start_url": ...}: find exposed IDs on an allowlisted portal, then draft
  a DPDP/I4C notice for the site.
- {"kind": "forgery", "report": VerifyReport, ...}: explain a failed verification, escalate,
  draft a notice.
Live: Claude (ORCHESTRATOR_MODEL) calls the specialists as tools through the tool runner.
Otherwise: the same specialists in a fixed deterministic plan. Either way the deterministic
verdicts stand; the only decision an agent can make is `escalate` (stricter, never looser).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from agents import auditor, notice, reviewer
from agents.runner import AgentRun, Budget, BudgetExceeded, Emit, run_llm, spec
from backend.app.core.decision import GateResult, escalate
from backend.app.settings import settings


async def _deterministic(case: dict, ctx: dict, emit: Emit, budget: Budget) -> dict:
    out: dict[str, Any] = {"actions_taken": [], "escalated": False}
    if case["kind"] == "audit":
        a = await auditor.audit(case["start_url"], emit, budget,
                                include_uidai=case.get("include_uidai", True))
        out["audit"] = a.output
        out["actions_taken"].append("audited portal")
        if a.output.get("exposed"):
            n = await notice.draft({"kind": "exposure", "case_id": case["case_id"],
                                    "recipient": "Sunrise Stays (mock portal)", **a.output,
                                    "masked": [v for e in a.output["exposed"]
                                               for v in e.get("masked_values", [])]},
                                   emit, budget)
            out["notice"] = n.output["notice_markdown"]
            out["escalated"] = True
            out["actions_taken"].append("drafted DPDP/I4C notice")
            emit({"agent": "notice", "type": "notice", "step": "notice",
                  "say": "Takedown notice drafted for the hotel under the DPDP Act 2023, plus "
                         "how to report on cybercrime.gov.in / 1930."})
        n_exp = len(a.output.get("exposed", []))
        out["exposed_count"] = n_exp
        out["risk"] = "high" if n_exp >= 2 else "medium" if n_exp == 1 else "none"
        out["summary"] = (f"{n_exp} copies of ID cards are publicly visible on this website."
                          if n_exp else "No exposed ID documents found on this website.")
    else:
        rep = case["report"]
        emit({"agent": "reviewer", "type": "tool", "step": "review",
              "say": "Comparing the copy against its seal, tile by tile…"})
        r = await reviewer.review(rep, ctx.get("image"), emit, budget, faces=ctx.get("faces"))
        out["review"] = r.output
        emit({"agent": "reviewer", "type": "review", "step": "review",
              "attack_type": r.output.get("attack_type"),
              "say": r.output.get("explanation", "")})
        out["actions_taken"].append("forensic review")
        if r.output.get("recommend_escalation"):
            g = escalate(GateResult(case.get("decision", "ARMOR_AND_ISSUE"), ()),
                         "BLOCK_FOR_REVIEW", r.output.get("attack_type", "tamper"))
            out["decision"] = g.decision
            out["escalated"] = True
            emit({"agent": "orchestrator", "type": "escalation", "decision": g.decision,
                  "step": "review", "text": f"Escalated: {r.output.get('attack_type')}",
                  "say": "Flagged: this copy must not be accepted."})
            n = await notice.draft({"kind": "forgery", "case_id": case["case_id"],
                                    "recipient": case.get("recipient", "the recipient"),
                                    "purpose": rep.get("purpose"), "detail": rep.get("detail"),
                                    "attack_type": r.output.get("attack_type"),
                                    "armor_id": rep.get("armor_id")}, emit, budget)
            out["notice"] = n.output["notice_markdown"]
            out["actions_taken"].append("drafted notice")
            emit({"agent": "notice", "type": "notice", "step": "notice",
                  "say": "Complaint draft ready in case someone misuses the edited copy."})
        out["summary"] = r.output.get("explanation", "")
        out["risk"] = "high" if out["escalated"] else "none"
    return out


def _live_tools(case: dict, ctx: dict, emit: Emit, budget: Budget, artifacts: dict):
    from anthropic import beta_async_tool

    @beta_async_tool
    async def run_auditor(start_url: str) -> str:
        """Scan an allowlisted portal for identity documents published without masking.

        Args:
            start_url: Portal URL to start from (must be on the allowlist).
        """
        a = await auditor.audit(start_url, emit, budget,
                                include_uidai=case.get("include_uidai", True))
        artifacts["audit"] = a.output
        return json.dumps(a.output)

    @beta_async_tool
    async def review_tamper() -> str:
        """Ask the Forensic Tamper Reviewer to explain this case's verification report."""
        r = await reviewer.review(case["report"], ctx.get("image"), emit, budget,
                                  faces=ctx.get("faces"))
        artifacts["review"] = r.output
        return json.dumps(r.output)

    @beta_async_tool
    async def draft_notice(recipient: str) -> str:
        """Draft a DPDP Act 2023 / I4C notice for the citizen to review.

        Args:
            recipient: Organisation the notice is addressed to.
        """
        if case["kind"] == "audit":
            a = artifacts.get("audit") or {}
            c = {"kind": "exposure", **a, "masked": [v for e in a.get("exposed", [])
                                                     for v in e.get("masked_values", [])]}
        else:
            rep = case["report"]
            c = {"kind": "forgery", "purpose": rep.get("purpose"), "detail": rep.get("detail"),
                 "attack_type": (artifacts.get("review") or {}).get("attack_type"),
                 "armor_id": rep.get("armor_id")}
        n = await notice.draft({**c, "case_id": case["case_id"], "recipient": recipient}, emit,
                               budget)
        artifacts["notice"] = n.output["notice_markdown"]
        return "Notice drafted (shown to the citizen for review)."

    @beta_async_tool
    async def escalate_case(reason: str) -> str:
        """Send this case to human review (BLOCK_FOR_REVIEW). You cannot clear a case.

        Args:
            reason: Short reason for the escalation.
        """
        g = escalate(GateResult(case.get("decision", "ARMOR_AND_ISSUE"), ()),
                     "BLOCK_FOR_REVIEW", reason)
        artifacts["escalated"] = True
        artifacts["decision"] = g.decision
        emit({"agent": "orchestrator", "type": "escalation", "decision": g.decision,
              "text": reason})
        return f"Decision is now {g.decision}."

    tools = [draft_notice, escalate_case]
    tools.insert(0, run_auditor if case["kind"] == "audit" else review_tamper)
    return tools


async def run_case(case: dict, emit: Emit, ctx: dict | None = None) -> dict:
    """Run a case end to end. Never raises for budget/LLM problems: reports them instead."""
    case = {"case_id": uuid.uuid4().hex[:10], **case}
    ctx = ctx or {}
    budget = Budget()
    emit({"agent": "orchestrator", "type": "start", "case": case["kind"], "step": "scan",
          "say": "Starting a leak scan" if case["kind"] == "audit"
          else "Starting a forensic check of the edited copy",
          "mode": settings.llm_mode, "budget_usd": budget.limit_usd,
          "models": {k: spec(k).model for k in ("orchestrator", "auditor", "reviewer", "notice")}})
    payload = {k: v for k, v in case.items() if k not in ("case_id",)}
    result: dict
    try:
        run: AgentRun | None = None
        if settings.llm_mode == "live":
            artifacts: dict = {}
            events: list[dict] = []

            def rec(ev: dict) -> None:
                events.append(ev)
                emit(ev)

            tools = _live_tools(case, ctx, rec, budget, artifacts)
            brief = json.dumps({k: v for k, v in payload.items() if k != "image"}, default=str)
            run = await run_llm(spec("orchestrator"), f"Case: {brief}", payload, rec, budget,
                                tools=tools, recorder=events,
                                finalize=lambda o: {**(o or {}), **artifacts})
        elif settings.llm_mode == "replay":
            run = await run_llm(spec("orchestrator"), "", payload, emit, budget)
        result = run.output if run and run.output else await _deterministic(case, ctx, emit,
                                                                            budget)
        result["mode"] = run.mode if run and run.output else "deterministic"
    except BudgetExceeded as e:
        emit({"agent": "orchestrator", "type": "error", "text": str(e)})
        result = {"error": str(e), "aborted": True}
    result["cost_usd"] = round(budget.spent_usd, 4)
    result["case_id"] = case["case_id"]
    emit({"agent": "orchestrator", "type": "done", "step": "done", "result": result,
          "say": result.get("summary") or result.get("error", "Done")})
    return result
