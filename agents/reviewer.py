from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewAction = Literal["ADD_REDACTION", "SEND_TO_HUMAN", "CONFIRM"]


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: ReviewAction
    reason: str = Field(min_length=1, max_length=500)
    bbox_pt: tuple[float, float, float, float] | None = None


def guard_review(decision: dict | ReviewDecision) -> ReviewDecision:
    """Accept only escalation/confirmation actions; invalid model output fails closed."""
    try:
        parsed = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    except Exception as exc:  # noqa: BLE001
        return ReviewDecision(action="SEND_TO_HUMAN", reason=f"Invalid reviewer output: {exc}")
    return parsed if parsed.action in {"ADD_REDACTION", "SEND_TO_HUMAN", "CONFIRM"} else ReviewDecision(action="SEND_TO_HUMAN", reason="Unsupported reviewer action")


def review_page(doc_id: str, page: int, reason: str, bbox_pt: tuple[float, float, float, float] | None = None) -> dict:
    decision = guard_review({"action": "SEND_TO_HUMAN", "reason": reason, "bbox_pt": bbox_pt})
    return {"doc_id": doc_id, "page": page, "action": decision.action, "reason": decision.reason, "bbox_pt": decision.bbox_pt, "card": f"Page {page + 1} requires clerk review: {decision.reason}"}
