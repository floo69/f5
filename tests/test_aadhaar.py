"""Aadhaar/VID detection: unit tests on hand-built PageText + fixture integration."""

from __future__ import annotations

import pymupdf

from backend.app.core import verhoeff
from backend.app.core.aadhaar import find_numbers
from backend.app.core.ocr import get_page_text
from backend.app.core.types import PageText, Word


def _num(payload: str) -> str:
    return payload + verhoeff.compute_check_digit(payload)


A12 = _num("23456789012")  # valid 12 digits
V16 = _num("234567890123456")  # valid 16 digits
BAD12 = A12[:-1] + str((int(A12[-1]) + 1) % 10)


def _bad(n: str) -> str:
    assert not verhoeff.validate(n)
    return n


def _pt(*lines: list[str], text_layer: bool = True) -> PageText:
    words: list[Word] = []
    for li, toks in enumerate(lines):
        x = 10.0
        for t in toks:
            w = 6.0 * len(t)
            box = (x, 10 + 14 * li, x + w, 20 + 14 * li)
            words.append(Word(text=t, bbox_pt=box, conf=1.0, line_id=li))
            x += w + 4
    return PageText(words=words, text_layer=text_layer, ocr_quality=1.0)


def _types(fs):
    return sorted(f.type for f in fs)


def _groups(n: str, sizes=(4, 4, 4)) -> list[str]:
    out, i = [], 0
    for s in sizes:
        out.append(n[i : i + s])
        i += s
    return out


def test_spaced_split_tokens_joined():
    fs = find_numbers(_pt(["Aadhaar", "No.:", *_groups(A12)]), 3)
    assert len(fs) == 1
    f = fs[0]
    assert f.type == "AADHAAR" and f.page == 3 and f.redact and f.source == "textlayer"
    assert f.confidence == 1.0  # keyword nearby
    assert f.value_masked == f"XXXX XXXX {A12[-4:]}"
    # bbox spans the three groups only, not the label
    assert f.bbox_pt[0] > 10 + 6 * 7


def test_plain_and_hyphen_formats():
    assert _types(find_numbers(_pt([A12]), 0)) == ["AADHAAR"]
    assert _types(find_numbers(_pt(["-".join(_groups(A12))]), 0)) == ["AADHAAR"]
    hy = _groups(A12)
    assert _types(find_numbers(_pt([hy[0] + "-", hy[1] + "-", hy[2]]), 0)) == ["AADHAAR"]


def test_confidence_without_keyword_and_previous_line_keyword():
    assert find_numbers(_pt(["Ref", A12]), 0)[0].confidence == 0.9
    assert find_numbers(_pt(["Aadhaar", "No.:"], [A12]), 0)[0].confidence == 1.0
    assert find_numbers(_pt(["ആധാർ", "നമ്പർ:", A12]), 0)[0].confidence == 1.0


def test_decoys_rejected():
    bad = _bad(BAD12)
    assert verhoeff.validate(A12) and not verhoeff.validate(bad)
    assert find_numbers(_pt(["Ref.", "No.", *_groups(bad)]), 0) == []
    assert find_numbers(_pt(["UID:", bad]), 0) == []
    assert find_numbers(_pt(["Phone:", "+91", "98470", "12345"]), 0) == []
    assert find_numbers(_pt(["Phone:", "+91-98470-12345"]), 0) == []
    assert find_numbers(_pt(["Phone:", "09847012345"]), 0) == []
    assert find_numbers(_pt(["Sy.", "No.", "123/4A", "dated", "12/05/2019", "12-05-2019"]), 0) == []


def test_plus_prefixed_valid_number_not_flagged():
    # "+91" + 10 digits is a phone; even if the 12 digits happened to pass Verhoeff.
    assert find_numbers(_pt(["+" + A12]), 0) == []


def test_masked_recognised_not_redacted():
    for sep in (" ", "-"):
        toks = sep.join(["XXXX", "XXXX", A12[-4:]])
        fs = find_numbers(_pt(["Aadhaar:", *toks.split(" ")]), 0)
        assert _types(fs) == ["MASKED_AADHAAR"], toks
        assert fs[0].redact is False and fs[0].value_masked == f"XXXX XXXX {A12[-4:]}"
    fs = find_numbers(_pt(["XXxX", "XXXX", A12[-4:]]), 0)  # OCR variant
    assert _types(fs) == ["MASKED_AADHAAR"] and not fs[0].redact


def test_vid_not_double_reported_as_aadhaar():
    fs = find_numbers(_pt(["VID:", *_groups(V16, (4, 4, 4, 4))]), 0)
    assert _types(fs) == ["VID"] and fs[0].value_masked == f"XXXX XXXX XXXX {V16[-4:]}"
    assert _types(find_numbers(_pt([V16]), 0)) == ["VID"]
    assert _types(find_numbers(_pt(["-".join(_groups(V16, (4, 4, 4, 4)))]), 0)) == ["VID"]


def test_long_digit_run_not_windowed():
    # valid Aadhaar followed by extra digits must not produce a 12-digit window match
    assert "AADHAAR" not in _types(find_numbers(_pt([A12 + "3456"]), 0))
    # 4+4+4 followed by a 5-digit atom: not an Aadhaar
    assert find_numbers(_pt([*_groups(A12), "79841"]), 0) == []
    assert find_numbers(_pt([*_groups(A12), "798412670824"]), 0) == []
    # a different line is a different number
    assert find_numbers(_pt(_groups(A12)[:2], _groups(A12)[2:]), 0) == []


def test_fragmented_ocr_groups_accepted():
    assert _types(find_numbers(_pt([A12[:8], A12[8:]], text_layer=False), 0)) == ["AADHAAR"]
    f = find_numbers(_pt([A12[:4], A12[4:8], A12[8:10], A12[10:]], text_layer=False), 0)
    assert _types(f) == ["AADHAAR"] and f[0].source == "ocr"


def test_ocr_confusions_and_malayalam_digits():
    ml = str.maketrans("0123456789", "൦൧൨൩൪൫൬൭൮൯")
    g = _groups(A12)
    toks = [x.translate(ml) for x in g]
    assert _types(find_numbers(_pt(toks), 0)) == ["AADHAAR"]
    src = A12.replace("0", "O").replace("1", "l")
    assert src != A12
    gs = _groups(src)
    gs[-1] += ","
    assert _types(find_numbers(_pt(["Aadhaar:", *gs]), 0)) == ["AADHAAR"]


def test_value_masked_never_more_than_four_digits():
    for fs in (
        find_numbers(_pt(["UID", *_groups(A12)]), 0),
        find_numbers(_pt(["VID", *_groups(V16, (4,) * 4)]), 0),
        find_numbers(_pt(["XXXX-XXXX-" + A12[-4:]]), 0),
    ):
        assert fs
        for f in fs:
            assert sum(c.isdigit() for c in f.value_masked) <= 4


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u else 0.0


def _eval(deed, min_recall: float):
    doc = pymupdf.open(deed.path)
    hit = total = 0
    for p in range(len(doc)):
        fs = find_numbers(get_page_text(doc[p]), p)
        for a in deed.gt["annotations"]:
            if a["page"] != p:
                continue
            if a["type"] == "DECOY_NUMBER":
                assert not [f for f in fs if _iou(f.bbox_pt, a["bbox_pt"]) > 0], f"decoy p{p}"
            elif a["type"] in ("AADHAAR", "VID"):
                total += 1
                hit += any(f.type == a["type"] and _iou(f.bbox_pt, a["bbox_pt"]) >= 0.3 for f in fs)
    assert total > 0
    assert hit / total >= min_recall, (hit, total)


def test_born_digital_deed_full_recall_no_decoys(born_digital_deed):
    _eval(born_digital_deed, 1.0)


def test_scanned_deed_recall_no_decoys(scanned_deed):
    _eval(scanned_deed, 0.8)
