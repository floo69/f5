"""Shared data types for the deterministic core.

Coordinates: PDF points, top-left origin, y down (PyMuPDF), as in docs/DATA_CONTRACT.md.
Bboxes are [x0, y0, x1, y1]. Pages are 0-indexed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BBox = tuple[float, float, float, float]

FindingType = Literal["FINGERPRINT", "AADHAAR", "VID", "MASKED_AADHAAR"]
FindingSource = Literal["textlayer", "ocr", "classical", "onnx"]

# Types that must be destroyed before publication. MASKED_AADHAAR is already compliant.
REDACT_TYPES: frozenset[str] = frozenset({"FINGERPRINT", "AADHAAR", "VID"})

# The only text redact.py may write inside a redacted rect; verify.py whitelists exactly these.
REDACTION_LABELS: dict[str, str] = {
    "FINGERPRINT": "THUMB IMPRESSION REDACTED",
    "AADHAAR": "AADHAAR REDACTED",
    "VID": "AADHAAR REDACTED",
}


class Word(BaseModel):
    text: str
    bbox_pt: BBox
    conf: float  # 0..1; 1.0 for text-layer words
    line_id: int  # same value = same text line on the page


class PageText(BaseModel):
    words: list[Word]
    text_layer: bool
    ocr_quality: float  # mean confidence over alphanumeric words, 0..1 (1.0 for text layer)


class Finding(BaseModel):
    type: FindingType
    page: int
    bbox_pt: BBox
    confidence: float
    source: FindingSource
    value_masked: str | None = None  # e.g. "XXXX XXXX 0124"; NEVER a full number
    redact: bool = Field(default=True)
    # AADHAAR/VID: one bbox per digit in reading order (lets presets mask the first 8 digits
    # only), split by character width inside each OCR word.
    parts_pt: list[BBox] = Field(default_factory=list)
