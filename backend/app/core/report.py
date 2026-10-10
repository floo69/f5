"""Redaction certificate: JSON + one-page PDF summary.

Contains counts, page decisions, hashes, detector versions and timestamps only — no full
numbers, no masked values, no images.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pymupdf


def certificate_dict(result, filename: str) -> dict:
    totals: dict[str, int] = {}
    for p in result.pages:
        for t, n in p.counts.items():
            totals[t] = totals.get(t, 0) + n
    return {
        "certificate": "ThumbShield redaction certificate",
        "issued_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "document": filename,
        "doc_id": result.doc_id,
        "sha256_in": result.sha256_in,
        "sha256_out": result.sha256_out,
        "status": result.status,
        "verification": result.verification.status,
        "verification_problems": len(result.verification.problems),
        "totals": totals,
        "pages": [
            {
                "page": p.page + 1,
                "decision": p.decision,
                "counts": p.counts,
                "text_layer": p.text_layer,
                "ocr_quality": p.ocr_quality,
            }
            for p in result.pages
        ],
        "detector_versions": result.detector_versions,
        "processing_ms": result.timings_ms,
        "processed_locally": True,
    }


def certificate_pdf(cert: dict) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    ok = cert["status"] == "VERIFIED_CLEAN"
    y = 60

    def line(
        text: str, size: float = 10, color=(0.1, 0.1, 0.15), bold: bool = False, dy: float = 16
    ):
        nonlocal y
        page.insert_text(
            (50, y), text, fontsize=size, fontname="hebo" if bold else "helv", color=color
        )
        y += dy

    line("ThumbShield — Redaction certificate", 18, bold=True, dy=26)
    line("Processed locally. No document left this machine.", 10, (0.35, 0.35, 0.4), dy=24)
    line(
        "VERIFIED CLEAN" if ok else "BLOCKED FOR REVIEW",
        16,
        (0.05, 0.5, 0.3) if ok else (0.75, 0.1, 0.1),
        bold=True,
        dy=28,
    )
    line(f"Document: {cert['document']}")
    line(f"Issued: {cert['issued_at']}")
    line(f"SHA-256 in:  {cert['sha256_in']}", 8)
    line(f"SHA-256 out: {cert['sha256_out']}", 8, dy=24)
    t = cert["totals"]
    line("Redacted", 12, bold=True, dy=18)
    line(
        f"Thumb impressions: {t.get('FINGERPRINT', 0)}    Aadhaar numbers: {t.get('AADHAAR', 0)}"
        f"    VIDs: {t.get('VID', 0)}    Masked (left as is): {t.get('MASKED_AADHAAR', 0)}",
        dy=24,
    )
    line("Pages", 12, bold=True, dy=18)
    for p in cert["pages"][:30]:
        c = p["counts"]
        source = "text layer" if p["text_layer"] else f"scanned, OCR q={p['ocr_quality']:.2f}"
        line(
            f"Page {p['page']:>3}: {p['decision']:<20} thumbs {c.get('FINGERPRINT', 0)}  "
            f"aadhaar {c.get('AADHAAR', 0) + c.get('VID', 0)}  {source}",
            9,
            dy=13,
        )
    y += 12
    line(f"Verification: {cert['verification']} ({cert['verification_problems']} problems)", 10)
    versions = ", ".join(f"{k} {v}" for k, v in cert["detector_versions"].items())
    line(f"Detectors: {versions}", 9)
    line(f"Total processing: {cert['processing_ms'].get('total', 0):.0f} ms", 9)
    out = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return out
