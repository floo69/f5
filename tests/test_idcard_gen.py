"""Tests for synth.idcard_gen (synthetic ID images). Synthetic data only."""

from __future__ import annotations

import io
import re

import cv2
import numpy as np
import pytesseract
import pytest
from PIL import Image

from backend.app.core.verhoeff import validate
from synth.idcard_gen import KINDS, phone_photo, render_id, to_jpeg_with_exif

PAN_RE = re.compile(r"[A-Z]{3}[ABCFGHLJPT][A-Z][0-9]{4}[A-Z]")


def _ocr(img: np.ndarray) -> str:
    return pytesseract.image_to_string(img, lang="eng", config="--psm 11")


def _inside(b, w, h) -> bool:
    return 0 <= b[0] < b[2] <= w and 0 <= b[1] < b[3] <= h


def test_determinism():
    for kind in KINDS:
        a, ga = render_id(5, kind)
        b, gb = render_id(5, kind)
        assert np.array_equal(a, b) and ga == gb
    assert not np.array_equal(render_id(5, "pan")[0], render_id(6, "pan")[0])
    p1, _ = phone_photo(*render_id(5, "pan"), 9)
    p2, _ = phone_photo(*render_id(5, "pan"), 9)
    assert np.array_equal(p1, p2)


def test_sizes_and_dpi():
    for kind in ("aadhaar_front", "aadhaar_back", "pan"):
        img, gt = render_id(1, kind)
        assert img.shape == (638, 1011, 3) and img.dtype == np.uint8
        assert gt["dpi"] == 300 and gt["synthetic"] is True and gt["kind"] == kind
    img, gt = render_id(1, "kyc_sheet")
    assert img.shape == (2339, 1654, 3) and gt["dpi"] == 200
    assert {a["type"] for a in gt["annotations"]} >= {"AADHAAR", "QR", "PAN", "FINGERPRINT", "FACE"}
    assert sum(a["type"] == "FINGERPRINT" for a in gt["annotations"]) == 1


def test_bboxes_inside_image():
    for kind in KINDS:
        img, gt = render_id(2, kind)
        h, w = img.shape[:2]
        for a in gt["annotations"]:
            assert _inside(a["bbox_px"], w, h), (kind, a["type"])
            for p in a.get("parts_px", []):
                assert _inside(p, w, h)
            if a["type"] in ("AADHAAR", "VID"):
                assert len(a["parts_px"]) == (3 if a["type"] == "AADHAAR" else 4)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_qr_decodes(seed):
    img, gt = render_id(seed, "aadhaar_back")
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    assert "uid=" in text and "name=" in text


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ocr_aadhaar_front(seed):
    img, gt = render_id(seed, "aadhaar_front")
    digits = re.sub(r"\D", "", _ocr(img))
    ann = next(a for a in gt["annotations"] if a["type"] == "AADHAAR")
    last4 = ann["value_masked"][-4:]
    m = [digits[i : i + 12] for i in range(len(digits) - 11) if digits[i + 8 : i + 12] == last4]
    assert any(validate(x) and x[0] in "23456789" for x in m)


@pytest.mark.parametrize("seed", [1, 3, 4])
def test_ocr_pan(seed):
    img, gt = render_id(seed, "pan")
    ann = next(a for a in gt["annotations"] if a["type"] == "PAN")
    found = PAN_RE.findall(_ocr(img).replace(" ", ""))
    assert found and found[0][5:9] == ann["value_masked"][5:9]
    assert found[0][3] == "P"


def test_watermark_present():
    for kind in KINDS:
        img, _ = render_id(4, kind)
        assert "SYNTHETIC" in _ocr(img).upper(), kind


def test_phone_photo():
    for kind in ("aadhaar_front", "aadhaar_back", "pan"):
        img, gt = render_id(3, kind)
        photo, g2 = phone_photo(img, gt, 11, blur=0.8)
        h, w = photo.shape[:2]
        assert photo.dtype == np.uint8 and (w, h) == (g2["width"], g2["height"])
        quad = np.array(g2["quad_px"])
        assert quad.shape == (4, 2) and quad.min() >= 0
        assert quad[:, 0].max() <= w and quad[:, 1].max() <= h
        area = cv2.contourArea(quad.astype(np.float32)) / (w * h)
        assert 0.5 < area < 0.85
        assert len(g2["annotations"]) == len(gt["annotations"])
        for a in g2["annotations"]:
            assert _inside(a["bbox_px"], w, h)
    # source gt untouched
    assert gt["width"] == 1011 and "quad_px" not in gt


def test_jpeg_exif():
    img, gt = render_id(3, "aadhaar_front")
    data = to_jpeg_with_exif(phone_photo(img, gt, 3)[0])
    assert data[:2] == b"\xff\xd8"
    ex = Image.open(io.BytesIO(data)).getexif()
    assert ex.get(0x010F) and ex.get(0x0110) and ex.get(0x0131)
    assert 0x8825 in ex and ex.get_ifd(0x8825).get(1) == "N"
    assert ex.get_ifd(0x8769).get(0x9003)


def test_no_full_numbers_in_gt():
    for kind in KINDS:
        _, gt = render_id(7, kind)
        blob = repr(gt)
        assert not re.search(r"\d{12}", blob.replace(" ", "")), kind
        for a in gt["annotations"]:
            if a["type"] in ("AADHAAR", "VID"):
                assert a["value_masked"].startswith("XXXX")
