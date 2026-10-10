"""Tests for the procedural thumb-impression generator (nothing is written to disk)."""

import numpy as np
import pytest

from synth.fingerprint_gen import generate
from synth.styles import PATTERNS, sample_fp_style


def _style(seed: int, split: str = "train", **overrides) -> dict:
    style = sample_fp_style(np.random.default_rng(seed), split)
    style.update(overrides)
    return style


def test_deterministic_and_seed_sensitive():
    style = _style(1)
    a = generate(7, style)
    b = generate(7, dict(style))
    assert a.shape == b.shape and np.array_equal(a, b)
    assert np.array_equal(generate(7), generate(7))
    c = generate(8, style)
    assert a.shape != c.shape or not np.array_equal(a, c)
    assert not np.array_equal(generate(3), generate(4))


def test_dtype_shape_and_colour():
    style = _style(2, rotation_deg=0.0, partial=0.0)
    out = generate(5, style)
    assert out.dtype == np.uint8 and out.ndim == 3 and out.shape[2] == 4
    ink = np.asarray(style["ink_rgb"])
    inked = out[out[..., 3] > 128][:, :3].astype(int)
    assert np.all(np.abs(inked.mean(axis=0) - ink) < 20)  # colour ~ ink_rgb, lightly modulated
    # Tight crop: the first/last rows and columns must contain some ink.
    alpha = out[..., 3]
    assert alpha[0].any() and alpha[-1].any() and alpha[:, 0].any() and alpha[:, -1].any()


@pytest.mark.parametrize("split", ["train", "test"])
@pytest.mark.parametrize("pattern", PATTERNS)
def test_every_pattern_and_split(pattern, split):
    for seed in range(3):
        style = _style(100 + seed, split, pattern=pattern)
        out = generate(seed, style)
        coverage = (out[..., 3] > 64).mean()
        assert 0.12 <= coverage <= 0.85, (pattern, split, seed, coverage)
        h = style["height_px"]
        assert 0.6 * h <= out.shape[0] <= 1.4 * h, (pattern, split, seed, out.shape)
        assert out.shape[1] >= 0.5 * h * style["aspect"]


def test_style_none_samples_train_space():
    out = generate(11)
    assert out.dtype == np.uint8 and out.shape[2] == 4
    assert (out[..., 3] > 64).mean() > 0.1


def test_effects_extremes_still_visible():
    style = _style(
        3, "test", partial=0.35, pressure=1.0, fade=0.6, smudge=1.0, bleed_px=2, blur_sigma=1.9
    )
    out = generate(9, style)
    assert (out[..., 3] > 32).mean() > 0.1
    assert out.shape[0] >= 0.6 * style["height_px"]


def test_does_not_mutate_style():
    style = _style(4)
    snapshot = dict(style)
    generate(1, style)
    assert style == snapshot
