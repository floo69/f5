"""Capture pre-processing: decode → strip metadata → find document → straighten → even light.

Output is a bare RGB numpy array at a known scale (ID card → 1011x638 @300 dpi, A4 →
1654x2339 @200 dpi). Decoding to raw pixels drops EXIF/GPS/XMP/ICC by construction; we
only report the NAMES of what was dropped. Nothing is written to disk.

Glare/shadow handling divides by a smooth illumination estimate. It never inpaints:
generated fill would fabricate document content.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import cv2
import numpy as np
import pymupdf
from PIL import ExifTags, Image, ImageOps

from .decision import MIN_BLUR_SCORE

CARD = (1011, 638, 300)  # ISO ID-1 85.6 x 54 mm
A4 = (1654, 2339, 200)
CARD_ASPECT = 85.6 / 54.0
A4_ASPECT = 297 / 210
MAX_SIDE = 2339
MIN_QUAD_FRACTION = 0.18
MAX_PIXELS = 40_000_000  # decompression-bomb guard


@dataclass
class Prepared:
    rgb: np.ndarray
    dpi: int
    doc_kind: str  # id_card | a4_page | unknown
    quad_found: bool
    rotation_deg: float
    blur_score: float
    glare_fraction: float
    shadow_corrected: bool
    metadata_removed: list[str] = field(default_factory=list)
    source_px: tuple[int, int] = (0, 0)  # document size in the ORIGINAL capture

    def facts(self) -> dict:
        h, w = self.rgb.shape[:2]
        return {
            "doc_kind": self.doc_kind, "quad_found": self.quad_found,
            "rotation_deg": round(self.rotation_deg, 1), "blur_score": round(self.blur_score, 1),
            "blur_ok": self.blur_score >= MIN_BLUR_SCORE,
            "glare_fraction": round(self.glare_fraction, 4),
            "shadow_corrected": self.shadow_corrected,
            "metadata_removed": self.metadata_removed, "width": w, "height": h, "dpi": self.dpi,
            "source_px": list(self.source_px),
        }


class UnreadableInput(ValueError):
    pass


def decode(data: bytes) -> tuple[np.ndarray, list[str], bool]:
    """(RGB array, names of metadata dropped, is_pdf). PDFs: page 1 rasterised at 200 dpi."""
    if data[:5] == b"%PDF-":
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as e:
            raise UnreadableInput("not a readable PDF") from e
        dropped = [f"PDF:{k}" for k, v in (doc.metadata or {}).items()
                   if v and k not in ("format", "encryption")]
        if doc.xref_xml_metadata():
            dropped.append("PDF:XMP")
        if doc.page_count > 1:
            dropped.append(f"PDF:pages 2-{doc.page_count} (only page 1 is armored)")
        pix = doc[0].get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()
        doc.close()
        return rgb, dropped + ["PDF:text layer", "PDF:fonts"], True
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        raise UnreadableInput("not a readable image") from e
    dropped: list[str] = []
    exif = im.getexif()
    for tag in exif:
        dropped.append(f"EXIF:{ExifTags.TAGS.get(tag, hex(tag))}")
    if ExifTags.IFD.GPSInfo in exif or exif.get_ifd(ExifTags.IFD.GPSInfo):
        if "EXIF:GPSInfo" not in dropped:
            dropped.append("EXIF:GPSInfo")
    for k in im.info:
        if k in ("icc_profile", "xmp", "XML:com.adobe.xmp", "comment", "photoshop", "exif"):
            dropped.append(f"{im.format}:{k}")
        elif im.format == "PNG" and k not in ("dpi", "gamma", "transparency", "aspect"):
            dropped.append(f"PNG:text:{k}")
    im = ImageOps.exif_transpose(im)  # honour orientation, then the tag is gone with the rest
    rgb = np.asarray(im.convert("RGB")).copy()
    return rgb, sorted(set(dropped)), False


def _order(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]],
                    np.float32)


def find_quad(rgb: np.ndarray) -> np.ndarray | None:
    """Document corners (TL, TR, BR, BL) in full-resolution pixels, or None."""
    h, w = rgb.shape[:2]
    s = 900 / max(h, w)
    small = cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    area_min = MIN_QUAD_FRACTION * small.shape[0] * small.shape[1]
    masks = []
    edges = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((3, 3), np.uint8), iterations=2)
    masks.append(edges)
    # documents are usually lighter than the table: brightness/low-saturation segmentation
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    paper = ((hsv[..., 2] > 0) & (hsv[..., 1] < 60)).astype(np.uint8) * 255
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks.append(cv2.morphologyEx(cv2.bitwise_and(paper, otsu), cv2.MORPH_CLOSE,
                                  np.ones((15, 15), np.uint8)))
    best, best_area = None, 0.0
    for m in masks:
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cs, key=cv2.contourArea, reverse=True)[:5]:
            hull = cv2.convexHull(c)
            a = cv2.contourArea(hull)
            if a < area_min or a <= best_area:
                continue
            approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype(np.float32)
            else:  # rounded corners: fall back to the min-area rectangle
                quad = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)
                if a < 0.85 * cv2.contourArea(quad):
                    continue
            best, best_area = quad, a
    if best is None:
        return None
    quad = _order(best / s)
    # a "document" covering the whole frame edge-to-edge is just the frame (flat scan)
    if best_area > 0.97 * small.shape[0] * small.shape[1]:
        return None
    return quad


def _target(w: float, h: float, photographed: bool = False) -> tuple[int, int, int, str]:
    """Canonical size for the closest known document shape (card or A4), else keep.

    Perspective makes a photographed card measure anywhere from ~1.4 to ~1.8, overlapping
    A4's 1.414, so photographed quads use orientation first: landscape -> card (A4 pages are
    shot portrait), portrait -> A4 unless clearly card-shaped."""
    aspect = max(w, h) / max(min(w, h), 1)
    landscape = w >= h
    cw, ch, cdpi = CARD
    aw, ah, adpi = A4
    if photographed and 1.3 <= aspect <= 1.95:
        if landscape:
            return cw, ch, cdpi, "id_card"
        return (aw, ah, adpi, "a4_page") if aspect < 1.5 else (ch, cw, cdpi, "id_card")
    d_card, d_a4 = abs(aspect - CARD_ASPECT), abs(aspect - A4_ASPECT)
    if d_card < 0.15 and d_card <= d_a4:
        return (cw, ch, cdpi, "id_card") if landscape else (ch, cw, cdpi, "id_card")
    if d_a4 < 0.12:
        return (aw, ah, adpi, "a4_page") if not landscape else (ah, aw, adpi, "a4_page")
    s = min(1.0, MAX_SIDE / max(w, h))
    return int(w * s), int(h * s), 200, "unknown"


def _even_light(rgb: np.ndarray) -> tuple[np.ndarray, bool, float]:
    """Divide out a smooth illumination field (shadows, glare halo). Returns
    (image, corrected?, glare fraction measured before correction)."""
    small = cv2.resize(rgb, None, fx=0.125, fy=0.125, interpolation=cv2.INTER_AREA)
    # glare = near-saturated pixels clearly brighter than the paper around them
    g = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    paper = cv2.medianBlur(g, 15)
    glare = float(((g >= 245) & (g.astype(np.int16) - paper >= 10)).mean())
    bg = cv2.dilate(small, np.ones((5, 5), np.uint8))  # remove dark text, keep paper
    bg = cv2.GaussianBlur(bg, (0, 0), 4)
    lum = cv2.cvtColor(bg, cv2.COLOR_RGB2GRAY).astype(np.float32)
    spread = float(np.percentile(lum, 95) - np.percentile(lum, 5))
    if spread < 28:
        return rgb, False, glare
    bgf = cv2.resize(bg, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
    ref = np.percentile(lum, 90)
    gain = ref / np.maximum(bgf.astype(np.float32), 1.0)
    out = np.clip(rgb.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    return out, True, glare


def blur_score(rgb: np.ndarray) -> float:
    """Variance of the Laplacian on a fixed-scale grey image (scale-normalised)."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    s = 1000 / max(gray.shape)
    if s < 1:
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def prepare(data: bytes) -> Prepared:
    rgb, dropped, is_pdf = decode(data)
    h, w = rgb.shape[:2]
    quad = None if is_pdf else find_quad(rgb)
    rotation = 0.0
    if quad is not None:
        tw = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
        th = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
        ow, oh, dpi, kind = _target(tw, th, photographed=True)
        src = (int(tw), int(th))
        m = cv2.getPerspectiveTransform(quad, np.float32([[0, 0], [ow, 0], [ow, oh], [0, oh]]))
        rgb = cv2.warpPerspective(rgb, m, (ow, oh), flags=cv2.INTER_LANCZOS4,
                                  borderMode=cv2.BORDER_REPLICATE)
        dx, dy = quad[1] - quad[0]
        rotation = float(np.degrees(np.arctan2(dy, dx)))
    else:
        ow, oh, dpi, kind = _target(w, h)
        src = (w, h)
        if (ow, oh) != (w, h):
            rgb = cv2.resize(rgb, (ow, oh), interpolation=cv2.INTER_AREA if ow < w
                             else cv2.INTER_CUBIC)
    rgb, corrected, glare = _even_light(rgb)
    return Prepared(rgb=np.ascontiguousarray(rgb), dpi=dpi, doc_kind=kind,
                    quad_found=quad is not None, rotation_deg=rotation,
                    blur_score=blur_score(rgb), glare_fraction=glare,
                    shadow_corrected=corrected, metadata_removed=dropped, source_px=src)
