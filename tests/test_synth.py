import re

import pymupdf
import pytest

from backend.app.core.verhoeff import validate
from synth.deed_gen import generate_deed

PX = 200 / 72


@pytest.fixture(scope="module")
def docs():
    out = {}
    for mode in ("born_digital", "scanned"):
        out[mode] = generate_deed(11, "train", mode, n_pages=2)
    return out


@pytest.mark.parametrize("mode", ["born_digital", "scanned"])
def test_determinism(mode, docs):
    pdf, gt, _ = docs[mode]
    pdf2, gt2, _ = generate_deed(11, "train", mode, n_pages=2)
    assert pdf == pdf2
    assert gt == gt2
    assert generate_deed(12, "train", mode, n_pages=1)[0] != pdf


@pytest.mark.parametrize("mode", ["born_digital", "scanned"])
def test_bboxes_in_bounds(mode, docs):
    _, gt, imgs = docs[mode]
    assert len(imgs) == len(gt["pages"]) == 2
    for e in gt["annotations"] + gt["hard_negatives"]:
        w, h = gt["pages"][e["page"]]["size_pt"]
        x0, y0, x1, y1 = e["bbox_pt"]
        assert 0 <= x0 < x1 <= w + 0.01 and 0 <= y0 < y1 <= h + 0.01
        for p, q in zip(e["bbox_px"], e["bbox_pt"], strict=True):
            assert abs(p - q * PX) <= 1.0


def _darkness(img, box):
    x0, y0, x1, y1 = box
    g = 255.0 - img.mean(axis=2)
    return g[y0:y1, x0:x1].mean(), g.mean()


@pytest.mark.parametrize("mode", ["born_digital", "scanned"])
def test_fingerprint_ink_inside_bbox(mode):
    # find a seed with prints; y-flip errors would put the bbox on blank paper
    n = 0
    for seed in range(20, 30):
        _, gt, imgs = generate_deed(seed, "train", mode, n_pages=1)
        for a in gt["annotations"]:
            if a["type"] == "FINGERPRINT":
                inside, page = _darkness(imgs[a["page"]], a["bbox_px"])
                assert inside > 1.5 * page, (seed, inside, page)
                n += 1
        if n >= 3:
            return
    pytest.fail("no fingerprints generated")


def test_text_layer_numbers_and_watermark():
    n_aad = n_bad = 0
    for seed in (31, 32, 33):
        pdf, gt, _ = generate_deed(seed, "train", "born_digital", n_pages=2)
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        for page in doc:
            assert "NOT A REAL DOCUMENT" in re.sub(r"\s+", " ", page.get_text())
        for a in gt["annotations"]:
            if a["type"] not in ("AADHAAR", "VID", "DECOY_NUMBER", "MASKED_AADHAAR"):
                continue
            page = doc[a["page"]]
            x0, y0, x1, y1 = a["bbox_pt"]
            digits = ""
            for wx0, wy0, wx1, wy1, word, *_ in page.get_text("words"):
                if x0 <= (wx0 + wx1) / 2 <= x1 and y0 <= (wy0 + wy1) / 2 <= y1:
                    digits += "".join(ch for ch in word if ch.isdigit() or ch in "X")
            if a["type"] == "MASKED_AADHAAR":
                assert digits.endswith(a["value_masked"][-4:])
            elif a["type"] == "DECOY_NUMBER":
                if a["subtype"] == "bad_checksum":
                    assert len(digits) == 12 and not validate(digits)
                    n_bad += 1
            else:
                assert validate(digits), a["type"]
                assert digits.endswith(a["value_masked"][-4:])
                assert len(digits) == (12 if a["type"] == "AADHAAR" else 16)
                n_aad += 1
    assert n_aad >= 3


def test_gt_has_no_full_numbers(docs):
    import json

    s = json.dumps(docs["born_digital"][1])
    assert not re.search(r"\d{12}", s)


def test_scanned_has_no_text_layer(docs):
    doc = pymupdf.open(stream=docs["scanned"][0], filetype="pdf")
    assert all(p.get_text().strip() == "" for p in doc)
