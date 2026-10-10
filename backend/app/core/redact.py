"""True redaction: destroy the underlying text and image pixels, not just cover them.

PyMuPDF's apply_redactions removes text under the rect, blanks image pixels inside it
(PDF_REDACT_IMAGE_PIXELS; an image fully covered is dropped entirely) and removes covered
vector art. The document is then scrubbed of metadata, annotations, attachments and
JavaScript before saving.
"""

from __future__ import annotations

from collections import defaultdict

import pymupdf

from backend.app.core.types import REDACT_TYPES, REDACTION_LABELS, BBox, Finding

PAD_PT = {"FINGERPRINT": 8.0, "AADHAAR": 2.0, "VID": 2.0}
LABEL_FONTSIZE = {"FINGERPRINT": 6.0, "AADHAAR": 4.5, "VID": 4.5}


def padded_rect(f: Finding, page_rect: pymupdf.Rect) -> pymupdf.Rect:
    pad = PAD_PT.get(f.type, 2.0)
    return (pymupdf.Rect(f.bbox_pt) + (-pad, -pad, pad, pad)) & page_rect


def redact_pdf(pdf: bytes, findings: list[Finding]) -> tuple[bytes, dict[int, list[BBox]]]:
    """Return (redacted PDF bytes, {page: [redacted rects in points]})."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    by_page: dict[int, list[Finding]] = defaultdict(list)
    for f in findings:
        if f.redact and f.type in REDACT_TYPES:
            by_page[f.page].append(f)

    rects: dict[int, list[BBox]] = {}
    for pno, fs in by_page.items():
        page = doc[pno]
        page_rects = []
        for f in fs:
            r = padded_rect(f, page.rect)
            if r.is_empty:
                continue
            page.add_redact_annot(
                r,
                text=REDACTION_LABELS[f.type],
                fontname="helv",
                fontsize=LABEL_FONTSIZE[f.type],
                align=pymupdf.TEXT_ALIGN_CENTER,
                fill=(0, 0, 0),
                text_color=(1, 1, 1),
                cross_out=False,
            )
            page_rects.append(tuple(r))
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        rects[pno] = page_rects

    for page in doc:
        for annot in list(page.annots() or []):
            page.delete_annot(annot)
    doc.scrub(redactions=False)
    doc.set_metadata({})
    doc.del_xml_metadata()
    out = doc.tobytes(garbage=4, deflate=True, clean=True)
    doc.close()
    return out, rects
