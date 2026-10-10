"""System-One deterministic decision engine.

Rules are authoritative. Optional backends may only make an outcome more restrictive.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from time import perf_counter
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ..settings import settings

Action = Literal["PUBLISH", "REDACT_AND_PUBLISH", "BLOCK_FOR_REVIEW"]


class DecisionFinding(BaseModel):
    type: str
    confidence: float = Field(ge=0, le=1)
    sources: list[str] = Field(default_factory=list)
    area_ratio: float = Field(default=0, ge=0)


class DecisionRequest(BaseModel):
    doc_id: str
    page: int
    text_layer: bool
    ocr_quality: float = Field(ge=0, le=1)
    findings: list[DecisionFinding] = Field(default_factory=list)
    verification: Literal["pass", "fail", "not_run"] = "not_run"


class DecisionResponse(BaseModel):
    action: Action
    confidence: float
    reason_codes: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    backend: str = "rules"
    fallback: bool = False
    latency_ms: float = 0


class DecisionBackend(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResponse: ...


class RulesBackend:
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        started = perf_counter()
        codes: list[str] = []
        reasons: list[str] = []
        actionable = [f for f in request.findings if f.type in {"AADHAAR", "VID", "FINGERPRINT"}]

        if request.verification == "fail":
            action = "BLOCK_FOR_REVIEW"
            codes.append("VERIFICATION_FAILED")
            reasons.append("Independent redaction verification failed.")
        elif any(f.type in {"AADHAAR", "VID"} for f in actionable):
            action = "REDACT_AND_PUBLISH"
            codes.append("SENSITIVE_IDENTIFIER_DETECTED")
            reasons.append("Aadhaar or VID content requires redaction.")
        elif any(f.type == "FINGERPRINT" and f.confidence >= settings.decision_fingerprint_threshold for f in actionable):
            action = "REDACT_AND_PUBLISH"
            codes.append("FINGERPRINT_THRESHOLD_MET")
            reasons.append("A fingerprint finding met the configured sensitive-confidence threshold.")
        elif any(
            f.type == "FINGERPRINT"
            and settings.decision_low_conf_threshold <= f.confidence < settings.decision_fingerprint_threshold
            and len(f.sources) <= 1
            for f in actionable
        ):
            action = "REDACT_AND_PUBLISH"
            codes.append("LOW_CONFIDENCE_FAIL_SAFE")
            reasons.append("A single detector reported a low-confidence fingerprint; fail-safe redaction is required.")
        elif not request.text_layer and request.ocr_quality < settings.decision_scanned_ocr_threshold:
            action = "BLOCK_FOR_REVIEW"
            codes.append("LOW_OCR_CONFIDENCE")
            reasons.append("Scanned-page OCR confidence is too low to prove absence of sensitive content.")
        else:
            action = "PUBLISH"
            codes.append("NO_SENSITIVE_FINDINGS")
            reasons.append("Required checks completed and no unresolved sensitive findings remain.")

        confidence = max((f.confidence for f in actionable), default=1.0 if action == "PUBLISH" else 0.0)
        return DecisionResponse(
            action=action,
            confidence=round(confidence, 3),
            reason_codes=codes,
            reasons=reasons,
            backend="rules",
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )


class NotConfigured(RuntimeError):
    pass


class JevBackend:
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        raise NotConfigured("Jev integration is not configured; using deterministic rules")


def _rank(action: str) -> int:
    return {"PUBLISH": 0, "REDACT_AND_PUBLISH": 1, "BLOCK_FOR_REVIEW": 2}[action]


def _guard(answer: DecisionResponse, baseline: DecisionResponse) -> DecisionResponse:
    if _rank(answer.action) < _rank(baseline.action):
        return baseline.model_copy(update={
            "reason_codes": [*baseline.reason_codes, "OPTIONAL_BACKEND_DOWNGRADE_BLOCKED"],
            "reasons": [*baseline.reasons, "Optional backend attempted an unsafe downgrade; rules remained authoritative."],
            "backend": "rules-guard",
            "fallback": True,
        })
    return answer


def decide(request: DecisionRequest, backend: DecisionBackend | None = None) -> DecisionResponse:
    rules = RulesBackend()
    baseline = rules.decide(request)
    selected = backend
    if selected is None:
        selected = JevBackend() if settings.decision_backend == "jev" else None
        if selected is None:
            return baseline
    try:
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(selected.decide, request)
        try:
            answer = future.result(timeout=settings.decision_timeout_ms / 1000)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return _guard(answer, baseline)
    except (NotConfigured, FutureTimeout, TimeoutError, Exception) as exc:
        return baseline.model_copy(update={
            "reason_codes": [*baseline.reason_codes, "OPTIONAL_BACKEND_FALLBACK"],
            "reasons": [*baseline.reasons, f"Optional decision backend unavailable; deterministic rules used ({type(exc).__name__})."],
            "backend": "rules-fallback",
            "fallback": True,
        })
