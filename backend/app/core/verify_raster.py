"""Fail-closed verification of an armored export (docs/ARMOR_CONTRACT.md, invariants 1-5).

Re-reads the exported bytes — not the in-memory arrays — and checks:
- PNG and PDF decode to exactly the sealed pixels; every mask is 0x00 in both;
- PNG carries only IHDR/IDAT/IEND; PDF has one image, no text, metadata, annotations, files;
- a fresh scan of the masked document finds nothing the preset says must be hidden;
- the purpose watermark is present across the page and across every detected face;
- the badge QR decodes to the expected payload.
Any failed check fails the export.
"""

from __future__ import annotations

import struct

import cv2
import numpy as np
import pymupdf
from pydantic import BaseModel

from . import id_detect, ocr
from .badge import find_badge_qr
from .decision import MIN_OCR_QUALITY_ID
from .presets import Preset, action_for

COVERED_FRACTION = 0.5
MIN_WATERMARK_COVERAGE = 0.04  # fraction of non-mask doc pixels changed by the watermark
MIN_FACE_COVERAGE = 0.02


class Check(BaseModel):
    name: str
    ok: bool
    detail: str


class RasterVerification(BaseModel):
    status: str  # pass | fail
    checks: list[Check]


def png_chunks(png: bytes) -> list[str]:
    out, i = [], 8
    while i + 8 <= len(png):
        n, typ = struct.unpack(">I4s", png[i : i + 8])
        out.append(typ.decode("latin-1"))
        i += 12 + n
    return out


def _masks_zero(img: np.ndarray, masks: list[list[int]]) -> int:
    """Number of non-zero bytes inside masks."""
    return int(sum(np.count_nonzero(img[y0:y1, x0:x1]) for x0, y0, x1, y1 in masks))


def _covered(b, masks: list[list[int]]) -> bool:
    x0, y0, x1, y1 = b
    area = max(1, (x1 - x0) * (y1 - y0))
    inside = 0
    for m in masks:
        ix = max(0, min(x1, m[2]) - max(x0, m[0]))
        iy = max(0, min(y1, m[3]) - max(y0, m[1]))
        inside += ix * iy
    return inside >= COVERED_FRACTION * area


def pdf_facts(pdf: bytes) -> dict:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    meta = {k: v for k, v in (doc.metadata or {}).items()
            if v and k not in ("format", "encryption")}
    facts = {
        "pages": doc.page_count,
        "text_chars": len(text.strip()),
        "text_sample": text.strip()[:40],
        "metadata": meta,
        "xmp": bool(doc.xref_xml_metadata()),
        "images": sum(len(p.get_images(full=True)) for p in doc),
        "annotations": sum(len(list(p.annots() or [])) for p in doc),
        "embedded_files": doc.embfile_count(),
        "javascript": any(doc.xref_get_key(doc.pdf_catalog(), k)[0] != "null"
                          for k in ("Names", "OpenAction", "AA")),
    }
    doc.close()
    return facts


def pdf_pixels(pdf: bytes) -> np.ndarray | None:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    imgs = doc[0].get_images(full=True)
    if len(imgs) != 1:
        return None
    pm = pymupdf.Pixmap(doc, imgs[0][0])
    if pm.n != 3 or pm.alpha:
        pm = pymupdf.Pixmap(pymupdf.csRGB, pm, 0)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n).copy()
    doc.close()
    return a


def verify_export(
    *,
    final_rgb: np.ndarray,
    png: bytes,
    pdf: bytes,
    destroyed_doc: np.ndarray,
    watermarked_doc: np.ndarray,
    masks: list[list[int]],
    preset: Preset,
    dpi: int,
    faces: list[tuple[int, int, int, int]],
    qr_payload: str,
    hidden: list[tuple[int, int, int, int]] = (),
    input_quality: float = 1.0,
    careful: bool = False,
    prints: bool = True,
) -> RasterVerification:
    """`hidden`: original boxes of fully masked findings. Any readable word whose centre lies
    in one of them (grown by half a line) but outside the masks means a mask cut a line."""
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(Check(name=name, ok=bool(ok), detail=detail))

    dec = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    png_rgb = None if dec is None or dec.ndim != 3 else cv2.cvtColor(dec, cv2.COLOR_BGR2RGB)
    same = png_rgb is not None and png_rgb.shape == final_rgb.shape and np.array_equal(
        png_rgb, final_rgb)
    add("png_matches_sealed_pixels", same, "PNG decodes to exactly the sealed pixels"
        if same else "PNG pixels differ from the sealed image")
    nz = _masks_zero(png_rgb, masks) if png_rgb is not None else -1
    add("masks_zero_png", nz == 0, f"{len(masks)} masks, {nz} non-zero bytes inside")

    chunks = png_chunks(png)
    add("png_no_metadata", set(chunks) <= {"IHDR", "IDAT", "IEND"},
        "chunks: " + ", ".join(dict.fromkeys(chunks)))

    pdf_rgb = pdf_pixels(pdf)
    same_pdf = pdf_rgb is not None and np.array_equal(pdf_rgb, final_rgb)
    nz_pdf = _masks_zero(pdf_rgb, masks) if pdf_rgb is not None else -1
    add("pdf_matches_and_masks_zero", same_pdf and nz_pdf == 0,
        f"single lossless image, {nz_pdf} non-zero bytes inside masks" if same_pdf
        else "PDF image differs from the sealed pixels")
    f = pdf_facts(pdf)
    flat = (f["pages"] == 1 and f["text_chars"] == 0 and not f["metadata"] and not f["xmp"]
            and f["images"] == 1 and f["annotations"] == 0 and f["embedded_files"] == 0
            and not f["javascript"])
    add("pdf_flat", flat, f"{f['text_chars']} text chars, {len(f['metadata'])} metadata fields, "
        f"{f['images']} image(s), {f['annotations']} annotations")

    # Fresh scan of the masked document (the watermark only adds ink on top of these pixels).
    # Masks are painted white for OCR only: their 0x00 content is proven above, and OCR on
    # black boxes just produces low-confidence noise.
    gray = cv2.cvtColor(destroyed_doc, cv2.COLOR_RGB2GRAY)
    for x0, y0, x1, y1 in masks:
        gray[y0:y1, x0:x1] = 255
    pt = ocr.ocr_image(gray, dpi, lang="eng")
    found = [*id_detect.text_findings(pt, dpi),
             *id_detect.codes(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)),
             *(id_detect.fingerprints(gray, dpi, faces) if prints else [])]
    leaks = []
    for x in found:
        if x.type in ("AADHAAR", "VID"):  # a full number is never allowed to survive
            hide = True
        else:
            hide = action_for(preset, x.type) != "KEEP"
        if hide and not _covered(x.bbox_px, masks):
            leaks.append(f"{x.type} at {list(x.bbox_px)}")
    for w in pt.words:
        if not any(c.isalnum() for c in w.text) or w.conf < 0.5:
            continue
        b = tuple(v * dpi / 72.0 for v in w.bbox_pt)
        cx, cy, hh = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, (b[3] - b[1]) / 2
        in_hidden = any(r[0] <= cx <= r[2] and r[1] - hh <= cy <= r[3] + hh for r in hidden)
        if in_hidden and not _covered(b, masks):
            leaks.append(f"text next to a mask at {[int(v) for v in b]}")
    add("rescan_no_leaks", not leaks, "nothing to hide is readable" if not leaks
        else "still visible: " + "; ".join(leaks[:5]))
    # the re-scan must be about as legible as the input the gate accepted, else absence of
    # leaks is unproven
    q = id_detect.latin_quality(pt)
    need = min(MIN_OCR_QUALITY_ID, input_quality - 0.15)
    # careful mode already hides every number and QR-like block, so a low re-scan score
    # can't hide a leak of those
    readable = careful or q >= need or len(pt.words) < 3
    add("rescan_quality", readable, f"OCR quality of the re-scan {q:.2f} (needs {need:.2f})")

    changed = np.any(watermarked_doc != destroyed_doc, axis=2)
    keep = np.ones(changed.shape, bool)
    for x0, y0, x1, y1 in masks:
        keep[y0:y1, x0:x1] = False
    cov = float(changed[keep].mean()) if keep.any() else 0.0
    face_cov = [float(changed[y0:y1, x0:x1].mean()) for x0, y0, x1, y1 in faces]
    ok_wm = cov >= MIN_WATERMARK_COVERAGE and all(c >= MIN_FACE_COVERAGE for c in face_cov)
    add("watermark_burned", ok_wm, f"{cov:.0%} of visible pixels carry the purpose watermark"
        + (f"; faces {', '.join(f'{c:.0%}' for c in face_cov)}" if face_cov else ""))

    got = find_badge_qr(final_rgb)
    add("badge_qr", got is not None and got[0] == qr_payload,
        "badge QR decodes to this issue" if got else "badge QR not readable")

    return RasterVerification(status="pass" if all(c.ok for c in checks) else "fail",
                              checks=checks)
