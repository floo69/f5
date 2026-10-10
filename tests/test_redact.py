import re

import numpy as np
import pymupdf
import pytest

from backend.app.core.redact import redact_pdf
from backend.app.core.types import Finding


def _gt_findings(deed) -> list[Finding]:
    return [
        Finding(
            type=a["type"],
            page=a["page"],
            bbox_pt=tuple(a["bbox_pt"]),
            confidence=1.0,
            source="classical",
        )
        for a in deed.gt_of("FINGERPRINT", "AADHAAR", "VID")
    ]


def _image_regions(doc, page, rect):
    """Pixel arrays of every embedded image region that intersects `rect`."""
    out = []
    for img in page.get_images(full=True):
        for q in page.get_image_rects(img[0]):
            if not q.intersects(rect):
                continue
            pm = pymupdf.Pixmap(doc, img[0])
            a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)
            sx, sy = pm.width / q.width, pm.height / q.height
            i = rect & q
            out.append(
                a[
                    int((i.y0 - q.y0) * sy) + 1 : int((i.y1 - q.y0) * sy) - 1,
                    int((i.x0 - q.x0) * sx) + 1 : int((i.x1 - q.x0) * sx) - 1,
                ]
            )
    return out


@pytest.mark.parametrize("fixture", ["born_digital_deed", "scanned_deed"])
def test_true_redaction_removes_text_and_pixels(fixture, request):
    deed = request.getfixturevalue(fixture)
    out, rects = redact_pdf(deed.pdf, _gt_findings(deed))
    doc = pymupdf.open(stream=out, filetype="pdf")
    assert rects
    for pno, rs in rects.items():
        page = doc[pno]
        for r in map(pymupdf.Rect, rs):
            text = page.get_text("text", clip=r)
            assert not re.search(r"\d", text), "digits survived redaction"
            for region in _image_regions(doc, page, r):
                assert region.size == 0 or region.var() == 0, "image pixels survived redaction"


def test_redaction_strips_metadata_and_keeps_watermark(born_digital_deed):
    out, _ = redact_pdf(born_digital_deed.pdf, _gt_findings(born_digital_deed))
    doc = pymupdf.open(stream=out, filetype="pdf")
    assert not any(doc.metadata.get(k) for k in ("author", "creator", "producer", "title"))
    assert "SYNTHETIC SAMPLE" in doc[0].get_text()


def test_masked_aadhaar_is_not_redacted(born_digital_deed):
    f = Finding(
        type="MASKED_AADHAAR",
        page=0,
        bbox_pt=(50, 50, 150, 60),
        confidence=1.0,
        source="textlayer",
        redact=False,
    )
    _, rects = redact_pdf(born_digital_deed.pdf, [f])
    assert rects == {}
