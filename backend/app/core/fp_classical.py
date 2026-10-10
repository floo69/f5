"""Classical (non-ML) thumb-impression detector. DEFENSIVE: finds regions so they can be destroyed.

Nothing here extracts, stores or exports fingerprint pixels: only bounding boxes and scalar
statistics leave this module.

Method (a ridge-field detector; tuned on the synthetic VAL split only)
  1. Work at 100 dpi (ridge periods become ~3.5-5.5 px). Long thin axis-aligned rules (thumb-box
     frames, signature lines) are removed first; they are strong, coherent, and not ridges.
  2. A Gabor filter bank (orientations x periods inside the ridge band) gives per-pixel ridge
     energy. Prints are *filled 2-D areas* of single-orientation, single-period texture; text,
     strokes, rings and wavy lines are 1-D or sparse, so after smoothing + threshold +
     a morphological opening wider than a stroke, only filled areas survive.
  3. Connected components are gated on rotated-rect size/aspect (a thumb impression is
     0.4-1.9 in x 0.3-1.4 in), solidity, ellipse fill, local orientation coherence (structure-tensor
     style: QR/checkerboards fail), and a "hollow ring" test (seals fail).
  4. Score = f(local coherence, ridge energy, ellipse fit, frequency stability, size fit).
Fail-closed spirit: thresholds favour recall; extra boxes only cost a harmless redaction.
Tunables are module-level constants.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
import pymupdf

from .types import Finding

cv2.setNumThreads(1)

ANALYSIS_DPI = 100.0

# ---- rule (axis-aligned line) removal
RULE_LEN = 51  # px @100dpi; ridge curves are never this straight
RULE_INK_DELTA = 55.0  # darker than the page background by this much counts as ink
SKEW_MAX = 3.0
SKEW_STEP = 0.5
RULE_THICK_OPEN = 5  # blobs thicker than this are ink areas, not rules

# ---- Gabor bank (px @100dpi)
GABOR_PERIODS = (4.0, 5.0)
GABOR_ORIENTS = 6
GABOR_SIGMA = 2.6
GABOR_K = 11
BG_SIGMA = 6.0  # subtract local mean before filtering

# ---- candidate extraction
SMOOTH_SIGMA = 3.0
AMP_CLIP = 250.0  # strong lines (frames, rules) must not bleed into wide bands
AMP_THRESHOLD = 100.0  # sqrt(Gabor energy), page-intensity units
NOISE_PERCENTILE = 25  # page noise floor = this percentile of the ridge amplitude map
NOISE_K = 3.0  # threshold >= NOISE_K x noise floor (scans are noisy, born-digital pages are not)
CLOSE_K = 5
OPEN_K = 17
MIN_COMPONENT_AREA = 400

# ---- shape / texture gates
MIN_LONG, MAX_LONG = 30.0, 170.0  # px @100dpi (rotated-rect long side)
MIN_SHORT, MAX_SHORT = 22.0, 135.0
ASPECT_MIN = 0.45
MIN_SOLIDITY = 0.70
MIN_AREA = 1200
MIN_ELLIPSE_FILL, MAX_ELLIPSE_FILL = 0.80, 1.12  # rectangles (QR, boxes) have 1.27
MIN_LOCAL_COH = 0.68  # QR / checkerboard ~0.58, prints 0.75-0.96
SEAL_CENTRE_ACTIVITY = 0.50  # hollow ring: little ridge energy in the middle
SEAL_MIN_ASPECT = 0.90

MIN_DENSITY = 0.85  # filled ridge area vs sparse strokes (signatures)
BOX_PAD_PX = 4  # @100dpi, around the component
MIN_SCORE = 0.0

_BANK: list[tuple[np.ndarray, np.ndarray]] | None = None


def _bank() -> list[tuple[np.ndarray, np.ndarray]]:
    """[(even, odd)] kernels, orientation-major, period-minor."""
    global _BANK
    if _BANK is None:
        r = GABOR_K // 2
        ys, xs = np.mgrid[-r : r + 1, -r : r + 1].astype(np.float32)
        env = np.exp(-(xs**2 + ys**2) / (2 * GABOR_SIGMA**2))
        bank = []
        for k in range(GABOR_ORIENTS):
            th = math.pi * k / GABOR_ORIENTS
            u = xs * math.cos(th) + ys * math.sin(th)
            for per in GABOR_PERIODS:
                ph = 2 * math.pi * u / per
                ev = env * np.cos(ph)
                ev -= env * (ev.sum() / env.sum())
                bank.append((ev.astype(np.float32), (env * np.sin(ph)).astype(np.float32)))
        _BANK = bank
    return _BANK


def _estimate_skew(img: np.ndarray) -> float:
    """Page skew in degrees (|.| <= SKEW_MAX) from row-projection variance of a 25-dpi ink map."""
    tiny = cv2.resize(img, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    bg = float(np.percentile(tiny, 90))
    ink = (tiny < bg - RULE_INK_DELTA).astype(np.float32)
    if ink.sum() < 50:
        return 0.0
    h, w = ink.shape
    best, best_a = -1.0, 0.0
    for ang in np.arange(-SKEW_MAX, SKEW_MAX + 1e-6, SKEW_STEP):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(ang), 1.0)
        prof = cv2.warpAffine(ink, m, (w, h)).sum(axis=1)
        sc = float(np.square(np.diff(prof)).sum())
        if sc > best:
            best, best_a = sc, float(ang)
    return best_a


def _remove_rules(img: np.ndarray) -> np.ndarray:
    """Paint over long thin straight rules (thumb-box frames, signature lines), skew tolerant."""
    h, w = img.shape
    bg = float(np.percentile(img, 90))
    ang = _estimate_skew(img)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    rot = (
        cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=bg)
        if abs(ang) > 1e-6
        else img
    )
    ink = (rot < bg - RULE_INK_DELTA).astype(np.uint8)
    rules = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, RULE_LEN), np.uint8))
    rules |= cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((RULE_LEN, 1), np.uint8))
    if not rules.any():
        return img
    if abs(ang) > 1e-6:
        mi = cv2.getRotationMatrix2D((w / 2, h / 2), -ang, 1.0)
        rules = cv2.warpAffine(rules, mi, (w, h), flags=cv2.INTER_NEAREST)
        ink = (img < bg - RULE_INK_DELTA).astype(np.uint8)
    thick = cv2.dilate(
        cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((RULE_THICK_OPEN,) * 2, np.uint8)),
        np.ones((7, 7), np.uint8),
    )
    rules = cv2.dilate(rules, np.ones((5, 5), np.uint8)) & (1 - thick)
    out = img.copy()
    out[rules > 0] = bg
    return out


def _gabor_maps(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (amp, orient_idx, period_idx): per-pixel max ridge amplitude over the bank."""
    hp = img - cv2.GaussianBlur(img, (0, 0), BG_SIGMA)
    n_per = len(GABOR_PERIODS)
    best = np.zeros(img.shape, np.float32)
    arg = np.zeros(img.shape, np.uint8)
    for i, (ev, od) in enumerate(_bank()):
        a = cv2.filter2D(hp, cv2.CV_32F, ev)
        b = cv2.filter2D(hp, cv2.CV_32F, od)
        e = a * a + b * b
        upd = e > best
        best = np.where(upd, e, best)
        arg = np.where(upd, np.uint8(i), arg)
    del n_per
    return np.sqrt(best), arg // len(GABOR_PERIODS), arg % len(GABOR_PERIODS)


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _component_features(comp: np.ndarray, amp, orient, period, x, y, w, h, area):
    """Scalar statistics of one component (mask `comp` is local to its bbox)."""
    cnt, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnt, key=cv2.contourArea)
    (_, _), (rw, rh), _ = cv2.minAreaRect(c)
    long_, short = max(rw, rh), min(rw, rh)
    solidity = area / (cv2.contourArea(cv2.convexHull(c)) + 1.0)
    fill = area / (math.pi / 4 * long_ * short + 1e-6)
    a = amp[y : y + h, x : x + w]
    o = orient[y : y + h, x : x + w]
    wgt = a[comp]
    th = math.pi * o[comp] / GABOR_ORIENTS
    # local orientation coherence (9x9 neighbourhoods), amplitude weighted
    c2 = np.cos(2 * math.pi * o / GABOR_ORIENTS) * a
    s2 = np.sin(2 * math.pi * o / GABOR_ORIENTS) * a
    k = (9, 9)
    loc = np.hypot(cv2.boxFilter(c2, -1, k), cv2.boxFilter(s2, -1, k)) / (
        cv2.boxFilter(a, -1, k) + 1e-3
    )
    local_coh = float(loc[comp].mean())
    global_coh = float(abs((wgt * np.exp(2j * th)).sum()) / (wgt.sum() + 1e-6))
    p90 = float(np.percentile(wgt, 90))
    active = (a > 0.3 * p90) & comp
    dens = float(((a > 0.15 * p90) & comp).sum() / comp.sum())
    y0, y1, x0, x1 = int(h * 0.3), int(h * 0.7), int(w * 0.3), int(w * 0.7)
    centre = float(active[y0:y1, x0:x1].mean()) if y1 > y0 and x1 > x0 else 1.0
    pr = period[y : y + h, x : x + w][comp]
    frac = float(pr.mean()) if len(GABOR_PERIODS) == 2 else 0.5
    return {
        "long": long_, "short": short, "solidity": solidity, "fill": fill,
        "local_coh": local_coh, "global_coh": global_coh, "centre": centre,
        "energy": float(np.median(wgt)), "dens": dens, "freq_stab": abs(frac - 0.5) * 2,
    }  # fmt: skip


def _passes(f: dict, area: int) -> bool:
    if area < MIN_AREA:
        return False
    if not (MIN_LONG <= f["long"] <= MAX_LONG and MIN_SHORT <= f["short"] <= MAX_SHORT):
        return False
    if f["short"] / f["long"] < ASPECT_MIN or f["solidity"] < MIN_SOLIDITY:
        return False
    if not (MIN_ELLIPSE_FILL <= f["fill"] <= MAX_ELLIPSE_FILL):
        return False
    if f["local_coh"] < MIN_LOCAL_COH or f["dens"] < MIN_DENSITY:
        return False
    return not (f["centre"] < SEAL_CENTRE_ACTIVITY and f["short"] / f["long"] > SEAL_MIN_ASPECT)


def _score(f: dict) -> float:
    return _clip01(
        0.35 * _clip01((f["local_coh"] - 0.6) / 0.3)
        + 0.25 * _clip01(f["energy"] / 400.0)
        + 0.2 * _clip01(1.0 - abs(f["fill"] - 0.95) / 0.2)
        + 0.1 * _clip01(f["short"] / f["long"] / 0.8)
        + 0.1 * (1.0 - f["freq_stab"] * 0.5)
    )


def analyze(
    gray200: np.ndarray, dpi: int = 200
) -> list[tuple[tuple[int, int, int, int], dict, int, bool]]:
    """All candidate components: (bbox @100dpi, features, area, passed_gates). Scalars only."""
    g = gray200 if gray200.ndim == 2 else cv2.cvtColor(gray200, cv2.COLOR_RGB2GRAY)
    scale = ANALYSIS_DPI / dpi
    small = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA).astype(np.float32)
    prep = _remove_rules(small)
    amp, orient, period = _gabor_maps(prep)
    thr = max(AMP_THRESHOLD, NOISE_K * float(np.percentile(amp, NOISE_PERCENTILE)))
    mask = (cv2.GaussianBlur(np.minimum(amp, AMP_CLIP), (0, 0), SMOOTH_SIGMA) > thr).astype(
        np.uint8
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_K,) * 2)
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (OPEN_K,) * 2)
    )
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    res = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < MIN_COMPONENT_AREA:
            continue
        comp = lab[y : y + h, x : x + w] == i
        f = _component_features(comp, amp, orient, period, x, y, w, h, area)
        f["score"] = _score(f)
        res.append(((x, y, x + w, y + h), f, area, _passes(f, area) and f["score"] >= MIN_SCORE))
    res.append(((0, 0, small.shape[1], small.shape[0]), {}, 0, False))  # page extent sentinel
    return res


def detect_gray(gray200: np.ndarray, page_index: int, dpi: int = 200) -> list[Finding]:
    """Detect thumb impressions on a grayscale page raster. Boxes: PDF points, top-left origin."""
    cands = analyze(gray200, dpi)
    W, H = cands[-1][0][2:]
    pt = 72.0 / ANALYSIS_DPI
    out: list[Finding] = []
    for (x0, y0, x1, y1), f, _area, ok in cands[:-1]:
        if not ok:
            continue
        x0, y0 = max(0, x0 - BOX_PAD_PX), max(0, y0 - BOX_PAD_PX)
        x1, y1 = min(W, x1 + BOX_PAD_PX), min(H, y1 + BOX_PAD_PX)
        out.append(
            Finding(
                type="FINGERPRINT", page=page_index, bbox_pt=(x0 * pt, y0 * pt, x1 * pt, y1 * pt),
                confidence=round(f["score"], 3), source="classical",
            )
        )  # fmt: skip
    return out


def detect_page(page: pymupdf.Page, page_index: int) -> list[Finding]:
    """Render at 200 dpi grayscale and detect."""
    pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.stride)[:, : pix.w]
    return detect_gray(gray, page_index, 200)
