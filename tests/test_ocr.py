"""OCR layer: text-layer path, Tesseract path, cache, token normaliser."""

from __future__ import annotations

import numpy as np
import pymupdf

from backend.app.core import ocr
from backend.app.core.ocr import get_page_text, normalize_token, ocr_image


def test_normalize_malayalam_digits_and_punct():
    assert normalize_token("൨൩൪൫:") == "2345"
    assert normalize_token(",1234.") == "1234"
    assert normalize_token("(൦൧)") == "01"


def test_normalize_confusables_only_in_digit_tokens():
    assert normalize_token("2O45") == "2045"
    assert normalize_token("l234") == "1234"
    assert normalize_token("|234") == "1234"
    assert normalize_token("S6B8") == "5688"
    assert normalize_token("BOSS") == "BOSS"  # no real digits: left alone
    assert normalize_token("Sy.") == "Sy"
    assert normalize_token("+91") == "+91"


def test_text_layer_used_for_born_digital(born_digital_deed):
    doc = pymupdf.open(born_digital_deed.path)
    pt = get_page_text(doc[0])
    assert pt.text_layer and pt.ocr_quality == 1.0
    assert pt.words and all(w.conf == 1.0 for w in pt.words)
    w, h = doc[0].rect.width, doc[0].rect.height
    assert all(0 <= b.bbox_pt[0] < b.bbox_pt[2] <= w + 1 for b in pt.words)
    assert all(0 <= b.bbox_pt[1] < b.bbox_pt[3] <= h + 1 for b in pt.words)
    assert len({x.line_id for x in pt.words}) > 3


def test_ocr_path_on_scanned_page_and_cache(scanned_deed):
    doc = pymupdf.open(scanned_deed.path)
    ocr._cache.clear()
    pt = get_page_text(doc[0])
    assert not pt.text_layer and len(pt.words) > 20
    assert 0.3 < pt.ocr_quality <= 1.0
    w, h = doc[0].rect.width, doc[0].rect.height
    assert all(-1 <= x.bbox_pt[0] and x.bbox_pt[2] <= w + 1 for x in pt.words)
    assert all(x.bbox_pt[3] <= h + 1 for x in pt.words)
    assert len(ocr._cache) == 1
    pt2 = get_page_text(doc[0])  # served from cache
    assert len(ocr._cache) == 1 and pt2 == pt and pt2 is not pt


def test_ocr_image_offset_shifts_points():
    ocr._cache.clear()
    page_doc = pymupdf.open()
    pg = page_doc.new_page(width=200, height=60)
    pg.insert_text((10, 40), "Hello 12345", fontsize=24)
    p = pg.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
    img = np.frombuffer(p.samples, np.uint8).reshape(p.height, p.width)
    a = ocr_image(img, 200)
    b = ocr_image(img, 200, offset=(5, 7))
    assert a.words and len(a.words) == len(b.words)
    assert abs(b.words[0].bbox_pt[0] - a.words[0].bbox_pt[0] - 5) < 1e-6
    assert abs(b.words[0].bbox_pt[1] - a.words[0].bbox_pt[1] - 7) < 1e-6
    assert len(ocr._cache) == 1  # offset does not split the cache
