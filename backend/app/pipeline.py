"""detect → decide → truly redact → verify (fail closed).

Pages are rendered in the calling thread (PyMuPDF documents aren't thread-safe); the heavy
per-page work (thumbprint detector, OCR) runs on numpy arrays in a small thread pool.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pymupdf
from pydantic import BaseModel

from backend.app.core import aadhaar, fp_classical, ocr
from backend.app.core.decision import LABELS, decide_page
from backend.app.core.redact import redact_pdf
from backend.app.core.types import Finding, PageText
from backend.app.core.verify import Verification, verify_pdf

FP_DPI = 200
OCR_DPI = 250
DETECTOR_VERSIONS = {"aadhaar": "1.0", "fp_classical": "1.0", "pipeline": "1.0"}

class PageResult(BaseModel):
    page: int
    size_pt: tuple[float, float]
    text_layer: bool
    ocr_quality: float
    decision: str
    reasons: list[str]
    findings: list[Finding]
    counts: dict[str, int]
    timings_ms: dict[str, float]


class Result(BaseModel):
    doc_id: str
    sha256_in: str
    sha256_out: str
    page_count: int
    status: str  # VERIFIED_CLEAN | BLOCKED_FOR_REVIEW
    pages: list[PageResult]
    verification: Verification
    timings_ms: dict[str, float]
    detector_versions: dict[str, str]


def _gray(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()


def process_pdf(
    pdf: bytes,
    doc_id: str,
    progress: Callable[[int, int], None] | None = None,
    workers: int = 3,
) -> tuple[Result, bytes]:
    """Returns (result, redacted PDF bytes). The input is never written to disk."""
    t_start = time.perf_counter()
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    n = doc.page_count
    progress and progress(0, n)

    pages: list[dict] = []
    futures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for pno, page in enumerate(doc):
            t0 = time.perf_counter()
            pt = ocr.get_page_text(page) if _has_text_layer(page) else None
            gray_fp = _gray(page, FP_DPI)
            gray_ocr = _gray(page, OCR_DPI) if pt is None else None
            t1 = time.perf_counter()
            pages.append(
                {
                    "page": pno,
                    "size_pt": (page.rect.width, page.rect.height),
                    "pt": pt,
                    "timings_ms": {"render": (t1 - t0) * 1000},
                }
            )
            futures.append(pool.submit(_detect, pno, gray_fp, gray_ocr, pt))
        doc.close()

        all_findings: list[Finding] = []
        page_results: list[PageResult] = []
        for i, fut in enumerate(futures):
            pt, findings, tms = fut.result()
            p = pages[i]
            decision, reasons = decide_page(findings, pt.text_layer, pt.ocr_quality)
            all_findings.extend(findings)
            page_results.append(
                PageResult(
                    page=p["page"],
                    size_pt=p["size_pt"],
                    text_layer=pt.text_layer,
                    ocr_quality=round(pt.ocr_quality, 3),
                    decision=decision,
                    reasons=reasons,
                    findings=findings,
                    counts={t: sum(f.type == t for f in findings) for t in LABELS},
                    timings_ms={k: round(v, 1) for k, v in {**p["timings_ms"], **tms}.items()},
                )
            )
            progress and progress(i + 1, n)
    t_detect = time.perf_counter()

    redacted, rects = redact_pdf(pdf, all_findings)
    t_redact = time.perf_counter()

    scanned = {p.page for p in page_results if not p.text_layer}
    verification = verify_pdf(redacted, rects, scanned, ocr_dpi=OCR_DPI)
    t_verify = time.perf_counter()

    # Fail closed: any page with a verification problem is blocked.
    bad_pages = {pr.page for pr in verification.problems}
    for pr in page_results:
        if pr.page in bad_pages:
            pr.decision = "BLOCK_FOR_REVIEW"
            pr.reasons.insert(0, "verification found something after redaction")
    blocked = verification.status != "pass" or any(
        p.decision == "BLOCK_FOR_REVIEW" for p in page_results
    )

    result = Result(
        doc_id=doc_id,
        sha256_in=hashlib.sha256(pdf).hexdigest(),
        sha256_out=hashlib.sha256(redacted).hexdigest(),
        page_count=n,
        status="BLOCKED_FOR_REVIEW" if blocked else "VERIFIED_CLEAN",
        pages=page_results,
        verification=verification,
        timings_ms={
            "detect": round((t_detect - t_start) * 1000, 1),
            "redact": round((t_redact - t_detect) * 1000, 1),
            "verify": round((t_verify - t_redact) * 1000, 1),
            "total": round((t_verify - t_start) * 1000, 1),
        },
        detector_versions=DETECTOR_VERSIONS,
    )
    return result, redacted


def _has_text_layer(page: pymupdf.Page) -> bool:
    words = page.get_text("words")
    return sum(any(c.isalnum() for c in w[4]) for w in words) >= 5


def _detect(
    pno: int, gray_fp: np.ndarray, gray_ocr: np.ndarray | None, pt: PageText | None
) -> tuple[PageText, list[Finding], dict[str, float]]:
    t0 = time.perf_counter()
    if pt is None:
        pt = ocr.ocr_image(gray_ocr, OCR_DPI)
    t1 = time.perf_counter()
    numbers = aadhaar.find_numbers(pt, pno)
    t2 = time.perf_counter()
    prints = fp_classical.detect_gray(gray_fp, pno, dpi=FP_DPI)
    t3 = time.perf_counter()
    return (
        pt,
        [*prints, *numbers],
        {
            "text": (t1 - t0) * 1000,
            "aadhaar": (t2 - t1) * 1000,
            "fingerprint": (t3 - t2) * 1000,
        },
    )
