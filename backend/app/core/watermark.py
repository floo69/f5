"""Purpose watermark: dense diagonal tiles burned into the pixels, crossing face and text lines.

Rows alternate two inks and carry a per-issue nonce at a seeded random phase, so no two
issues share a pattern and no clean template exists to subtract. The row pitch is
smaller than a face or an ID line, so cropping cannot avoid it, and erasing it changes
sealed tiles (see badge.py). Drawn BEFORE masks are zeroed; the zeroing comes last.
"""

from __future__ import annotations

import hashlib
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[3] / "synth" / "fonts" / "NotoSans-Bold.ttf"
ANGLE_DEG = 28.0
INKS = ((176, 22, 40), (40, 40, 150))  # crimson, indigo
ALPHA = 0.30


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def burn(rgb: np.ndarray, text: str, nonce: str) -> np.ndarray:
    """Return a new RGB array with the tiled watermark alpha-blended in."""
    h, w = rgb.shape[:2]
    size = max(12, int(min(w, h) / 26))
    font = _font(size)
    rng = random.Random(int(hashlib.sha256(nonce.encode()).hexdigest()[:16], 16))
    diag = int((w * w + h * h) ** 0.5) + 2 * size
    layer = Image.new("L", (diag, diag), 0)
    ink = Image.new("L", (diag, diag), 0)  # row bands: which of the two inks to use
    unit = f"{text}  •  {nonce}  •  "
    x0, y0, x1, y1 = font.getbbox(unit)
    tile = Image.new("L", (int(x1) + 1, int(y1) + 2), 0)
    ImageDraw.Draw(tile).text((0, 0), unit, font=font, fill=255)  # rendered once, pasted often
    unit_w = int(ImageDraw.Draw(tile).textlength(unit, font=font))
    pitch = int(size * 2.1)
    di = ImageDraw.Draw(ink)
    for row, y in enumerate(range(-pitch, diag, pitch)):
        if row % 2:
            di.rectangle([0, y - size // 2, diag, y + pitch - size // 2], fill=255)
        x = -int(rng.uniform(0, unit_w))
        while x < diag:
            layer.paste(255, (x, y), tile)
            x += unit_w
    rot = [im.rotate(ANGLE_DEG, resample=Image.BILINEAR, center=(diag / 2, diag / 2))
           for im in (layer, ink)]
    ox, oy = (diag - w) // 2, (diag - h) // 2
    a = np.asarray(rot[0], np.float32)[oy : oy + h, ox : ox + w, None] / 255.0 * ALPHA
    which = np.asarray(rot[1], np.uint8)[oy : oy + h, ox : ox + w, None] > 127
    color = np.where(which, np.array(INKS[1], np.float32), np.array(INKS[0], np.float32))
    out = rgb.astype(np.float32) * (1 - a) + color * a
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)
