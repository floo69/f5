"""Procedural synthetic thumb impressions (no real fingerprint data involved).

Pipeline
1. Orientation field from singular points (Sherlock-Monro): the ridge direction at z is
   0.5 * (sum arg(z - core_i) - sum arg(z - delta_j)), plus a low-frequency perturbation.
   Plain arches use a smooth analytic field with no singularities.
2. Ridges are grown by iterated oriented Gabor filtering of white noise. For speed the
   growth runs at a fixed working ridge period of WORK_PERIOD px (small 11x11 kernels),
   orientation is quantised into N_BINS bins, and each bin is filtered only inside the
   bounding box of its pixels. The result is resized to the requested ridge period.
3. Soft binarisation, elliptical thumb mask, and ink effects (pressure, partial print,
   bleed, smudge, blur, fade), rotation on an expanded canvas, tight crop to alpha > 0.

generate() returns RGBA uint8; RGB is the ink colour (slightly modulated), A is ink
coverage. Fully deterministic in (seed, style). Nothing is ever written to disk here.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from synth.styles import sample_fp_style

WORK_PERIOD = 4.0  # ridge period (px) at which ridges are grown
N_BINS = 16  # orientation quantisation over [0, pi)
KSIZE = 11  # Gabor kernel size at the working period
SIGMOID_GAIN = 4.0  # steepness of the soft binarisation
NOISE_REINJECT = 0.8  # initial amplitude of noise re-injected during ridge growth

# Singular points per pattern, in units of the thumb half-width / half-height,
# origin at the ellipse centre, y UP.  (cores, deltas)
_PRESETS: dict[str, tuple[list[tuple[float, float]], list[tuple[float, float]]]] = {
    "tented_arch": ([(0.0, -0.05)], [(0.0, -0.45)]),
    "left_loop": ([(-0.05, 0.15)], [(0.55, -0.55)]),
    "right_loop": ([(0.05, 0.15)], [(-0.55, -0.55)]),
    "whorl": ([(-0.04, 0.1), (0.04, 0.1)], [(-0.6, -0.5), (0.6, -0.5)]),
    "double_loop": ([(-0.18, 0.28), (0.18, -0.08)], [(-0.6, -0.55), (0.6, -0.5)]),
}


def _lowfreq_noise(rng: np.random.Generator, h: int, w: int, cells: int) -> np.ndarray:
    """Smooth random field in roughly [-1, 1], from a cells x cells grid upsampled cubically."""
    g = rng.uniform(-1.0, 1.0, (cells, cells)).astype(np.float32)
    return cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)


def _orientation_field(h: int, w: int, pattern: str, rng: np.random.Generator) -> np.ndarray:
    """Ridge direction in radians (y-up convention) for an h x w grid."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    x = (xs - (w - 1) / 2) / (w / 2)  # [-1, 1]
    y = ((h - 1) / 2 - ys) / (h / 2)  # [-1, 1], up

    if pattern == "arch":
        # Ridges follow the bump y = A * exp(-x^2 / 2s^2) (tangent angle = atan(dy/dx));
        # the arch is strongest in the upper half and flattens toward the base.
        s = rng.uniform(0.45, 0.7)
        amp = rng.uniform(0.5, 0.9) * np.clip(0.7 + 0.5 * y, 0.2, 1.1)
        theta = np.arctan(-amp * x / s**2 * np.exp(-(x**2) / (2 * s**2)))
    else:
        cores, deltas = _PRESETS[pattern]
        jitter = 0.08
        theta = np.zeros((h, w), np.float32)
        for cx, cy in cores:
            cx += rng.uniform(-jitter, jitter)
            cy += rng.uniform(-jitter, jitter)
            theta += 0.5 * np.arctan2(y - cy, x - cx)
        for dx, dy in deltas:
            dx += rng.uniform(-jitter, jitter)
            dy += rng.uniform(-jitter, jitter)
            theta -= 0.5 * np.arctan2(y - dy, x - dx)

    theta += 0.12 * _lowfreq_noise(rng, h, w, 4)
    return theta.astype(np.float32)


def _gabor_bank(period: float) -> list[np.ndarray]:
    """Zero-mean Gabor kernels, one per orientation bin (ridge direction = bin angle)."""
    bank = []
    for b in range(N_BINS):
        ridge_dir = b * math.pi / N_BINS
        # cv2's theta is the direction of the cosine variation (normal to the ridges),
        # measured in image coordinates (y down), hence the sign flip.
        k = cv2.getGaborKernel(
            (KSIZE, KSIZE), 0.5 * period, -ridge_dir + math.pi / 2, period, 0.5, 0, cv2.CV_32F
        )
        k -= k.mean()
        bank.append(k / np.abs(k).sum())
    return bank


def _grow_ridges(theta: np.ndarray, iterations: int, rng: np.random.Generator) -> np.ndarray:
    """Iterated oriented filtering of noise; returns a zero-mean, unit-std ridge image."""
    h, w = theta.shape
    bins = np.rint(np.mod(theta, math.pi) / (math.pi / N_BINS)).astype(np.int32) % N_BINS
    bank = _gabor_bank(WORK_PERIOD)
    pad = KSIZE // 2

    # Per bin: bounding box (with kernel margin) and selection mask inside that box.
    jobs = []
    for b in np.unique(bins):
        sel = bins == b
        rows = np.flatnonzero(sel.any(axis=1))
        cols = np.flatnonzero(sel.any(axis=0))
        y0, y1 = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, h)
        x0, x1 = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, w)
        jobs.append((bank[b], (slice(y0, y1), slice(x0, x1)), sel[y0:y1, x0:x1]))

    img = rng.standard_normal((h, w)).astype(np.float32)
    out = np.empty_like(img)
    for i in range(iterations):
        for kernel, box, sel in jobs:
            r = cv2.filter2D(img[box], -1, kernel, borderType=cv2.BORDER_REFLECT)
            np.copyto(out[box], r, where=sel)
        img = (out - out.mean()) / (out.std() + 1e-6)
        img = np.tanh(img)  # soft clip keeps the dynamic range bounded
        # Re-inject (decaying) noise so ridge phases disagree locally, which is what
        # produces endings and bifurcations instead of perfectly parallel stripes.
        amp = NOISE_REINJECT * (1.0 - (i + 1) / iterations)
        if amp > 0.02:
            img += amp * rng.standard_normal((h, w)).astype(np.float32)
    # Local contrast normalisation: near singular points the filter response is weak,
    # which would otherwise binarise to a grey cloud instead of crisp ridges.
    img -= img.mean()
    k = int(3 * WORK_PERIOD) | 1
    local_rms = np.sqrt(cv2.blur(img * img, (k, k)) + 1e-4)
    return img / local_rms


def _thumb_mask(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    """Soft, slightly irregular egg-shaped mask in [0, 1]."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    x = (xs - (w - 1) / 2) / (w / 2 - 1)
    y = ((h - 1) / 2 - ys) / (h / 2 - 1)
    x = x / (1.0 - 0.12 * y)  # narrower at the tip
    rho = np.sqrt(x * x + y * y)
    phi = np.arctan2(y, x)
    wobble = np.zeros_like(rho)
    for k in range(2, 6):
        wobble += rng.uniform(0.0, 0.04) * np.sin(k * phi + rng.uniform(0, 2 * math.pi))
    edge = 0.05
    return np.clip((1.0 + wobble - rho) / edge, 0.0, 1.0).astype(np.float32)


def _motion_kernel(length: int, angle: float) -> np.ndarray:
    k = np.zeros((length, length), np.float32)
    c = (length - 1) / 2
    cv2.line(
        k,
        (int(round(c - c * math.cos(angle))), int(round(c - c * math.sin(angle)))),
        (int(round(c + c * math.cos(angle))), int(round(c + c * math.sin(angle)))),
        1.0,
        1,
    )
    return k / max(k.sum(), 1.0)


def _apply_effects(ridges: np.ndarray, style: dict, rng: np.random.Generator) -> np.ndarray:
    """Ridge field (full size) -> ink coverage map in [0, 1], unrotated."""
    h, w = ridges.shape

    # Uneven pressure: biases ridge thickness before binarisation and dims the ink.
    pressure = _lowfreq_noise(rng, h, w, 3)
    ink = 1.0 / (1.0 + np.exp(-SIGMOID_GAIN * (ridges + 1.1 * style["pressure"] * pressure)))
    ink *= np.clip(1.0 - 0.35 * style["pressure"] * (pressure + 0.5), 0.4, 1.0)
    ink *= _thumb_mask(h, w, rng)

    # Partial print: clip a fraction from one side with a soft, wavy edge.
    side = int(rng.integers(4))
    if style["partial"] > 0:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        coord, size, perp = (ys, h, xs) if side < 2 else (xs, w, ys)
        if side % 2:
            coord = size - 1 - coord
        wave = 3.0 * np.sin(perp / size * 2 * math.pi * rng.uniform(1, 3) + rng.uniform(0, 6.3))
        cut = style["partial"] * size
        ink *= np.clip((coord - cut + wave) / 4.0, 0.0, 1.0)

    if style["bleed_px"] > 0:
        r = int(style["bleed_px"])
        el = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        ink = cv2.dilate(ink, el)

    if style["smudge"] > 0:
        length = int(3 + 14 * style["smudge"]) | 1
        smeared = cv2.filter2D(ink, -1, _motion_kernel(length, rng.uniform(0, math.pi)))
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * h
        rad = (0.25 + 0.3 * style["smudge"]) * h
        blob = np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * rad * rad)).astype(np.float32)
        blob *= style["smudge"]
        ink = ink * (1 - blob) + np.minimum(1.4 * smeared, 1.0) * blob

    if style["blur_sigma"] > 0.15:
        # Blur spreads the ink but should not wash it out: keep the peak darkness.
        peak = float(ink.max())
        ink = cv2.GaussianBlur(ink, (0, 0), style["blur_sigma"])
        ink *= min(peak / (float(ink.max()) + 1e-6), 1.6)

    return np.clip(ink * (1.0 - style["fade"]), 0.0, 1.0).astype(np.float32)


def generate(seed: int, style: dict | None = None) -> np.ndarray:
    """Synthetic thumb impression as RGBA uint8 (H, W, 4); array bounds = print bounds."""
    rng = np.random.default_rng(seed)
    if style is None:
        style = sample_fp_style(rng, "train")

    h = int(style["height_px"])
    w = max(8, int(round(h * style["aspect"])))
    scale = style["ridge_period"] / WORK_PERIOD
    hw, ww = max(16, int(round(h / scale))), max(16, int(round(w / scale)))

    theta = _orientation_field(hw, ww, style["pattern"], rng)
    ridges = _grow_ridges(theta, int(style["iterations"]), rng)
    ridges = cv2.resize(ridges, (w, h), interpolation=cv2.INTER_CUBIC)
    ink = _apply_effects(ridges, style, rng)

    # Ink colour, slightly modulated per print and across the impression.
    rgb = np.asarray(style["ink_rgb"], np.float32) + rng.uniform(-6, 6, 3).astype(np.float32)
    tint = _lowfreq_noise(rng, h, w, 3)[..., None] * np.float32(5.0)
    rgba = np.empty((h, w, 4), np.float32)
    rgba[..., :3] = rgb + tint
    rgba[..., 3] = ink * 255.0

    # Rotate on an expanded canvas so nothing is cut off.
    angle = style["rotation_deg"]
    rad = math.radians(abs(angle))
    hh = int(math.ceil(w * math.sin(rad) + h * math.cos(rad))) + 2
    ww2 = int(math.ceil(w * math.cos(rad) + h * math.sin(rad))) + 2
    m = cv2.getRotationMatrix2D(((w - 1) / 2, (h - 1) / 2), angle, 1.0)
    m[0, 2] += (ww2 - w) / 2
    m[1, 2] += (hh - h) / 2
    rgba = cv2.warpAffine(
        rgba,
        m,
        (ww2, hh),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(float(rgb[0]), float(rgb[1]), float(rgb[2]), 0.0),
    )

    out = np.clip(rgba + 0.5, 0, 255).astype(np.uint8)
    rows = np.flatnonzero(out[..., 3].any(axis=1))
    cols = np.flatnonzero(out[..., 3].any(axis=0))
    if rows.size == 0:  # fully faded/clipped: degenerate but keep a valid array
        return out[:1, :1]
    return np.ascontiguousarray(out[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1])
