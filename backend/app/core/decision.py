"""System-One decision engine: typed, pure, fast. Deterministic rules decide; LLMs never do.

Two gates share this module:
- `decide_armor`: SurakshitID ID-document gate (ARMOR_AND_ISSUE / INSUFFICIENT_PURPOSE /
  BLOCK_FOR_REVIEW). First matching rule wins; every safety rule comes before purpose rules.
- `decide_page`: ThumbShield deed-page gate (PUBLISH / REDACT_AND_PUBLISH / BLOCK_FOR_REVIEW).

No I/O, no allocation-heavy work: a call takes microseconds (tests assert < 5 ms). An agent
may only escalate a result (`escalate`), never relax one.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from .presets import PRESETS
from .types import REDACT_TYPES, Finding

ArmorDecision = Literal["ARMOR_AND_ISSUE", "INSUFFICIENT_PURPOSE", "BLOCK_FOR_REVIEW"]
PageDecision = Literal["PUBLISH", "REDACT_AND_PUBLISH", "BLOCK_FOR_REVIEW"]

MIN_BLUR_SCORE = 60.0  # variance of Laplacian on the normalised grey image
MIN_OCR_QUALITY_ID = 0.55
MIN_OCR_QUALITY_PAGE = 0.55
MIN_RECIPIENT_CHARS = 3
ID_TOKENS = frozenset({"AADHAAR", "VID", "MASKED_AADHAAR", "PAN", "QR"})
_SEVERITY = {"ARMOR_AND_ISSUE": 0, "INSUFFICIENT_PURPOSE": 1, "BLOCK_FOR_REVIEW": 2}


@dataclass(frozen=True, slots=True)
class ArmorSummary:
    preset: str | None
    recipient: str
    valid_days: int
    doc_found: bool
    blur_score: float
    ocr_quality: float
    finding_types: tuple[str, ...]
    unmaskable: int = 0  # findings that must be hidden but have no usable geometry
    verified_tokens: int = 0  # Verhoeff-valid Aadhaar/VID, PAN, QR: proof the key text is legible
    verification: Literal["pending", "pass", "fail"] = "pending"


@dataclass(frozen=True, slots=True)
class GateResult:
    decision: str
    reasons: tuple[str, ...]
    elapsed_us: float = field(default=0.0, compare=False)


def needs_care(s: ArmorSummary) -> bool:
    """Readable enough to find the ID, not enough to prove every character: issue the copy
    but hide MORE (whole number, every number, anything QR-like) instead of refusing."""
    return s.ocr_quality < MIN_OCR_QUALITY_ID or not s.verified_tokens


def _armor_rules(s: ArmorSummary) -> tuple[str, tuple[str, ...]]:
    block: list[str] = []
    has_id = bool(ID_TOKENS.intersection(s.finding_types))
    if s.blur_score < MIN_BLUR_SCORE:
        block.append("The photo is too blurry to read")
    elif not has_id:
        block.append("We couldn't find an Aadhaar number, PAN or QR code in this photo"
                     if s.doc_found else "We couldn't find an ID card in this photo")
    if s.unmaskable:
        block.append(f"{s.unmaskable} private detail(s) couldn't be located precisely")
    if block:
        return "BLOCK_FOR_REVIEW", ("Cannot verify safely", *block)

    p = PRESETS.get(s.preset or "")
    purpose: list[str] = []
    if p is None:
        purpose.append("Choose what this copy is for")
    if len(s.recipient.strip()) < MIN_RECIPIENT_CHARS:
        purpose.append("Say who will receive this copy (e.g. 'Taj Hotel, Goa')")
    if p is not None and not 1 <= s.valid_days <= p.max_days:
        purpose.append(f"For {p.label}, a copy can be valid for 1–{p.max_days} days")
    if purpose:
        return "INSUFFICIENT_PURPOSE", tuple(purpose)

    if s.verification == "fail":
        return "BLOCK_FOR_REVIEW", ("Cannot verify safely",
                                    "Our final check found something still visible")
    reasons = [f"Locked to {p.label}"]
    if needs_care(s):
        reasons.append("Some text was hard to read, so we hid extra details to be safe")
    return "ARMOR_AND_ISSUE", tuple(reasons)


def decide_armor(s: ArmorSummary) -> GateResult:
    t0 = time.perf_counter()
    d, reasons = _armor_rules(s)
    return GateResult(d, reasons, (time.perf_counter() - t0) * 1e6)


def escalate(current: GateResult, proposed: str, reason: str) -> GateResult:
    """Apply an agent's suggestion only if it is stricter than the current decision."""
    if _SEVERITY.get(proposed, -1) > _SEVERITY.get(current.decision, -1):
        return GateResult(proposed, (*current.reasons, f"Escalated: {reason}"))
    return current


# ---- ThumbShield deed pages ------------------------------------------------------------

LABELS = {
    "FINGERPRINT": ("thumb impression", "thumb impressions"),
    "AADHAAR": ("Aadhaar number", "Aadhaar numbers"),
    "VID": ("Aadhaar VID", "Aadhaar VIDs"),
    "MASKED_AADHAAR": ("masked Aadhaar (already compliant)", "masked Aadhaar (already compliant)"),
}


def decide_page(findings: list[Finding], text_layer: bool, ocr_quality: float
                ) -> tuple[str, list[str]]:
    counts = Counter(f.type for f in findings)
    reasons = [f"{n} {LABELS[t][n != 1]}" for t, n in sorted(counts.items(), key=lambda kv: kv[0])]
    if not text_layer and ocr_quality < MIN_OCR_QUALITY_PAGE:
        return "BLOCK_FOR_REVIEW", [
            f"OCR quality {ocr_quality:.2f} too low to prove absence",
            *reasons,
        ]
    if any(f.redact and f.type in REDACT_TYPES for f in findings):
        return "REDACT_AND_PUBLISH", reasons
    return "PUBLISH", reasons or ["nothing sensitive found"]
