"""Page text extraction: PDF text layer when usable, else Tesseract OCR (eng+mal).

Bboxes are PDF points, top-left origin. Renders live only in memory (never written to disk).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pymupdf
import pytesseract

from .types import PageText, Word

OCR_LANG = "eng+mal"
OCR_PSM = 11  # sparse text: best recall on scanned number fields (measured)
MIN_TEXT_LAYER_WORDS = 5
_CACHE_SIZE = 32
_cache: OrderedDict[tuple, PageText] = OrderedDict()

_ML_DIGITS = {ord("൦") + i: str(i) for i in range(10)}
# Characters Tesseract confuses with digits when they sit inside a digit token.
_CONFUSABLE = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"}
_STRIP = " \t\r\n:;,.()[]{}<>'\"`‘’“”"
_ALNUM = re.compile(r"[0-9A-Za-zഀ-ൿ]")

# Windows installs Tesseract per-machine, but its installer does not always refresh the PATH
# of an already-open terminal. Keep the normal PATH behavior and add the standard install path
# as a fallback so the local API can still use the installed OCR engine.
if not shutil.which("tesseract"):
    _windows_tesseract = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Tesseract-OCR"
        / "tesseract.exe"
    )
    if _windows_tesseract.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(_windows_tesseract)


def normalize_token(text: str) -> str:
    """Strip surrounding punctuation, map Malayalam digits to ASCII and fix O/l/I/S/B -> digit
    confusions, the latter only when the token is otherwise digits."""
    t = text.translate(_ML_DIGITS).strip(_STRIP)
    if t and all(c.isdigit() or c in _CONFUSABLE for c in t):
        real = sum(c.isdigit() for c in t)
        if real * 2 >= len(t):
            t = "".join(_CONFUSABLE.get(c, c) for c in t)
    return t


def _quality(words: list[Word]) -> float:
    confs = [w.conf for w in words if _ALNUM.search(w.text)]
    return float(sum(confs) / len(confs)) if confs else 0.0


def _text_layer(page: pymupdf.Page) -> PageText | None:
    raw = page.get_text("words")
    if sum(1 for w in raw if any(c.isalnum() for c in w[4])) < MIN_TEXT_LAYER_WORDS:
        return None
    ids: dict[tuple[int, int], int] = {}
    words = [
        Word(
            text=w[4],
            bbox_pt=(float(w[0]), float(w[1]), float(w[2]), float(w[3])),
            conf=1.0,
            line_id=ids.setdefault((w[5], w[6]), len(ids)),
        )
        for w in raw
        if w[4].strip()
    ]
    return PageText(words=words, text_layer=True, ocr_quality=1.0)


def ocr_image(
    gray: np.ndarray,
    dpi: int,
    offset: tuple[float, float] = (0, 0),
    *,
    lang: str = OCR_LANG,
    psm: int = OCR_PSM,
) -> PageText:
    """OCR a grayscale image rendered at `dpi`; `offset` (points) is the image's top-left
    position on the page. Results are cached in memory by image hash."""
    digest = hashlib.sha256(np.ascontiguousarray(gray).tobytes()).hexdigest()
    key = (digest, gray.shape, dpi, lang, psm)
    pt = _cache.get(key)
    if pt is None:
        pt = _run_tesseract(gray, dpi, lang, psm)
        _cache[key] = pt
        if len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    pt = pt.model_copy(deep=True)
    if offset != (0, 0):
        ox, oy = offset
        for w in pt.words:
            x0, y0, x1, y1 = w.bbox_pt
            w.bbox_pt = (x0 + ox, y0 + oy, x1 + ox, y1 + oy)
    return pt


def _run_tesseract(gray: np.ndarray, dpi: int, lang: str, psm: int) -> PageText:
    d = pytesseract.image_to_data(
        gray, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT
    )
    s = 72.0 / dpi
    ids: dict[tuple[int, int, int], int] = {}
    words: list[Word] = []
    for i, text in enumerate(d["text"]):
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < 0 or not text or not text.strip():
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        lid = ids.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), len(ids))
        words.append(
            Word(
                text=text.strip(),
                bbox_pt=(x * s, y * s, (x + w) * s, (y + h) * s),
                conf=min(conf / 100.0, 1.0),
                line_id=lid,
            )
        )
    if psm in (11, 12):  # sparse modes give fragmentary lines: regroup geometrically
        _regroup_lines(words)
    return PageText(words=words, text_layer=False, ocr_quality=_quality(words))


def _regroup_lines(words: list[Word]) -> None:
    """Assign one line_id to words that overlap vertically and sit close side by side."""
    parent = list(range(len(words)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(len(words)), key=lambda i: words[i].bbox_pt[0])
    for a, i in enumerate(order):
        x0, y0, x1, y1 = words[i].bbox_pt
        for j in order[a + 1 :]:
            u0, v0, u1, v1 = words[j].bbox_pt
            h = min(y1 - y0, v1 - v0)
            if u0 - x1 > 1.5 * max(y1 - y0, v1 - v0):
                break
            if h > 0 and min(y1, v1) - max(y0, v0) > 0.6 * h and u0 - x1 > -0.5 * h:
                parent[find(j)] = find(i)
    ids: dict[int, int] = {}
    for i, w in enumerate(words):
        w.line_id = ids.setdefault(find(i), len(ids))


def get_page_text(page: pymupdf.Page, dpi: int = 250) -> PageText:
    """Text-layer words if the page has a usable layer, otherwise OCR of a grayscale render."""
    pt = _text_layer(page)
    if pt is not None:
        return pt
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return ocr_image(gray, dpi, offset=(page.rect.x0, page.rect.y0))
