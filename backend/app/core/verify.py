"""Fail-closed verification of a redacted PDF.

Re-opens the output and re-runs detection from scratch. FAIL if:
- any AADHAAR/VID or FINGERPRINT is found outside an already-redacted rect;
- any text inside a redacted rect is something other than our own label (or contains a digit);
- any embedded image still has non-uniform pixels inside a redacted rect.
"""

from __future__ import annotations

import re
import time

import numpy as np
import pymupdf
from pydantic import BaseModel

from backend.app.core import aadhaar, fp_classical, ocr
from backend.app.core.types import REDACTION_LABELS, BBox

ALLOWED_LABEL_TEXT = {s for label in REDACTION_LABELS.values() for s in (label, *label.split())}
# A detection counts as "already redacted" if this fraction of its area lies in redacted rects.
COVERED_FRACTION = 0.5


class Problem(BaseModel):
    page: int
    type: str
    bbox_pt: BBox
    detail: str


class Verification(BaseModel):
    status: str  # "pass" | "fail"
    problems: list[Problem]
    timings_ms: dict[str, float] = {}


def _covered(bbox: BBox, rects: list[pymupdf.Rect]) -> bool:
    b = pymupdf.Rect(bbox)
    if b.is_empty:
        return True
    inside = sum((b & r).get_area() for r in rects)
    return inside >= COVERED_FRACTION * b.get_area()


def _render_gray(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)


def _image_pixels_left(
    doc: pymupdf.Document, page: pymupdf.Page, rects: list[pymupdf.Rect]
) -> bool:
    for img in page.get_images(full=True):
        xref = img[0]
        for q in page.get_image_rects(xref):
            hits = [q & r for r in rects if q.intersects(r)]
            if not hits:
                continue
            pm = pymupdf.Pixmap(doc, xref)
            a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)
            sx, sy = pm.width / q.width, pm.height / q.height
            for i in hits:
                # 1 px inset: resampling at the rect border may touch neighbouring pixels
                y0, y1 = int((i.y0 - q.y0) * sy) + 1, int((i.y1 - q.y0) * sy) - 1
                x0, x1 = int((i.x0 - q.x0) * sx) + 1, int((i.x1 - q.x0) * sx) - 1
                region = a[max(y0, 0) : y1, max(x0, 0) : x1]
                if region.size and float(region.var()) > 0.0:
                    return True
    return False


def verify_pdf(
    pdf: bytes,
    redacted: dict[int, list[BBox]],
    scanned_pages: set[int],
    ocr_dpi: int = 250,
) -> Verification:
    """`scanned_pages`: pages that had no text layer originally (our labels add one)."""
    problems: list[Problem] = []
    t = {"text": 0.0, "fingerprint": 0.0, "pixels": 0.0}
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    for pno, page in enumerate(doc):
        rects = [pymupdf.Rect(r) for r in redacted.get(pno, [])]

        t0 = time.perf_counter()
        if pno in scanned_pages:
            pt = ocr.ocr_image(_render_gray(page, ocr_dpi), ocr_dpi)
        else:
            pt = ocr.get_page_text(page)
        for f in aadhaar.find_numbers(pt, pno):
            if f.redact and not _covered(f.bbox_pt, rects):
                problems.append(
                    Problem(page=pno, type=f.type, bbox_pt=f.bbox_pt, detail="number still visible")
                )
        for r in rects:
            words = page.get_text("words", clip=r)
            for w in words:
                if w[4] not in ALLOWED_LABEL_TEXT or re.search(r"\d", w[4]):
                    problems.append(
                        Problem(
                            page=pno,
                            type="TEXT",
                            bbox_pt=tuple(r),
                            detail="text left in redacted area",
                        )
                    )
                    break
        t1 = time.perf_counter()

        for f in fp_classical.detect_gray(_render_gray(page, 200), pno):
            if not _covered(f.bbox_pt, rects):
                problems.append(
                    Problem(
                        page=pno,
                        type="FINGERPRINT",
                        bbox_pt=f.bbox_pt,
                        detail="thumb impression still visible",
                    )
                )
        t2 = time.perf_counter()

        if rects and _image_pixels_left(doc, page, rects):
            problems.append(
                Problem(
                    page=pno,
                    type="IMAGE",
                    bbox_pt=tuple(rects[0]),
                    detail="image pixels left under redaction",
                )
            )
        t3 = time.perf_counter()
        t["text"] += (t1 - t0) * 1000
        t["fingerprint"] += (t2 - t1) * 1000
        t["pixels"] += (t3 - t2) * 1000
    doc.close()
    return Verification(status="fail" if problems else "pass", problems=problems, timings_ms=t)
