"""Synthetic Indian identity-document images (Aadhaar front/back, PAN, KYC sheet).

Input material for testing the on-device ID masking tool (docs/ARMOR_CONTRACT.md).
All data is generated: Faker(en_IN) names/addresses, Verhoeff-valid fake Aadhaar numbers,
procedurally drawn synthetic portraits (not real faces), synthetic thumb impressions. Every image
carries the visible "SYNTHETIC SAMPLE – NOT A REAL DOCUMENT" watermark.

Ground truth never holds a full number, only `value_masked` (last 4 digits).
Fingerprint images exist only in memory; nothing is written to disk here.
"""

from __future__ import annotations

# ruff: noqa: E501
import copy
import io
import random
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from faker import Faker
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from synth import fingerprint_gen
from synth.deed_gen import _fmt, make_aadhaar, make_vid
from synth.styles import sample_fp_style

KINDS = ("aadhaar_front", "aadhaar_back", "pan", "kyc_sheet")

FONT_DIR = Path(__file__).parent / "fonts"
WATERMARK = "SYNTHETIC SAMPLE – NOT A REAL DOCUMENT"
CARD_W, CARD_H, CARD_DPI = 1011, 638, 300
SHEET_W, SHEET_H, SHEET_DPI = 1654, 2339, 200

INK = (25, 25, 30)
RED = (190, 20, 20)
_FAKER: Faker | None = None


@lru_cache(maxsize=64)
def _font(bold: bool, size: int, dev: bool = False) -> ImageFont.FreeTypeFont:
    base = "NotoSansDevanagari" if dev else "NotoSans"
    name = f"{base}-{'Bold' if bold else 'Regular'}.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _faker(seed: int) -> Faker:
    global _FAKER
    if _FAKER is None:
        _FAKER = Faker("en_IN")
    _FAKER.seed_instance(seed)
    return _FAKER


# --------------------------------------------------------------------------- identity
def _identity(seed: int) -> dict:
    rng = random.Random(seed * 7919 + 13)
    fake = _faker(seed)
    female = rng.random() < 0.5
    first = fake.first_name_female() if female else fake.first_name_male()
    surname = fake.last_name()
    father = f"{fake.first_name_male()} {surname}"
    dob = date(1950, 1, 1) + timedelta(days=rng.randint(0, 365 * 55))
    street = fake.street_address().replace("\n", ", ")
    pin = str(rng.randint(110000, 859999))
    pan = (
        "".join(rng.choice("ABCDEFGHKLMNPRSTUVWXYZ") for _ in range(3))
        + "P"
        + surname.strip()[0].upper()
        + "".join(str(rng.randint(0, 9)) for _ in range(4))
        + rng.choice("ABCDEFGHKLMNPRSTUVWXYZ")
    )
    return {
        "name": f"{first} {surname}",
        "surname": surname,
        "father": father,
        "female": female,
        "dob": dob,
        "aadhaar": make_aadhaar(rng),
        "vid": make_vid(rng) if rng.random() < 0.5 else None,
        "pan": pan,
        "co": f"C/O: {father}",
        "street": street,
        "city": fake.city(),
        "state": fake.state(),
        "pin": pin,
        "skin": rng.choice([(224, 172, 140), (198, 134, 98), (160, 105, 72), (121, 80, 56)]),
        "hair": rng.choice([(25, 20, 18), (45, 32, 24), (70, 60, 55), (150, 150, 150)]),
        "bg": rng.choice([(215, 228, 240), (232, 232, 226), (222, 236, 224)]),
        "seed": seed,
    }


def _masked(digits: str) -> str:
    groups = ["XXXX"] * (len(digits) // 4 - 1) + [digits[-4:]]
    return " ".join(groups)


# --------------------------------------------------------------------------- Devanagari
_D_CONS = {
    "chh": "छ", "kh": "ख", "gh": "घ", "ch": "च", "jh": "झ", "th": "थ", "dh": "ध",
    "ph": "फ", "bh": "भ", "sh": "श", "k": "क", "g": "ग", "j": "ज", "t": "त", "d": "द",
    "n": "न", "p": "प", "f": "फ", "b": "ब", "m": "म", "y": "य", "r": "र", "l": "ल",
    "v": "व", "w": "व", "s": "स", "h": "ह", "z": "ज", "q": "क", "c": "क", "x": "क्स",
}  # fmt: skip
_D_VOW = {
    "aa": "आ", "ee": "ई", "oo": "ऊ", "ai": "ऐ", "au": "औ", "ou": "औ", "a": "अ",
    "i": "इ", "u": "उ", "e": "ए", "o": "ओ",
}  # fmt: skip
_D_MATRA = {
    "aa": "ा", "ee": "ी", "oo": "ू", "ai": "ै", "au": "ौ", "ou": "ौ", "a": "",
    "i": "ि", "u": "ु", "e": "े", "o": "ो",
}  # fmt: skip
_D_WORDS = {"c/o": "सी/ओ", "s/o": "पुत्र", "no": "नं"}


def _translit_word(w: str) -> str:
    """Rough Latin -> Devanagari (approximate by design; cosmetic only)."""
    low = w.lower()
    if low.strip(".:,") in _D_WORDS:
        return _D_WORDS[low.strip(".:,")] + w[len(w.rstrip(".:,")) :]
    toks: list[tuple[str, str]] = []
    i = 0
    while i < len(low):
        for n in (3, 2, 1):
            seg = low[i : i + n]
            if len(seg) == n and seg in _D_VOW:
                toks.append(("V", seg))
                break
            if len(seg) == n and seg in _D_CONS:
                toks.append(("C", seg))
                break
        else:
            toks.append(("O", low[i]))
            n = 1
        i += n
    out = ""
    for k, (kind, v) in enumerate(toks):
        prev = toks[k - 1][0] if k else "O"
        last = k == len(toks) - 1
        if kind == "C":
            out += _D_CONS[v]
            nxt = toks[k + 1][0] if not last else "O"
            if nxt == "C":
                out += "्"
        elif kind == "V":
            if prev == "C":
                if last and len(low) > 3 and v == "a":
                    v = "aa"
                elif last and len(low) > 3 and v == "i":
                    v = "ee"
                out += _D_MATRA[v]
            else:
                out += _D_VOW[v]
        else:
            out += v
    return out


def _translit(text: str) -> str:
    return " ".join(_translit_word(w) for w in text.split())


# --------------------------------------------------------------------------- drawing helpers
class _Filled:
    """ImageDraw proxy that always fills shapes with 255 (mask drawing)."""

    def __init__(self, d: ImageDraw.ImageDraw):
        self._d = d

    def __getattr__(self, name):
        f = getattr(self._d, name)
        return lambda *a, **k: f(*a, **{"fill": 255, **k})


def _mask(size, fn, blur: float = 0.0) -> Image.Image:
    m = Image.new("L", size, 0)
    fn(_Filled(ImageDraw.Draw(m)))
    return m.filter(ImageFilter.GaussianBlur(blur)) if blur else m


def _shaded(size, color, light=(0.35, 0.3), strength=0.35) -> Image.Image:
    """Flat colour with a soft radial light falloff (gives volume)."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.sqrt(((xx / w) - light[0]) ** 2 + ((yy / h) - light[1]) ** 2)
    k = np.clip(1.0 + strength * (0.55 - dist), 0.3, 1.4)
    arr = np.asarray(color, np.float32)[None, None, :] * k[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _avatar(w: int, h: int, ident: dict, rng: np.random.Generator) -> Image.Image:
    """Soft studio-style synthetic head-and-shoulders portrait.

    Fully procedural (gradients + shapes), obviously not a real person.
    """
    S = 2
    W, H = w * S, h * S
    sz = (W, H)
    skin, hair, bgc = ident["skin"], ident["hair"], ident["bg"]
    female = ident["female"]

    def box(x0, y0, x1, y1):
        return [x0 * W, y0 * H, x1 * W, y1 * H]

    # studio backdrop: vertical gradient + vignette
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1.08 - 0.5 * (((xx / W - 0.5) ** 2 + (yy / H - 0.42) ** 2) ** 0.5)
    grad = 1.06 - 0.22 * (yy / H)
    bg = np.asarray(bgc, np.float32)[None, None, :] * (grad * vig)[..., None]
    im = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))

    def put(color, fn, blur=1.5, light=(0.35, 0.3), strength=0.4):
        nonlocal im
        m = _mask(sz, fn, blur * S / 2)
        im = Image.composite(_shaded(sz, color, light, strength), im, m)

    palette = [(70, 82, 112), (128, 66, 62), (66, 94, 84), (182, 172, 152), (92, 92, 102), (150, 122, 92)]
    cloth = palette[int(rng.integers(0, len(palette)))]
    dark = tuple(int(c * 0.82) for c in skin)
    # long hair behind the head and shoulders
    if female:
        put(hair, lambda d: d.ellipse(box(0.16, 0.08, 0.84, 0.96)), 4, (0.3, 0.2), 0.5)
    # soft drop shadow of the subject on the backdrop
    sh = _mask(sz, lambda d: d.ellipse(box(-0.08, 0.80, 1.08, 1.6)), 14 * S)
    im = Image.composite(Image.new("RGB", sz, (0, 0, 0)), im, sh.point(lambda v: int(v * 0.25)))
    # shoulders / clothing
    put(cloth, lambda d: d.ellipse(box(-0.12, 0.76, 1.12, 1.55)), 3, (0.3, 0.7), 0.6)
    # neck (darker, then chin shadow)
    neck = tuple(int(c * 0.9) for c in skin)
    put(neck, lambda d: d.polygon([(0.41 * W, 0.50 * H), (0.59 * W, 0.50 * H), (0.62 * W, 0.80 * H), (0.38 * W, 0.80 * H)]), 3, (0.7, 0.2), 0.5)
    if female:
        put(neck, lambda d: d.ellipse(box(0.36, 0.72, 0.64, 0.92)), 3, (0.7, 0.2), 0.5)
    else:
        put(neck, lambda d: d.polygon([(0.38 * W, 0.76 * H), (0.62 * W, 0.76 * H), (0.5 * W, 0.93 * H)]), 2, (0.7, 0.2), 0.5)
        col = (235, 235, 232)
        put(col, lambda d: d.polygon([(0.36 * W, 0.73 * H), (0.46 * W, 0.78 * H), (0.5 * W, 0.93 * H), (0.40 * W, 0.84 * H)]), 1.5, (0.4, 0.2), 0.3)
        put(col, lambda d: d.polygon([(0.64 * W, 0.73 * H), (0.54 * W, 0.78 * H), (0.5 * W, 0.93 * H), (0.60 * W, 0.84 * H)]), 1.5, (0.6, 0.2), 0.3)
    # neck shadow under jaw
    sh = _mask(sz, lambda d: d.ellipse(box(0.36, 0.60, 0.64, 0.74)), 7 * S)
    im = Image.composite(Image.new("RGB", sz, (30, 15, 10)), im, sh.point(lambda v: int(v * 0.16)))
    # ears
    for ex in (0.262, 0.738):
        put(dark, lambda d, ex=ex: d.ellipse(box(ex - 0.028, 0.37, ex + 0.028, 0.49)), 2, (0.5, 0.3), 0.4)
    # head: cranium + jaw ellipses merged and softened
    def head(d):
        d.ellipse(box(0.26, 0.13, 0.74, 0.55))
        d.ellipse(box(0.29, 0.28, 0.71, 0.65))
    put(skin, head, 3, (0.38, 0.30), 0.55)
    # cheek blush + forehead highlight
    for cx in (0.37, 0.63):
        bl = _mask(sz, lambda d, cx=cx: d.ellipse(box(cx - 0.06, 0.45, cx + 0.06, 0.53)), 8 * S)
        im = Image.composite(Image.new("RGB", sz, (200, 90, 80)), im, bl.point(lambda v: int(v * 0.18)))
    hl = _mask(sz, lambda d: d.ellipse(box(0.40, 0.19, 0.58, 0.28)), 9 * S)
    im = Image.composite(Image.new("RGB", sz, (255, 240, 225)), im, hl.point(lambda v: int(v * 0.16)))
    # hair
    hair_m = _mask(sz, lambda d: d.ellipse(box(0.235, 0.085, 0.765, 0.43)), 2 * S)
    fore = _mask(sz, lambda d: d.ellipse(box(0.30, 0.215, 0.70, 0.60)), 3 * S)
    if female:  # centre parting: hair frames the forehead, skin visible between
        fore = _mask(sz, lambda d: d.ellipse(box(0.31, 0.23, 0.69, 0.60)), 3 * S)
    hair_m = ImageChops.subtract(hair_m, fore)
    streak = cv2.resize(rng.normal(0, 1, (6, W // 4)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    hl_img = _shaded(sz, hair, (0.35, 0.1), 0.9)
    arr = np.asarray(hl_img, np.float32) * (1 + 0.06 * streak[..., None])
    im = Image.composite(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), im, hair_m.filter(ImageFilter.GaussianBlur(S)))
    if female:
        for lx in (0.185, 0.675):
            put(hair, lambda d, lx=lx: d.ellipse(box(lx, 0.30, lx + 0.14, 0.88)), 3, (0.4, 0.2), 0.5)
        # re-draw face edge over the side locks
        put(skin, head, 3, (0.38, 0.30), 0.55) if False else None
    # key light from the upper left across the whole subject
    lt = (1.07 - 0.20 * (xx / W) - 0.05 * (yy / H))[..., None]
    im = Image.fromarray(np.clip(np.asarray(im, np.float32) * lt, 0, 255).astype(np.uint8))
    # features
    d = ImageDraw.Draw(im, "RGBA")
    ey = 0.385
    for cx in (0.405, 0.595):
        d.ellipse(box(cx - 0.052, ey - 0.020, cx + 0.052, ey + 0.020), fill=(238, 232, 226))
        d.ellipse(box(cx - 0.024, ey - 0.024, cx + 0.024, ey + 0.024), fill=(58, 38, 26))
        d.ellipse(box(cx - 0.012, ey - 0.012, cx + 0.012, ey + 0.012), fill=(10, 8, 8))
        d.ellipse(box(cx - 0.014 + 0.008, ey - 0.016, cx - 0.004 + 0.008, ey - 0.006), fill=(255, 255, 255, 200))
        d.arc(box(cx - 0.056, ey - 0.032, cx + 0.056, ey + 0.026), 195, 345, fill=(60, 35, 28, 230), width=2 * S)
        d.arc(box(cx - 0.050, ey - 0.014, cx + 0.050, ey + 0.036), 20, 160, fill=(120, 80, 70, 90), width=S)
        d.arc(box(cx - 0.066, ey - 0.078, cx + 0.066, ey - 0.020), 200, 340, fill=tuple(hair) + (235,), width=4 * S)
    # nose
    d.arc(box(0.455, 0.42, 0.545, 0.53), 20, 160, fill=(110, 60, 45, 150), width=2 * S)
    d.line([0.468 * W, 0.40 * H, 0.462 * W, 0.50 * H], fill=(120, 70, 55, 55), width=3 * S)
    d.ellipse(box(0.468, 0.505, 0.485, 0.518), fill=(70, 35, 28, 150))
    d.ellipse(box(0.515, 0.505, 0.532, 0.518), fill=(70, 35, 28, 150))
    # mouth
    lip = (168, 78, 78) if female else (150, 85, 78)
    d.ellipse(box(0.43, 0.572, 0.57, 0.612), fill=lip + (255,))
    d.ellipse(box(0.45, 0.560, 0.55, 0.585), fill=lip + (255,))
    d.line([0.43 * W, 0.587 * H, 0.57 * W, 0.587 * H], fill=(70, 30, 30, 200), width=S)
    if not female and ident["seed"] % 3 == 0:  # moustache
        d.pieslice(box(0.40, 0.53, 0.60, 0.60), 190, 350, fill=tuple(hair) + (230,))
    # fine film grain + gentle softness, then downsample
    im = im.filter(ImageFilter.GaussianBlur(1.1))
    a = np.asarray(im, np.float32) + rng.normal(0, 3.0, (H, W, 1)).astype(np.float32)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return im.resize((w, h), Image.LANCZOS)


def _seal(size: int, color=(40, 50, 110)) -> Image.Image:
    """Generic round seal placeholder (NOT any national emblem)."""
    S = 4
    n = size * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n / 2
    col = tuple(color) + (255,)
    d.ellipse([2, 2, n - 3, n - 3], outline=col, width=S * 2)
    d.ellipse([S * 6, S * 6, n - S * 6 - 1, n - S * 6 - 1], outline=col, width=S)
    for k in range(36):
        a = 2 * np.pi * k / 36
        r0, r1 = n / 2 - S * 11, n / 2 - S * 8
        d.line([c + r0 * np.cos(a), c + r0 * np.sin(a), c + r1 * np.cos(a), c + r1 * np.sin(a)], fill=col, width=S)
    for k in range(8):
        a = 2 * np.pi * k / 8
        px, py = c + n * 0.20 * np.cos(a), c + n * 0.20 * np.sin(a)
        r = n * 0.10
        d.ellipse([px - r, py - r * 0.55, px + r, py + r * 0.55], outline=col, width=S)
    d.ellipse([c - n * 0.11, c - n * 0.11, c + n * 0.11, c + n * 0.11], fill=col)
    d.ellipse([c - n * 0.06, c - n * 0.06, c + n * 0.06, c + n * 0.06], fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.LANCZOS)


def _paste_rgba(im: Image.Image, patch: Image.Image, xy) -> None:
    im.paste(patch, xy, patch)


def _text(d, xy, s, font, fill=INK, anchor="la"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)
    return d.textbbox(xy, s, font=font, anchor=anchor)


def _runs(d, xy, runs, size: int, fill=INK, anchor="l"):
    """Draw mixed Devanagari/Latin runs [(text, dev, bold), ...] on one baseline.

    Returns (bbox of everything, [bbox per run]); anchor "l" or "m" (centre) or "r".
    """
    fonts = [_font(b, size, dv) for _, dv, b in runs]
    total = sum(f.getlength(t) for (t, _, _), f in zip(runs, fonts, strict=True))
    x, y = xy
    x -= {"l": 0, "m": total / 2, "r": total}[anchor]
    boxes = []
    for (t, _, _), f in zip(runs, fonts, strict=True):
        d.text((x, y), t, font=f, fill=fill, anchor="ls")
        boxes.append([int(v) for v in d.textbbox((x, y), t, font=f, anchor="ls")])
        x += f.getlength(t)
    full = [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]
    return full, boxes


def _groups(d, x, y, digits, font, fill=INK) -> tuple[list, list[list[int]]]:
    """Draw digits in groups of 4 at baseline y; return (full bbox, per-group bboxes)."""
    text = _fmt(digits, "spaced")
    d.text((x, y), text, font=font, fill=fill, anchor="ls")
    parts = []
    for i in range(0, len(digits), 4):
        pre = _fmt(digits[:i], "spaced") + (" " if i else "")
        gx = x + font.getlength(pre)
        parts.append(
            [int(v) for v in d.textbbox((gx, y), digits[i : i + 4], font=font, anchor="ls")]
        )
    full = [
        min(p[0] for p in parts),
        min(p[1] for p in parts),
        max(p[2] for p in parts),
        max(p[3] for p in parts),
    ]
    return full, parts


def _ann(typ, bbox, parts=None, masked=None) -> dict:
    a = {"type": typ, "bbox_px": [int(v) for v in bbox]}
    if parts is not None:
        a["parts_px"] = parts
    a["value_masked"] = masked
    return a


def _watermark(d: ImageDraw.ImageDraw, w: int, y: int, size: int) -> None:
    d.text((w // 2, y), WATERMARK, font=_font(True, size), fill=RED, anchor="mt")


def _wm_band(d: ImageDraw.ImageDraw) -> None:
    """Small tinted band along the bottom edge (clear of every annotated region)."""
    d.rectangle([0, CARD_H - 34, CARD_W, CARD_H], fill=(252, 226, 226))
    d.line([0, CARD_H - 34, CARD_W, CARD_H - 34], fill=RED, width=3)
    d.text((CARD_W // 2, CARD_H - 15), WATERMARK, font=_font(True, 22), fill=RED, anchor="mm")


def _fit(text: str, bold: bool, size: int, max_w: int, dev: bool = False) -> ImageFont.FreeTypeFont:
    while size > 14 and _font(bold, size, dev).getlength(text) > max_w:
        size -= 2
    return _font(bold, size, dev)


def _wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    out: list[str] = []
    cur = ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if f.getlength(t) > max_w and cur:
            out.append(cur)
            cur = word
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def _qr(payload: str, target: int) -> np.ndarray:
    qr = cv2.QRCodeEncoder.create().encode(payload)
    n = qr.shape[0]
    k = max(1, round(target / n))
    return cv2.resize(qr, (n * k, n * k), interpolation=cv2.INTER_NEAREST)


def _payload(ident: dict) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><PrintLetterBarcodeData '
        f'uid="{ident["aadhaar"]}" name="{ident["name"]}" gender="{"F" if ident["female"] else "M"}" '
        f'yob="{ident["dob"].year}" pc="{ident["pin"]}" dist="{ident["city"]}" '
        f'state="{ident["state"]}"/>'
    )


def _header_gradient(h: int, strength: float = 1.0) -> Image.Image:
    """Saffron -> white -> green horizontal band."""
    x = np.linspace(0, 1, CARD_W, dtype=np.float32)[None, :, None]
    saf = np.array([255, 153, 51], np.float32)
    grn = np.array([40, 150, 60], np.float32)
    wht = np.array([255, 255, 255], np.float32)
    t_l = np.clip(x / 0.42, 0, 1)
    t_r = np.clip((x - 0.58) / 0.42, 0, 1)
    row = saf * (1 - t_l) + wht * t_l
    row = row * (1 - t_r) + grn * t_r
    row = 255 - (255 - row) * 0.72 * strength
    vert = np.linspace(1.0, 0.94, h, dtype=np.float32)[:, None, None]
    arr = np.broadcast_to(row, (h, CARD_W, 3)) * vert
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _finish(im: Image.Image, rng: np.random.Generator, seed_tint=0) -> np.ndarray:
    """Paper grain, slight print softness, rounded corners with a thin edge."""
    a = np.asarray(im, np.float32)
    low = cv2.resize(rng.normal(0, 1, (8, 12)).astype(np.float32), (CARD_W, CARD_H), interpolation=cv2.INTER_CUBIC)
    fine = rng.normal(0, 1, (CARD_H, CARD_W)).astype(np.float32)
    a = a + (1.4 * low + 1.6 * fine)[..., None]
    a = cv2.GaussianBlur(np.clip(a, 0, 255), (0, 0), 0.4)
    card = Image.fromarray(a.astype(np.uint8))
    m = Image.new("L", (CARD_W * 3, CARD_H * 3), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, CARD_W * 3 - 1, CARD_H * 3 - 1], radius=26 * 3, fill=255)
    m = m.resize((CARD_W, CARD_H), Image.LANCZOS)
    out = Image.composite(card, Image.new("RGB", (CARD_W, CARD_H), (255, 255, 255)), m)
    ImageDraw.Draw(out).rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=26, outline=(178, 178, 172), width=2)
    return np.asarray(out)


def _footer_rule(d, y):
    d.line([30, y, CARD_W - 30, y], fill=(200, 40, 40), width=3)


# --------------------------------------------------------------------------- card renderers
def _aadhaar_front(ident: dict, rng: np.random.Generator) -> tuple[np.ndarray, list]:
    im = Image.new("RGB", (CARD_W, CARD_H), (253, 253, 251))
    im.paste(_header_gradient(104), (0, 0))
    d = ImageDraw.Draw(im)
    ann = []
    _paste_rgba(im, _seal(70, (40, 50, 110)), (30, 17))
    _text(d, (CARD_W // 2, 14), "भारत सरकार", _font(True, 38, True), anchor="mt")
    _text(d, (CARD_W // 2, 62), "Government of India", _font(True, 28), anchor="mt")
    d.line([0, 104, CARD_W, 104], fill=(215, 215, 210), width=2)
    # photo with thin frame
    px0, py0, pw, ph = 40, 128, 210, 250
    im.paste(_avatar(pw, ph, ident, rng), (px0, py0))
    d.rectangle([px0 - 1, py0 - 1, px0 + pw, py0 + ph], outline=(150, 150, 150), width=1)
    ann.append(_ann("FACE", [px0, py0, px0 + pw, py0 + ph]))
    x, wmax = 282, 490
    _text(d, (x, 126), _translit(ident["name"]), _fit(_translit(ident["name"]), True, 34, wmax, True))
    ann.append(
        _ann("NAME", _text(d, (x, 176), ident["name"], _fit(ident["name"], True, 36, wmax)))
    )
    if ident["seed"] % 3 == 0:
        runs = [("जन्म वर्ष / ", True, False), ("Year of Birth: ", False, False)]
        val = str(ident["dob"].year)
    else:
        runs = [("जन्म तिथि / ", True, False), ("DOB: ", False, False)]
        val = ident["dob"].strftime("%d/%m/%Y")
    _, bx = _runs(d, (x, 262), runs + [(val, False, False)], 30)
    ann.append(_ann("DOB", bx[-1]))
    g = ("महिला / ", "Female") if ident["female"] else ("पुरुष / ", "Male")
    _runs(d, (x, 312), [(g[0], True, False), (g[1], False, False)], 30)
    # QR on the right
    qr = _qr(_payload(ident), 170)
    qh = qr.shape[0]
    qx, qy = CARD_W - 40 - qh, 128
    d.rectangle([qx - 8, qy - 8, qx + qh + 8, qy + qh + 8], fill=(255, 255, 255))
    im.paste(Image.fromarray(qr).convert("RGB"), (qx, qy))
    ann.append(_ann("QR", [qx, qy, qx + qh, qy + qh]))
    # number
    num = ident["aadhaar"]
    fnum = _font(True, 84)
    nx = (CARD_W - fnum.getlength(_fmt(num, "spaced"))) / 2
    full, parts = _groups(d, nx, 478, num, fnum)
    ann.append(_ann("AADHAAR", full, parts, _masked(num)))
    vid = ident["vid"]
    if vid:
        fv = _font(False, 30)
        txt = "VID : " + _fmt(vid, "spaced")
        vx = (CARD_W - fv.getlength(txt)) / 2
        d.text((vx, 524), "VID : ", font=fv, fill=INK, anchor="ls")
        full, parts = _groups(d, vx + fv.getlength("VID : "), 524, vid, fv)
        ann.append(_ann("VID", full, parts, _masked(vid)))
    _footer_rule(d, 546)
    foot = "मेरा आधार, मेरी पहचान" if ident["seed"] % 2 else "आधार – आम आदमी का अधिकार"
    _text(d, (CARD_W // 2, 556), foot, _font(True, 26, True), (200, 30, 30), anchor="mt")
    _wm_band(d)
    return _finish(im, rng), ann


def _aadhaar_back(ident: dict, rng: np.random.Generator) -> tuple[np.ndarray, list]:
    im = Image.new("RGB", (CARD_W, CARD_H), (253, 253, 251))
    im.paste(_header_gradient(96, 0.8), (0, 0))
    d = ImageDraw.Draw(im)
    ann = []
    _paste_rgba(im, _seal(64, (40, 50, 110)), (30, 16))
    _text(d, (CARD_W // 2, 12), "भारतीय विशिष्ट पहचान प्राधिकरण", _font(True, 32, True), anchor="mt")
    _text(d, (CARD_W // 2, 58), "Unique Identification Authority of India", _font(True, 28), anchor="mt")
    d.line([0, 96, CARD_W, 96], fill=(215, 215, 210), width=2)
    _runs(d, (40, 140), [("पता: / ", True, True), ("Address:", False, True)], 28)
    fh, fe = _font(False, 27, True), _font(False, 27)
    hin = [
        f"सी/ओ: {_translit(ident['father'])}",
        _translit(ident["street"]),
        f"{_translit(ident['city'])}, {_translit(ident['state'])} - {ident['pin']}",
    ]
    hl: list[str] = []
    for ln in hin:
        hl += _wrap(ln, fh, 600)
    y = 156
    for ln in hl[:3]:
        d.text((40, y), ln, font=fh, fill=INK)
        if ident["pin"] in ln:
            pre = fh.getlength(ln.split(ident["pin"])[0])
            ann.append(_ann("PIN", d.textbbox((40 + pre, y), ident["pin"], font=fh)))
        y += 40
    lines = [ident["co"], ident["street"], f"{ident['city']}, {ident['state']} -"]
    el: list[str] = []
    for ln in lines:
        el += _wrap(ln, fe, 600)
    el = el[:4]
    y += 10
    for i, ln in enumerate(el):
        d.text((40, y), ln, font=fe, fill=INK)
        if i == len(el) - 1:
            pre = fe.getlength(ln + " ")
            d.text((40 + pre, y), ident["pin"], font=fe, fill=INK)
            ann.append(_ann("PIN", d.textbbox((40 + pre, y), ident["pin"], font=fe)))
        y += 36
    qr = _qr(_payload(ident), 260)
    qh = qr.shape[0]
    qx, qy = CARD_W - 40 - qh, 124
    d.rectangle([qx - 10, qy - 10, qx + qh + 10, qy + qh + 10], fill=(255, 255, 255))
    im.paste(Image.fromarray(qr).convert("RGB"), (qx, qy))
    ann.append(_ann("QR", [qx, qy, qx + qh, qy + qh]))
    num = ident["aadhaar"]
    fnum = _font(True, 80)
    nx = (CARD_W - fnum.getlength(_fmt(num, "spaced"))) / 2
    full, parts = _groups(d, nx, 512, num, fnum)
    ann.append(_ann("AADHAAR", full, parts, _masked(num)))
    _footer_rule(d, 538)
    _text(d, (CARD_W // 2, 552), "help@example.invalid   |   www.example.invalid", _font(False, 25), anchor="mt")
    _wm_band(d)
    return _finish(im, rng), ann


def _guilloche(rng: np.random.Generator) -> Image.Image:
    """Cream-to-blue security-paper background with fine sine-wave line work."""
    yy, xx = np.mgrid[0:CARD_H, 0:CARD_W].astype(np.float32)
    t = np.clip((xx / CARD_W * 0.7 + yy / CARD_H * 0.5), 0, 1)[..., None]
    cream = np.array([244, 240, 224], np.float32)
    blue = np.array([196, 222, 244], np.float32)
    bg = cream * (1 - t) + blue * t
    lm = np.zeros((CARD_H, CARD_W), np.uint8)
    xs = np.arange(0, CARD_W + 4, 3, dtype=np.float32)
    ph = float(rng.uniform(0, 6))
    for i in range(46):
        y0 = i * 15.0 - 20
        ys = y0 + 16 * np.sin(xs * 0.018 + i * 0.22 + ph) + 9 * np.sin(xs * 0.047 - i * 0.5)
        cv2.polylines(lm, [np.stack([xs, ys], 1).astype(np.int32)], False, 255, 1, cv2.LINE_AA)
    ys2 = np.arange(0, CARD_H + 4, 3, dtype=np.float32)
    for i in range(22):
        x0 = i * 50.0
        xs2 = x0 + 12 * np.sin(ys2 * 0.03 + i * 0.4) + 7 * np.sin(ys2 * 0.07 + i)
        cv2.polylines(lm, [np.stack([xs2, ys2], 1).astype(np.int32)], False, 255, 1, cv2.LINE_AA)
    for r in range(30, 300, 9):  # rosette rings, lower right
        cv2.circle(lm, (820, 430), r, 255, 1, cv2.LINE_AA)
    lm = cv2.GaussianBlur(lm, (0, 0), 0.5).astype(np.float32) / 255.0
    bg = bg * (1 - 0.075 * lm[..., None]) - 5 * lm[..., None]
    return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))


def _signature(d: ImageDraw.ImageDraw, box, rng: np.random.Generator) -> None:
    """Scribbled synthetic signature built from cubic beziers."""
    x0, y0, x1, y1 = box
    ink = (28, 38, 110)
    n = int(rng.integers(5, 8))
    dx = (x1 - x0) / n
    hgt = (y1 - y0) * 0.9
    path: list[tuple[float, float]] = []
    for k in range(n):
        a = (x0 + dx * k, y0 + (y1 - y0) * float(rng.uniform(0.45, 0.8)))
        b = (a[0] + dx, y0 + (y1 - y0) * float(rng.uniform(0.45, 0.8)))
        c1 = (a[0] + dx * float(rng.uniform(1.4, 2.2)), a[1] - hgt * float(rng.uniform(0.6, 1.3)))
        c2 = (b[0] - dx * float(rng.uniform(0.2, 1.0)), b[1] + hgt * float(rng.uniform(0.2, 0.7)))
        for t in np.linspace(0, 1, 28):
            u = 1 - t
            path.append(
                (
                    u**3 * a[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * b[0],
                    u**3 * a[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * b[1],
                )
            )
    path = [(min(max(x, x0 - 6), x1 + 12), min(max(y, y0 - 14), y1 + 8)) for x, y in path]
    d.line(path, fill=ink, width=2, joint="curve")
    d.line([(x0 + 14, y1 + 2), ((x0 + x1) / 2, y1 - 4), (x1 + 8, y1 - 2)], fill=ink, width=2)


def _hologram(size: int) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    ph = (xx + yy) / size * 5.5
    r = 190 + 60 * np.cos(ph)
    g = 190 + 60 * np.cos(ph + 2.1)
    b = 200 + 55 * np.cos(ph + 4.2)
    hl = np.exp(-(((xx - size * 0.3) ** 2 + (yy - size * 0.3) ** 2) / (size * 0.25) ** 2))
    arr = np.stack([r, g, b], -1) + 50 * hl[..., None]
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    ImageDraw.Draw(im).rectangle([0, 0, size - 1, size - 1], outline=(150, 150, 165), width=2)
    return im


def _pan(ident: dict, rng: np.random.Generator) -> tuple[np.ndarray, list]:
    im = _guilloche(rng)
    d = ImageDraw.Draw(im)
    ann = []
    _paste_rgba(im, _seal(64, (35, 60, 120)), ((CARD_W - 64) // 2, 14))
    hd, he = _font(True, 30, True), _font(True, 21)
    _text(d, (40, 12), "आयकर विभाग", hd, (25, 40, 110))
    _text(d, (40, 56), "INCOME TAX DEPARTMENT", he, (25, 40, 110))
    _text(d, (CARD_W - 40, 12), "भारत सरकार", hd, (25, 40, 110), anchor="ra")
    _text(d, (CARD_W - 40, 56), "GOVT. OF INDIA", he, (25, 40, 110), anchor="ra")
    d.line([30, 92, CARD_W - 30, 92], fill=(60, 80, 140), width=2)
    px0, py0, pw, ph = 40, 150, 200, 240
    x = 282
    _text(d, (x, 104), "स्थायी लेखा संख्या कार्ड", _font(True, 24, True), (25, 40, 110))
    _text(d, (x, 138), "Permanent Account Number Card", _font(False, 22), (25, 40, 110))
    bb = _text(d, (x, 172), ident["pan"], _font(True, 64))
    ann.append(_ann("PAN", bb, None, "XXXXX" + ident["pan"][5:9] + "X"))
    grey = (70, 74, 90)
    _runs(d, (x, 278), [("नाम / ", True, False), ("Name", False, False)], 19, grey)
    ann.append(
        _ann("NAME", _text(d, (x, 286), ident["name"].upper(), _fit(ident["name"].upper(), True, 34, 560)))
    )
    _runs(d, (x, 356), [("पिता का नाम / ", True, False), ("Father's Name", False, False)], 19, grey)
    _text(d, (x, 364), ident["father"].upper(), _fit(ident["father"].upper(), True, 34, 560))
    _runs(d, (x, 434), [("जन्म की तारीख / ", True, False), ("Date of Birth", False, False)], 19, grey)
    ann.append(_ann("DOB", _text(d, (x, 442), ident["dob"].strftime("%d/%m/%Y"), _font(True, 34))))
    im.paste(_avatar(pw, ph, ident, rng), (px0, py0))
    d.rectangle([px0 - 1, py0 - 1, px0 + pw, py0 + ph], outline=(120, 125, 140), width=1)
    ann.append(_ann("FACE", [px0, py0, px0 + pw, py0 + ph]))
    _signature(d, (px0 + 10, py0 + ph + 22, px0 + pw - 10, py0 + ph + 70), rng)
    _runs(d, (px0 + pw // 2, py0 + ph + 98), [("हस्ताक्षर / ", True, False), ("Signature", False, False)], 17, grey, "m")
    im.paste(_hologram(74), (CARD_W - 40 - 74, 442))
    _wm_band(d)
    return _finish(im, rng), ann


_CARD_FUNCS = {"aadhaar_front": _aadhaar_front, "aadhaar_back": _aadhaar_back, "pan": _pan}


def _kyc_sheet(ident: dict, seed: int) -> tuple[np.ndarray, list]:
    page = Image.new("RGB", (SHEET_W, SHEET_H), (255, 255, 255))
    d = ImageDraw.Draw(page)
    ann: list[dict] = []
    _text(d, (SHEET_W // 2, 110), "Self-attested KYC copy", _font(True, 64), anchor="mt")
    _text(
        d,
        (SHEET_W // 2, 195),
        "Attach photocopies of identity documents below",
        _font(False, 30),
        (90, 90, 90),
        anchor="mt",
    )
    s = 674 / CARD_W
    slots = {"aadhaar_front": (102, 300), "aadhaar_back": (878, 300), "pan": (102, 800)}
    rng = np.random.default_rng(seed + 1)
    for kind, (ox, oy) in slots.items():
        card, cann = _CARD_FUNCS[kind](ident, rng)
        small = cv2.resize(card, (674, round(CARD_H * s)), interpolation=cv2.INTER_AREA)
        page.paste(Image.fromarray(small), (ox, oy))
        for a in cann:
            a = copy.deepcopy(a)
            a["bbox_px"] = [
                round(a["bbox_px"][0] * s + ox),
                round(a["bbox_px"][1] * s + oy),
                round(a["bbox_px"][2] * s + ox),
                round(a["bbox_px"][3] * s + oy),
            ]
            if "parts_px" in a:
                a["parts_px"] = [
                    [
                        round(p[0] * s + ox),
                        round(p[1] * s + oy),
                        round(p[2] * s + ox),
                        round(p[3] * s + oy),
                    ]
                    for p in a["parts_px"]
                ]
            ann.append(a)
    f = _font(False, 38)
    _text(d, (102, 1400), f"Name: {ident['name']}", f)
    _text(d, (102, 1560), "Signature", f)
    d.line([102, 1545, 760, 1545], fill=INK, width=3)
    # thumb impression box ~1.6 x 1.5 in at 200 dpi (deed-like margins around the print)
    bx0, by0, bw, bh = 1180, 1300, 320, 300
    d.rectangle([bx0, by0, bx0 + bw, by0 + bh], outline=INK, width=3)
    _text(d, (bx0 + bw // 2, by0 + bh + 24), "Thumb impression", _font(False, 28), anchor="mt")
    frng = np.random.default_rng(seed + 2)
    style = sample_fp_style(frng, "train")
    style["blur_sigma"] = min(style["blur_sigma"], 0.8)
    style["partial"] = 0.0
    fp = fingerprint_gen.generate(seed + 3, style)
    sc = min(1.0, (bw - 80) / fp.shape[1], (bh - 80) / fp.shape[0])
    fp = cv2.resize(
        fp,
        (max(1, int(fp.shape[1] * sc)), max(1, int(fp.shape[0] * sc))),
        interpolation=cv2.INTER_AREA,
    )
    alpha = fp[..., 3:4].astype(np.float32) / 255.0
    ink = (fp[..., :3].astype(np.float32) * alpha + 255.0 * (1 - alpha)).astype(np.uint8)
    page.paste(
        Image.fromarray(ink), (bx0 + (bw - ink.shape[1]) // 2, by0 + (bh - ink.shape[0]) // 2)
    )
    px0 = bx0 + (bw - ink.shape[1]) // 2
    py0 = by0 + (bh - ink.shape[0]) // 2
    ann.append(_ann("FINGERPRINT", [px0, py0, px0 + ink.shape[1], py0 + ink.shape[0]]))
    del fp, ink
    _watermark(d, SHEET_W, SHEET_H - 90, 34)
    return np.asarray(page), ann


# --------------------------------------------------------------------------- public API
def render_id(seed: int, kind: str) -> tuple[np.ndarray, dict]:
    """Clean, flat, axis-aligned scan. Returns (RGB uint8 HxWx3, gt)."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    ident = _identity(seed)
    if kind == "kyc_sheet":
        img, ann = _kyc_sheet(ident, seed)
        dpi = SHEET_DPI
    else:
        rng = np.random.default_rng(seed * 31 + KINDS.index(kind))
        img, ann = _CARD_FUNCS[kind](ident, rng)
        dpi = CARD_DPI
    h, w = img.shape[:2]
    gt = {
        "kind": kind,
        "seed": seed,
        "dpi": dpi,
        "width": w,
        "height": h,
        "synthetic": True,
        "annotations": ann,
    }
    return np.ascontiguousarray(img), gt


def _bg_texture(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    base = np.array(
        rng.choice([[120, 88, 60], [150, 150, 148], [70, 90, 80], [176, 140, 100]]), np.float32
    )
    low = cv2.resize(
        rng.normal(0, 1, (6, 8)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC
    )
    grain = cv2.resize(
        rng.normal(0, 1, (h // 2, 12)).astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR
    )
    fine = rng.normal(0, 1, (h, w)).astype(np.float32)
    t = 14 * low + 7 * grain + 3 * fine
    return base[None, None, :] + t[..., None]


def _xform_box(b, m):
    pts = np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], np.float32)[None]
    o = cv2.perspectiveTransform(pts, m)[0]
    return o


def phone_photo(
    rgb: np.ndarray, gt: dict, seed: int, *, blur: float = 0.0
) -> tuple[np.ndarray, dict]:
    """Simulate a phone photo of the document (see module docs); returns (photo, gt')."""
    rng = np.random.default_rng(seed * 101 + 7)
    h, w = rgb.shape[:2]
    f = float(rng.uniform(0.78, 0.88))
    W, H = int(round(w / f)), int(round(h / f))
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    # place centred, rotate, jitter corners
    ang = np.deg2rad(rng.uniform(-8, 8))
    c, s = np.cos(ang), np.sin(ang)
    ctr = np.array([w / 2, h / 2], np.float32)
    rot = np.array([[c, -s], [s, c]], np.float32)
    quad = (src - ctr) @ rot.T + np.array([W / 2, H / 2], np.float32)
    quad += rng.uniform(-0.06, 0.06, (4, 2)).astype(np.float32) * np.array([w, h], np.float32)
    quad += rng.uniform(-0.02, 0.02, 2).astype(np.float32) * np.array([W, H], np.float32)
    # keep whole document inside the frame
    lo, hi = quad.min(0), quad.max(0)
    mx, my = 0.01 * W, 0.01 * H
    k = min(
        1.0,
        (W / 2 - mx) / max(abs(lo[0] - W / 2), abs(hi[0] - W / 2), 1),
        (H / 2 - my) / max(abs(lo[1] - H / 2), abs(hi[1] - H / 2), 1),
    )
    quad = (quad - np.array([W / 2, H / 2], np.float32)) * k + np.array([W / 2, H / 2], np.float32)
    quad = quad.astype(np.float32)
    m = cv2.getPerspectiveTransform(src, quad)

    bg = _bg_texture(H, W, rng)
    doc = cv2.warpPerspective(rgb, m, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0)).astype(
        np.float32
    )
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (W, H), flags=cv2.INTER_LINEAR)
    mask_f = (mask.astype(np.float32) / 255.0)[..., None]
    # cast shadow on the table
    sh = cv2.GaussianBlur(mask, (0, 0), max(W, H) * 0.012)
    sh = np.roll(sh, (int(H * 0.012), int(W * 0.012)), axis=(0, 1)).astype(np.float32) / 255.0
    bg *= (1 - 0.45 * sh)[..., None]
    out = doc * mask_f + bg * (1 - mask_f)

    # soft lighting gradient
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    th = rng.uniform(0, 2 * np.pi)
    g = (xx / W - 0.5) * np.cos(th) + (yy / H - 0.5) * np.sin(th)
    out *= (0.92 + rng.uniform(0.12, 0.3) * g)[..., None] + rng.uniform(-0.03, 0.03)

    # transformed annotations
    gt2 = copy.deepcopy(gt)
    gt2["width"], gt2["height"] = W, H
    gt2["quad_px"] = [[round(float(x), 1), round(float(y), 1)] for x, y in quad]

    def tb(b):
        o = _xform_box(b, m)
        x0, y0 = np.floor(o.min(0)).astype(int)
        x1, y1 = np.ceil(o.max(0)).astype(int)
        return [int(max(0, x0)), int(max(0, y0)), int(min(W, x1)), int(min(H, y1))]

    for a in gt2["annotations"]:
        a["bbox_px"] = tb(a["bbox_px"])
        if "parts_px" in a:
            a["parts_px"] = [tb(p) for p in a["parts_px"]]

    # one specular glare blob, away from number-bearing regions
    keep = [
        a["bbox_px"] for a in gt2["annotations"] if a["type"] in ("AADHAAR", "VID", "PAN", "QR")
    ]
    sig = 0.07 * min(w, h)
    best, best_pen = None, None
    for _ in range(60):
        u = rng.uniform(0.1, 0.9, 2)
        p = (quad[0] + (quad[1] - quad[0]) * u[0]) * (1 - u[1]) + (
            quad[3] + (quad[2] - quad[3]) * u[0]
        ) * u[1]
        pen = sum(
            max(0.0, min(p[0] + 2.5 * sig, b[2]) - max(p[0] - 2.5 * sig, b[0]))
            * max(0.0, min(p[1] + 2.5 * sig, b[3]) - max(p[1] - 2.5 * sig, b[1]))
            for b in keep
        )
        if best_pen is None or pen < best_pen:
            best, best_pen = p, pen
        if pen == 0:
            break
    d2 = ((xx - best[0]) / (sig * 1.6)) ** 2 + ((yy - best[1]) / sig) ** 2
    glare = np.exp(-d2) * rng.uniform(0.55, 0.8) * mask_f[..., 0]
    out = out * (1 - glare[..., None]) + 255.0 * glare[..., None]

    out += rng.normal(0, 3.0, out.shape).astype(np.float32)
    out = np.clip(out, 0, 255).astype(np.uint8)
    if blur > 0:
        out = cv2.GaussianBlur(out, (0, 0), blur)
    return np.ascontiguousarray(out), gt2


def to_jpeg_with_exif(rgb: np.ndarray, quality: int = 92) -> bytes:
    """JPEG bytes with fake EXIF (Make/Model/DateTimeOriginal/Software + GPS at 0N 0E)."""
    exif = Image.Exif()
    exif[0x010F] = "SynthPhone"
    exif[0x0110] = "SP-1 Fake"
    exif[0x0131] = "SynthCam 1.0"
    exif[0x0132] = "2026:01:15 10:30:00"
    exif.get_ifd(0x8769)[0x9003] = "2026:01:15 10:30:00"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (0.0, 0.0, 0.0), "E", (0.0, 0.0, 0.0)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, exif=exif)
    return buf.getvalue()
