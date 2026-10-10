from backend.app.core.redact import redact_pdf
from backend.app.core.types import Finding
from backend.app.core.verify import verify_pdf


def _gt(deed, *types):
    return [
        Finding(
            type=a["type"],
            page=a["page"],
            bbox_pt=tuple(a["bbox_pt"]),
            confidence=1.0,
            source="classical",
        )
        for a in deed.gt_of(*types)
    ]


def test_unredacted_pdf_fails(born_digital_deed):
    v = verify_pdf(born_digital_deed.pdf, {}, scanned_pages=set())
    assert v.status == "fail"
    assert {p.type for p in v.problems} >= {"AADHAAR", "FINGERPRINT"}


def test_partially_redacted_pdf_fails(born_digital_deed):
    # Redact the numbers but leave the thumb impressions.
    out, rects = redact_pdf(born_digital_deed.pdf, _gt(born_digital_deed, "AADHAAR", "VID"))
    v = verify_pdf(out, rects, scanned_pages=set())
    assert v.status == "fail"
    assert any(p.type == "FINGERPRINT" for p in v.problems)


def test_fully_redacted_pdf_passes(born_digital_deed):
    out, rects = redact_pdf(
        born_digital_deed.pdf, _gt(born_digital_deed, "FINGERPRINT", "AADHAAR", "VID")
    )
    v = verify_pdf(out, rects, scanned_pages=set())
    assert v.status == "pass", v.problems
