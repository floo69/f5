"""SurakshitID: capture → preprocess → detect → decide → destroy → watermark → verify → seal.

Everything happens in memory on this machine. The original capture is never written to
disk; only an ARMOR_AND_ISSUE result produces files (armored PNG/PDF + badge), and the
registry keeps hashes and purpose fields only.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw

from backend.app.core import badge as badge_mod
from backend.app.core import id_detect, watermark
from backend.app.core.decision import ArmorSummary, decide_armor, needs_care
from backend.app.core.preprocess import Prepared, UnreadableInput, prepare
from backend.app.core.presets import PRESETS, action_for, watermark_text
from backend.app.core.verify_raster import RasterVerification, verify_export

STEPS = [
    ("capture", "Read capture & strip metadata"),
    ("preprocess", "Crop, straighten, even out light"),
    ("detect", "Find Aadhaar, PAN, QR, thumbprints, faces"),
    ("decide", "System-One decision gate"),
    ("destroy", "Overwrite sensitive pixels with 0x00"),
    ("watermark", "Burn purpose watermark"),
    ("verify", "Re-scan the exported files"),
    ("seal", "Sign badge & append to ledger"),
]
CAREFUL_HIDE = {"AADHAAR", "VID", "MASKED_AADHAAR", "PAN", "QR", "BARCODE", "NUMBER", "DOB"}
MIN_SOURCE_PX = 800  # longest side of the document in the original capture
VERIFIED = {"AADHAAR", "VID", "MASKED_AADHAAR", "PAN", "QR"}
_B32 = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_armor_id() -> str:
    s = "".join(secrets.choice(_B32) for _ in range(8))
    return f"SKID-{s[:4]}-{s[4:]}"


@dataclass
class ArmorOutput:
    result: dict
    prepared: Prepared | None = None
    ocr_quality: float = 0.0
    findings: list[id_detect.IdFinding] = field(default_factory=list)
    final_rgb: np.ndarray | None = None
    png: bytes | None = None
    pdf: bytes | None = None


def _inside_any(b, boxes) -> bool:
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in boxes)


MAX_USER_BOXES = 20
MIN_USER_BOX_PX = 8


def clean_user_boxes(raw: list[dict] | None, shape: tuple[int, int]) -> list[dict]:
    """Validate hand-drawn boxes: clip to the image, drop slivers, cap the count. Labels are
    short plain text kept only in the findings list (never in the watermark)."""
    h, w = shape
    out = []
    for b in (raw or [])[:MAX_USER_BOXES]:
        try:
            x0, y0, x1, y1 = (int(round(float(v))) for v in b["bbox_px"])
        except (KeyError, TypeError, ValueError):
            continue
        x0, x1 = sorted((max(0, min(w, x0)), max(0, min(w, x1))))
        y0, y1 = sorted((max(0, min(h, y0)), max(0, min(h, y1))))
        if x1 - x0 < MIN_USER_BOX_PX or y1 - y0 < MIN_USER_BOX_PX:
            continue
        label = "".join(c for c in str(b.get("label") or "") if c.isalnum() or c in " -/")[:24]
        out.append({"bbox_px": [x0, y0, x1, y1], "label": label.strip() or None})
    return out


def _mostly_inside(b, boxes, frac: float = 0.5) -> bool:
    bx0, by0, bx1, by1 = b
    area = max(1, (bx1 - bx0) * (by1 - by0))
    for x0, y0, x1, y1 in boxes:
        iw, ih = min(bx1, x1) - max(bx0, x0), min(by1, y1) - max(by0, y0)
        if iw > 0 and ih > 0 and iw * ih / area >= frac:
            return True
    return False


def _pad(dpi: int) -> int:
    return max(3, round(dpi / 50))


def mask_rects(f: id_detect.IdFinding, action: str, dpi: int, shape: tuple[int, int]
               ) -> list[list[int]]:
    """Rectangles to zero for one finding. MASK_PARTIAL (Aadhaar) hides the first 8 digits and
    keeps the last 4; without per-digit geometry it falls back to the whole number."""
    h, w = shape
    p = _pad(dpi)

    def clip(x0, y0, x1, y1) -> list[int]:
        return [max(0, int(x0)), max(0, int(y0)),
                min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1)))]

    if action == "KEEP":
        return []
    x0, y0, x1, y1 = f.bbox_px
    if f.type in ("QR", "BARCODE"):
        q = max(p, int(0.04 * max(x1 - x0, y1 - y0)))
        return [clip(x0 - q, y0 - q, x1 + q, y1 + q)]
    if action == "MASK_PARTIAL" and len(f.digits_px) >= 12:
        d = f.digits_px
        # group the first 8 digits into text lines (a number may wrap onto two lines)
        groups: list[list] = [[d[0]]]
        for b in d[1:8]:
            prev = groups[-1][-1]
            same_line = abs((b[1] + b[3]) - (prev[1] + prev[3])) / 2 < (prev[3] - prev[1]) / 2
            if same_line:
                groups[-1].append(b)
            else:
                groups.append([b])
        out = []
        for g in groups:
            gx1 = max(b[2] for b in g) + p
            if g[-1] is d[7] and d[8][0] > d[7][2] and abs(d[8][1] - d[7][1]) < (d[7][3] - d[7][1]):
                gx1 = (d[7][2] + d[8][0]) / 2  # stop halfway into the gap before digit 9
            out.append(clip(min(b[0] for b in g) - p, min(b[1] for b in g) - p, gx1,
                            max(b[3] for b in g) + p))
        return out
    return [clip(x0 - p, y0 - p, x1 + p, y1 + p)]


def _strip(width: int, lines: list[str], qr: np.ndarray) -> tuple[np.ndarray, tuple[int, ...]]:
    """White badge strip with purpose text and the badge QR at the right."""
    qh = qr.shape[0]
    size = max(13, int(width / 50))
    step = int((size + 4) * 1.35)
    h = max(qh + 24, 16 + step * len(lines) + size // 2)
    img = Image.new("RGB", (width, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width - 1, 5], fill=(15, 118, 110))
    y = 16
    for i, ln in enumerate(lines):
        font = watermark._font(size + (4 if i == 0 else 0))
        while d.textlength(ln, font=font) > width - qh - 40 and len(ln) > 10:
            ln = ln[:-2]
        d.text((16, y), ln, font=font, fill=(17, 24, 39) if i == 0 else (55, 65, 81))
        y += step
    arr = np.asarray(img).copy()
    qx = width - qh - 12
    arr[12 : 12 + qh, qx : qx + qh] = qr
    return arr, (qx, 12, qx + qh, 12 + qh)


def _encode(rgb: np.ndarray, dpi: int) -> tuple[bytes, bytes]:
    ok, png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise RuntimeError("PNG encode failed")
    png = png.tobytes()
    h, w = rgb.shape[:2]
    doc = pymupdf.open()
    page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
    page.insert_image(page.rect, stream=png)
    doc.set_metadata({})
    doc.del_xml_metadata()
    pdf = doc.tobytes(garbage=4, deflate=True, clean=True, no_new_id=True)
    doc.close()
    return png, pdf


def armor(
    data: bytes,
    preset_key: str,
    recipient: str,
    valid_days: int,
    sealer: badge_mod.Sealer,
    step: Callable[[str, str, float | None], None] | None = None,
    now: datetime | None = None,
    extra_boxes: list[dict] | None = None,
    reuse: ArmorOutput | None = None,
) -> ArmorOutput:
    """Run the full pipeline. `step(key, status, ms)` reports progress.

    `extra_boxes` are user-drawn rectangles (normalised pixel coords) that are zeroed in
    addition to the detected ones: the user can only ever hide MORE. `reuse` re-runs the
    destroy/watermark/verify/seal stages on an earlier output's normalised image and findings
    (the original upload is never kept), so detection is identical to the first pass."""
    report = step or (lambda *_: None)
    timings: dict[str, float] = {}
    t = time.perf_counter()

    def done(key: str) -> None:
        nonlocal t
        ms = round((time.perf_counter() - t) * 1000, 1)
        timings[key] = ms
        report(key, "done", ms)
        t = time.perf_counter()

    preset = PRESETS.get(preset_key)
    recipient = " ".join(recipient.split())[:60]
    now = (now or datetime.now(UTC).astimezone()).replace(microsecond=0)
    expires = now + timedelta(days=max(valid_days, 0))
    armor_id = new_armor_id()
    base = {
        "armor_id": armor_id, "preset": preset.public() if preset else None,
        "recipient": recipient, "issued_at": now.isoformat(), "expires_at": expires.isoformat(),
        "watermark_text": "", "preprocess": None, "ocr_quality": 0.0, "findings": [],
        "masks_px": [], "careful": False,
        "verification": {"status": "skipped", "checks": []}, "badge": None,
        "timings_ms": timings,
    }

    report("capture", "running", None)
    report("preprocess", "running", None)
    try:
        prep = reuse.prepared if reuse is not None else prepare(data)
    except UnreadableInput as e:
        g = decide_armor(ArmorSummary(preset_key, recipient, valid_days, False, 0.0, 0.0, ()))
        return ArmorOutput({**base, "decision": g.decision,
                            "reasons": [*g.reasons, str(e)], "decision_us": g.elapsed_us})
    done("capture")
    done("preprocess")
    base["preprocess"] = prep.facts()

    report("detect", "running", None)
    if reuse is not None:
        findings, ocr_q = reuse.findings, reuse.ocr_quality
    else:
        sc = id_detect.scan(prep.rgb, prep.dpi, prep.doc_kind)
        findings = [f for f in sc.findings if f.type != "BADGE"]
        ocr_q = sc.ocr_quality
    base["ocr_quality"] = round(ocr_q, 3)
    done("detect")

    report("decide", "running", None)
    h, w = prep.rgb.shape[:2]
    verified = sum(f.type in VERIFIED and not f.source.endswith("-suspect") for f in findings)
    doc_found = prep.quad_found or prep.doc_kind != "unknown"
    careful = needs_care(ArmorSummary(preset_key, recipient, valid_days, doc_found,
                                      prep.blur_score, ocr_q, (), 0,
                                      verified_tokens=verified))
    portraits = [f.bbox_px for f in findings if f.type == "FACE"]
    shown, masks = [], []
    unmaskable = 0
    for f in findings:
        act = action_for(preset, f.type) if preset else (
            "MASK" if f.type in ("FINGERPRINT", "VID") else "KEEP")
        if careful and f.type in CAREFUL_HIDE:
            act = "MASK"  # unsure what we read: hide the whole thing
        if f.type in ("NUMBER", "DOB") and _inside_any(f.bbox_px, portraits):
            act = "KEEP"  # OCR noise inside the ID photo, not printed text
        rects = mask_rects(f, act, prep.dpi, (h, w))
        if act != "KEEP" and not rects:
            unmaskable += 1
        masks.extend(rects)
        shown.append({"type": f.type, "bbox_px": list(f.bbox_px), "action": act,
                      "masked_px": rects, "value_masked": f.value_masked,
                      "confidence": round(f.confidence, 3), "source": f.source})
    user_boxes = clean_user_boxes(extra_boxes, (h, w))
    for ub in user_boxes:
        masks.append(ub["bbox_px"])
        shown.append({"type": "USER", "bbox_px": ub["bbox_px"], "action": "MASK",
                      "masked_px": [ub["bbox_px"]], "value_masked": None, "confidence": 1.0,
                      "source": "user", "label": ub["label"]})
    base["findings"], base["masks_px"], base["careful"] = shown, masks, careful
    summary = ArmorSummary(preset_key, recipient, valid_days, doc_found, prep.blur_score,
                           ocr_q, tuple(f.type for f in findings), unmaskable,
                           verified_tokens=verified)
    gate = decide_armor(summary)
    done("decide")
    out = ArmorOutput(base, prepared=prep, ocr_quality=ocr_q, findings=findings)
    if gate.decision != "ARMOR_AND_ISSUE":
        reasons = list(gate.reasons)
        if gate.decision == "BLOCK_FOR_REVIEW" and max(prep.source_px) < MIN_SOURCE_PX:
            sw, sh = prep.source_px
            reasons.append(f"Photo resolution is very low ({sw}×{sh} px). Upload the original "
                           "camera photo, not a screenshot or thumbnail.")
        base.update(decision=gate.decision, reasons=reasons,
                    decision_us=round(gate.elapsed_us, 2))
        return out

    report("destroy", "running", None)
    destroyed = prep.rgb.copy()
    for x0, y0, x1, y1 in masks:
        destroyed[y0:y1, x0:x1] = 0
    done("destroy")

    report("watermark", "running", None)
    text = watermark_text(preset, recipient, now, expires, armor_id)
    base["watermark_text"] = text
    marked = watermark.burn(destroyed, text, armor_id)
    for x0, y0, x1, y1 in masks:  # masks are zeroed LAST: watermark ink never lands in them
        marked[y0:y1, x0:x1] = 0
    module = max(4, w // 220)
    placeholder = badge_mod.render_qr(badge_mod.qr_payload(armor_id, "0" * 64), module)
    lines = [f"SurakshitID · SEALED COPY · {armor_id}",
             f"FOR {recipient.upper()} — {preset.label.upper()} ONLY",
             f"VALID {now:%d %b %Y} – {expires:%d %b %Y}"
             f" · NOT FOR {', '.join(preset.not_valid_for)}",
             "Any edit breaks the seal · verify on the SurakshitID portal"]
    strip, qr_rect = _strip(w, lines, placeholder)
    qr_rect = (qr_rect[0], qr_rect[1] + h, qr_rect[2], qr_rect[3] + h)
    final = np.vstack([marked, strip])
    tiles = badge_mod.tile_hashes(final, badge_mod.TILE_PX, qr_rect)
    root = badge_mod.merkle_root(tiles)
    payload = badge_mod.qr_payload(armor_id, root)
    qr = badge_mod.render_qr(payload, module)
    if qr.shape != placeholder.shape:  # payload length is fixed, so this never happens
        raise RuntimeError("badge QR size changed")
    final[qr_rect[1] : qr_rect[3], qr_rect[0] : qr_rect[2]] = qr
    done("watermark")

    report("verify", "running", None)
    png, pdf = _encode(final, prep.dpi)
    # a photo the user chose to hide carries no watermark by design
    user_rects = [ub["bbox_px"] for ub in user_boxes]
    faces = [f.bbox_px for f in findings if f.type == "FACE"
             and not _mostly_inside(f.bbox_px, user_rects)]
    ver: RasterVerification = verify_export(
        final_rgb=final, png=png, pdf=pdf, destroyed_doc=destroyed, watermarked_doc=marked,
        masks=masks, preset=preset, dpi=prep.dpi, faces=faces, qr_payload=payload,
        hidden=[tuple(f["bbox_px"]) for f in shown
                if f["action"] == "MASK" and f["type"] != "USER"],
        input_quality=ocr_q, careful=careful, prints=prep.doc_kind != "id_card")
    base["verification"] = ver.model_dump()
    done("verify")

    gate = decide_armor(ArmorSummary(**{**summary_dict(summary), "verification": ver.status}))
    base.update(decision=gate.decision, reasons=list(gate.reasons),
                decision_us=round(gate.elapsed_us, 2))
    if gate.decision != "ARMOR_AND_ISSUE":
        return out

    report("seal", "running", None)
    fh, fw = final.shape[:2]
    core = {"v": 1, "armor_id": armor_id, "preset": preset.key, "recipient": recipient,
            "purpose": f"{preset.purpose} ONLY", "issued_at": now.isoformat(),
            "expires_at": expires.isoformat(), "width": fw, "height": fh,
            "tile_px": badge_mod.TILE_PX, "qr_rect": list(qr_rect),
            "sha256": badge_mod.pixel_sha256(final, qr_rect), "tiles_root": root}
    base["badge"] = sealer.seal(core, tiles, {"masks_px": masks})
    done("seal")
    out.final_rgb, out.png, out.pdf = final, png, pdf
    return out


def summary_dict(s: ArmorSummary) -> dict:
    return {k: getattr(s, k) for k in s.__slots__}
