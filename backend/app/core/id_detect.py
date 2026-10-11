"""On-device detectors for identity documents. Deterministic; nothing leaves the process.

Aadhaar/VID (strict groups + Verhoeff, reused from aadhaar.py), PAN (format + OCR-confusion
repair), DOB, other numbers, address block, QR/1-D barcodes (OpenCV), faces (classical skin/
portrait-region heuristic) and thumb impressions (fp_classical). Only bboxes and masked
values come out: QR payloads are never returned or logged (an Aadhaar QR holds the whole
record), full numbers never leave `_digits`-local variables.
"""

from __future__ import annotations

import re

import cv2
import numpy as np
from pydantic import BaseModel

from . import aadhaar, fp_classical, ocr
from .badge import QR_PREFIX
from .types import PageText

PxBox = tuple[int, int, int, int]


class IdFinding(BaseModel):
    type: str  # AADHAAR VID MASKED_AADHAAR PAN QR BARCODE FACE FINGERPRINT DOB NUMBER ADDRESS
    bbox_px: PxBox
    digits_px: list[PxBox] = []  # AADHAAR/VID only: one box per digit, reading order
    confidence: float
    source: str
    value_masked: str | None = None


class Scan(BaseModel):
    findings: list[IdFinding]
    ocr_quality: float
    words: int


_PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHLJPT][A-Z][0-9]{4}[A-Z]$")
_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}
_TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "|": "1", "Z": "2", "S": "5",
             "B": "8", "G": "6"}
_DOB_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$")
_PIN_RE = re.compile(r"^\d{6}$")
_ADDR_KW = ("address", "addr", "पता", "വിലാസം")


def _px(b, s: float) -> PxBox:
    return (int(np.floor(b[0] * s)), int(np.floor(b[1] * s)), int(np.ceil(b[2] * s)),
            int(np.ceil(b[3] * s)))


def pan_candidate(token: str) -> str | None:
    """Repair OCR confusions by position (letters 1-5, digits 6-9, letter 10)."""
    t = re.sub(r"[^A-Za-z0-9|]", "", token).upper()
    if len(t) != 10:
        return None
    fixed = "".join(
        (_TO_LETTER.get(c, c) if i < 5 or i == 9 else _TO_DIGIT.get(c, c)) for i, c in enumerate(t)
    )
    return fixed if _PAN_RE.match(fixed) else None


def _lines(pt: PageText) -> list[list]:
    by: dict[int, list] = {}
    for w in pt.words:
        by.setdefault(w.line_id, []).append(w)
    out = [sorted(ws, key=lambda w: w.bbox_pt[0]) for ws in by.values()]
    return sorted(out, key=lambda ws: sum(w.bbox_pt[1] for w in ws) / len(ws))


def text_findings(pt: PageText, dpi: int) -> list[IdFinding]:
    s = dpi / 72.0
    src = "ocr" if not pt.text_layer else "textlayer"
    out: list[IdFinding] = []
    covered: list[PxBox] = []
    for f in aadhaar.find_numbers(pt, 0):
        b = _px(f.bbox_pt, s)
        covered.append(b)
        out.append(IdFinding(type=f.type, bbox_px=b, digits_px=[_px(p, s) for p in f.parts_pt],
                             confidence=f.confidence, source=src, value_masked=f.value_masked))

    def inside(b: PxBox) -> bool:
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return any(c[0] <= cx <= c[2] and c[1] <= cy <= c[3] for c in covered)

    lines = _lines(pt)
    for f in _suspect_numbers(lines, s, src):
        if not inside(f.bbox_px):
            out.append(f)
            covered.append(f.bbox_px)
    for ws in lines:
        for w in ws:
            b = _px(w.bbox_pt, s)
            if inside(b):
                continue
            pan = pan_candidate(w.text)
            if pan:
                out.append(IdFinding(type="PAN", bbox_px=b, confidence=0.95, source=src,
                                     value_masked="XXXXX" + pan[5:9] + "X"))
                covered.append(b)
                continue
            t = ocr.normalize_token(w.text)
            if _DOB_RE.match(t) or (t.isdigit() and len(t) == 4 and 1900 <= int(t) <= 2030
                                    and any("birth" in x.text.lower() or "yob" in x.text.lower()
                                            for x in ws)):
                out.append(IdFinding(type="DOB", bbox_px=b, confidence=0.9, source=src,
                                     value_masked="XX/XX/XXXX"))
                covered.append(b)
            elif any(c.isdigit() for c in w.text.translate(ocr._ML_DIGITS)):
                out.append(IdFinding(type="NUMBER", bbox_px=b, confidence=0.8, source=src))
    out.extend(_address(lines, s, src))
    return out


def _suspect_numbers(lines: list[list], s: float, src: str) -> list[IdFinding]:
    """Fail closed on OCR misreads: a 4-4-4 (or 4-4-4-4) digit-group run that fails Verhoeff is
    still treated as an Aadhaar (VID) number, since one misread digit must not unmask it."""
    out = []
    for ws in lines:
        run: list = []
        for w in [*ws, None]:
            t = ocr.normalize_token(w.text) if w is not None else ""
            if t.isdigit() and len(t) == 4:
                run.append(w)
                continue
            if len(run) in (3, 4):
                kind = "AADHAAR" if len(run) == 3 else "VID"
                digits = []
                for r in run:
                    x0, y0, x1, y1 = r.bbox_pt
                    cw = (x1 - x0) / 4
                    digits += [_px((x0 + i * cw, y0, x0 + (i + 1) * cw, y1), s) for i in range(4)]
                bs = [r.bbox_pt for r in run]
                box = (bs[0][0], min(b[1] for b in bs), bs[-1][2], max(b[3] for b in bs))
                last4 = ocr.normalize_token(run[-1].text)
                out.append(IdFinding(type=kind, bbox_px=_px(box, s), digits_px=digits,
                                     confidence=0.6, source=src + "-suspect",
                                     value_masked=("XXXX " * (len(run) - 1)) + last4))
            run = []
    return out


def _address(lines: list[list], s: float, src: str) -> list[IdFinding]:
    """Geometric block: from the 'Address' keyword line down to the line holding a 6-digit PIN
    (else ~5 lines), every word at or right of the keyword's column."""
    words = [w for ws in lines for w in ws]
    out = []
    for ws in lines:
        kw = next((w for w in ws if any(w.text.lower().startswith(a) for a in _ADDR_KW)), None)
        if kw is None:
            continue
        lh = kw.bbox_pt[3] - kw.bbox_pt[1]
        x_left, top = kw.bbox_pt[0] - 0.8 * lh, kw.bbox_pt[1] - 0.3 * lh
        col = sorted((w for w in words if w.bbox_pt[0] >= x_left and w.bbox_pt[1] >= top
                      and w.bbox_pt[1] <= top + 10 * lh), key=lambda w: w.bbox_pt[1])
        pin = next((w for w in col if _PIN_RE.match(ocr.normalize_token(w.text))), None)
        bottom = pin.bbox_pt[3] if pin is not None else top + 7 * lh
        block = [w for w in col if (w.bbox_pt[1] + w.bbox_pt[3]) / 2 <= bottom + 0.2 * lh]
        if not block:
            continue
        bs = [w.bbox_pt for w in block]
        pad = 0.25 * lh
        box = (min(b[0] for b in bs) - pad, min(b[1] for b in bs) - pad,
               max(b[2] for b in bs) + pad, max(b[3] for b in bs) + pad)
        out.append(IdFinding(type="ADDRESS", bbox_px=_px(box, s), confidence=0.75, source=src))
    return out


def _qr_quads(gray: np.ndarray) -> list[tuple[np.ndarray, bool]]:
    """(corner points, is_our_badge) from two detectors: the classic one decodes (only to tell
    our badge apart); the ArUco-based one finds small/dense codes the classic one misses."""
    quads: list[tuple[np.ndarray, bool]] = []
    det = cv2.QRCodeDetector()
    ok, texts, pts, _ = det.detectAndDecodeMulti(gray)
    if ok and pts is not None:
        for t, p in zip(texts, pts, strict=False):
            quads.append((p, bool(t) and t.startswith(QR_PREFIX)))
        del texts  # decoded payloads are never kept
    try:
        ok, pts = cv2.QRCodeDetectorAruco().detectMulti(gray)
        if ok and pts is not None:
            quads.extend((p, False) for p in pts)
    except (AttributeError, cv2.error):
        pass
    if not quads and min(gray.shape) < 1500:  # small/soft capture: try again at 2x
        up = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        try:
            ok, pts = cv2.QRCodeDetectorAruco().detectMulti(up)
            if ok and pts is not None:
                quads.extend((p / 2.0, False) for p in pts)
        except (AttributeError, cv2.error):
            pass
    return quads


def qr_like(gray: np.ndarray) -> list[PxBox]:
    """Classical fallback for QR codes too small/blurry to decode or even detect: a square,
    densely edged block that is roughly half dark (text paragraphs are ~10-20% dark, photos
    have few sharp edges). Used in careful mode, where hiding a little extra is the point."""
    h, w = gray.shape
    k = max(9, min(h, w) // 25)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 50, 150)
    density = cv2.blur((edges > 0).astype(np.float32), (k, k))
    mask = (density > 0.16).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k // 2 | 1, k // 2 | 1), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    _, dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    out = []
    for c in cs:
        x, y, bw, bh = cv2.boundingRect(c)
        side = min(bw, bh)
        if not (0.12 * min(h, w) <= side <= 0.6 * min(h, w)) or not 0.75 <= bw / bh <= 1.33:
            continue
        if cv2.contourArea(c) < 0.7 * bw * bh:
            continue
        frac = float((dark[y : y + bh, x : x + bw] > 0).mean())
        if 0.3 <= frac <= 0.65:
            out.append((x, y, x + bw, y + bh))
    return out


def codes(rgb: np.ndarray) -> list[IdFinding]:
    """QR codes and 1-D barcodes. Our own badge QR (SKID1|...) is tagged BADGE. Detection
    without decoding still counts (fail closed: an undecodable QR is still masked)."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    out: list[IdFinding] = []
    for p, badge in _qr_quads(gray):
        xs, ys = p[:, 0], p[:, 1]
        b = (int(xs.min()), int(ys.min()), int(np.ceil(xs.max())), int(np.ceil(ys.max())))
        dup = next((q for q in out if _overlap(b, q.bbox_px) > 0.5), None)
        if dup is not None:
            if badge:
                dup.type = "BADGE"
            continue
        out.append(IdFinding(type="BADGE" if badge else "QR", bbox_px=b, confidence=0.99,
                             source="opencv-qr"))
    for b in qr_like(gray):  # grow partial detections; add codes nothing else found
        hit = next((q for q in out if q.type == "QR" and _overlap(q.bbox_px, b) > 0.2), None)
        if hit is not None:
            hit.bbox_px = (min(hit.bbox_px[0], b[0]), min(hit.bbox_px[1], b[1]),
                           max(hit.bbox_px[2], b[2]), max(hit.bbox_px[3], b[3]))
        elif not any(_overlap(b, q.bbox_px) > 0.3 for q in out):
            out.append(IdFinding(type="QR", bbox_px=b, confidence=0.7, source="qr-texture"))
    try:
        bd = cv2.barcode_BarcodeDetector()
        ok, bpts = bd.detectMulti(gray)
        if ok and bpts is not None:
            for p in bpts:
                xs, ys = p[:, 0], p[:, 1]
                b = (int(xs.min()), int(ys.min()), int(np.ceil(xs.max())), int(np.ceil(ys.max())))
                if not any(_overlap(b, q.bbox_px) > 0.3 for q in out):
                    out.append(IdFinding(type="BARCODE", bbox_px=b, confidence=0.9,
                                         source="opencv-barcode"))
    except (AttributeError, cv2.error):
        pass
    return out


def _overlap(a: PxBox, b: PxBox) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return ix * iy / area


def faces(rgb: np.ndarray) -> list[IdFinding]:
    """Classical portrait-region detector: a compact skin-tone blob with a face-like aspect.
    Faces are never masked; this only reports where the photo is (watermark covers it anyway)."""
    h, w = rgb.shape[:2]
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    skin = cv2.inRange(ycc, (40, 135, 80), (240, 175, 130))
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(skin)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < 0.0008 * h * w or area > 0.2 * h * w:
            continue
        if not 0.55 <= bw / max(bh, 1) <= 1.6 or area < 0.5 * bw * bh:
            continue
        pad = int(0.35 * max(bw, bh))
        out.append(IdFinding(type="FACE", bbox_px=(max(0, x - pad), max(0, y - pad),
                                                   min(w, x + bw + pad), min(h, y + bh + 2 * pad)),
                             confidence=0.6, source="skin-region"))
    return out


FP_PAD_IN = 0.12  # extra margin around every detected print, inches


def _enclosing_frame(gray: np.ndarray, b: PxBox) -> PxBox | None:
    """A drawn rectangle (thumb box) that contains the detection and is not much bigger."""
    x0, y0, x1, y1 = b
    bw, bh = x1 - x0, y1 - y0
    h, w = gray.shape
    X0, Y0 = max(0, x0 - 2 * bw), max(0, y0 - 2 * bh)
    X1, Y1 = min(w, x1 + 2 * bw), min(h, y1 + 2 * bh)
    roi = gray[Y0:Y1, X0:X1]
    _, ink = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(15, bw // 2), 1))) | cv2.morphologyEx(
        ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, bh // 2))))
    cs, _ = cv2.findContours(lines, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cs:
        cx, cy, cw, ch = cv2.boundingRect(c)
        fx0, fy0, fx1, fy1 = cx + X0, cy + Y0, cx + cw + X0, cy + ch + Y0
        if fx0 <= x0 + 4 and fy0 <= y0 + 4 and fx1 >= x1 - 4 and fy1 >= y1 - 4 \
                and cw * ch <= 12 * bw * bh:
            if best is None or cw * ch < (best[2] - best[0]) * (best[3] - best[1]):
                best = (fx0, fy0, fx1, fy1)
    return best


ID_MIN_DENSITY = 0.75  # recall over precision on ID captures (JPEG blocking lowers density)
ID_MIN_SCORE = 0.8


def _print_boxes(gray: np.ndarray, dpi: int, faces: list[PxBox] = ()
                 ) -> list[tuple[PxBox, float]]:
    """fp_classical candidates, with the density gate relaxed for high-scoring components:
    an extra mask costs nothing, a missed print is a leak. Relaxed (not strict) candidates
    lying mostly on a detected portrait are dropped: the photo must stay visible."""
    s = dpi / fp_classical.ANALYSIS_DPI
    pad = fp_classical.BOX_PAD_PX
    out = []
    for (x0, y0, x1, y1), f, area, ok in fp_classical.analyze(gray, dpi)[:-1]:
        relaxed = (not ok and f and f["dens"] >= ID_MIN_DENSITY and f["score"] >= ID_MIN_SCORE
                   and fp_classical._passes({**f, "dens": fp_classical.MIN_DENSITY}, area))
        if not (ok or relaxed):
            continue
        b = (int((x0 - pad) * s), int((y0 - pad) * s), int((x1 + pad) * s), int((y1 + pad) * s))
        if any(_overlap(fc, b) > 0.6 for fc in faces):
            continue  # covers most of the portrait: that's the ID photo, not a thumb impression
        if relaxed and any(_overlap(b, fc) > 0.5 for fc in faces):
            continue
        out.append((b, float(f["score"])))
    return out


def fingerprints(gray: np.ndarray, dpi: int, faces: list[PxBox] = ()) -> list[IdFinding]:
    """Thumb impressions, boxes grown to the enclosing thumb-box frame (if any) plus a margin:
    a partial detection must never leave part of a print behind."""
    pad = int(FP_PAD_IN * dpi)
    h, w = gray.shape
    out = []
    for b, score in _print_boxes(gray, dpi, faces):
        frame = _enclosing_frame(gray, b)
        if frame is not None:
            b = frame
        b = (max(0, b[0] - pad), max(0, b[1] - pad), min(w, b[2] + pad), min(h, b[3] + pad))
        out.append(IdFinding(type="FINGERPRINT", bbox_px=b, confidence=round(score, 3),
                             source="classical" + ("+frame" if frame else "")))
    return out


_LATIN_WORD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/:.,'-]{2,}$")


def latin_quality(pt: PageText) -> float:
    """Mean OCR confidence over Latin/digit words of 3+ chars. Real Aadhaar cards carry
    Hindi/regional script that English OCR turns into low-confidence noise; that noise says
    nothing about whether the numbers we must hide are readable."""
    confs = [w.conf for w in pt.words if _LATIN_WORD.match(w.text.strip())]
    return float(sum(confs) / len(confs)) if confs else 0.0


def _verified(fs: list[IdFinding]) -> bool:
    return any(f.type in ("AADHAAR", "VID") and not f.source.endswith("-suspect") for f in fs)


def scan(rgb: np.ndarray, dpi: int, doc_kind: str = "unknown") -> Scan:
    """`doc_kind="id_card"`: a single Aadhaar/PAN card. Those never carry thumb impressions,
    and their guilloche seals look ridge-like, so the print detector is skipped there."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    pt = ocr.ocr_image(gray, dpi, lang="eng")
    text = text_findings(pt, dpi)
    quality = latin_quality(pt)
    if not _verified(text):
        # second pass, block-text mode: rescues small/soft captures where sparse mode misreads
        # a digit. Verified numbers replace overlapping suspects; nothing is ever dropped.
        pt6 = ocr.ocr_image(gray, dpi, lang="eng", psm=6)
        extra = [f for f in text_findings(pt6, dpi) if f.type in ("AADHAAR", "VID", "PAN")
                 and not f.source.endswith("-suspect")]
        if extra:
            text = [f for f in text if not (f.source.endswith("-suspect") and any(
                _overlap(f.bbox_px, e.bbox_px) > 0.3 for e in extra))] + extra
            quality = max(quality, latin_quality(pt6))
    portraits = faces(rgb)
    prints = [] if doc_kind == "id_card" else fingerprints(gray, dpi,
                                                          [f.bbox_px for f in portraits])
    found = [*text, *codes(rgb), *portraits, *prints]
    return Scan(findings=found, ocr_quality=quality, words=len(pt.words))
