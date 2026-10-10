"""Style spaces for synthetic data, per split.

train and val share one space. test uses DISJOINT ink colours and blur/scan-degradation
ranges so evaluation measures generalisation, not memorisation. Keep this table the single
source of truth: fingerprint_gen and deed_gen sample from here.
"""

from __future__ import annotations

import numpy as np

PATTERNS = ("arch", "tented_arch", "left_loop", "right_loop", "whorl", "double_loop")

# RGB, 0-255
INKS = {
    "train": {
        "purple": (88, 40, 140),
        "blue": (30, 52, 160),
        "black": (28, 28, 34),
    },
    "test": {
        "violet_red": (122, 30, 92),
        "teal": (20, 82, 96),
        "brown_black": (64, 42, 30),
    },
}
INKS["val"] = INKS["train"]

# Gaussian blur sigma (px at 200 dpi) applied to the impression itself.
FP_BLUR = {"train": (0.0, 1.1), "val": (0.0, 1.1), "test": (1.1, 1.9)}

# Scanned-mode degradations.
SCAN = {
    "train": {"blur": (0.0, 0.9), "jpeg_q": (45, 85), "noise": (2.0, 7.0), "yellow": (0.0, 0.35)},
    "val": {"blur": (0.0, 0.9), "jpeg_q": (45, 85), "noise": (2.0, 7.0), "yellow": (0.0, 0.35)},
    "test": {"blur": (0.9, 1.5), "jpeg_q": (30, 45), "noise": (7.0, 11.0), "yellow": (0.35, 0.55)},
}


def sample_fp_style(rng: np.random.Generator, split: str = "train") -> dict:
    """Style dict accepted by synth.fingerprint_gen.generate()."""
    inks = INKS[split]
    ink_name = list(inks)[int(rng.integers(len(inks)))]
    lo, hi = FP_BLUR[split]
    return {
        "pattern": PATTERNS[int(rng.integers(len(PATTERNS)))],
        "ink_name": ink_name,
        "ink_rgb": inks[ink_name],
        "ridge_period": float(rng.uniform(7.0, 11.0)),  # px; frequency 1/11..1/7
        "height_px": int(rng.integers(120, 261)),  # at 200 dpi
        "aspect": float(rng.uniform(0.65, 0.80)),  # width / height
        "rotation_deg": float(rng.uniform(-35, 35)),
        "blur_sigma": float(rng.uniform(lo, hi)),
        "pressure": float(rng.uniform(0.0, 1.0)),  # 0 = even, 1 = very uneven
        "fade": float(rng.uniform(0.0, 0.6)),  # 0 = full ink, 1 = invisible
        "bleed_px": int(rng.integers(0, 3)),  # dilation radius
        "partial": float(rng.uniform(0.0, 0.35)) if rng.random() < 0.3 else 0.0,  # clipped fraction
        "smudge": float(rng.uniform(0.0, 1.0)) if rng.random() < 0.3 else 0.0,
        "iterations": int(rng.integers(8, 16)),
    }


def sample_scan_style(rng: np.random.Generator, split: str = "train") -> dict:
    s = SCAN[split]
    return {
        "skew_deg": float(rng.uniform(-2.0, 2.0)),
        "blur_sigma": float(rng.uniform(*s["blur"])),
        "jpeg_quality": int(rng.integers(s["jpeg_q"][0], s["jpeg_q"][1] + 1)),
        "noise_std": float(rng.uniform(*s["noise"])),
        "yellowing": float(rng.uniform(*s["yellow"])),
    }
