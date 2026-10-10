import time

from backend.app.core.decision import DecisionFinding, DecisionRequest, DecisionResponse, decide
from backend.app.core.fusion import fuse_candidates
from backend.app.core.fp_onnx import DetectorUnavailable, model_info
from backend.app.core.types import Finding


def request(*findings, text_layer=True, ocr=1.0, verification="not_run"):
    return DecisionRequest(
        doc_id="test", page=0, text_layer=text_layer, ocr_quality=ocr,
        findings=[DecisionFinding(**f) for f in findings], verification=verification,
    )


def test_verification_failure_has_highest_precedence():
    result = decide(request({"type": "AADHAAR", "confidence": 1.0}, verification="fail"))
    assert result.action == "BLOCK_FOR_REVIEW"
    assert "VERIFICATION_FAILED" in result.reason_codes


def test_sensitive_and_low_ocr_is_redacted_before_ocr_block_rule():
    result = decide(request({"type": "AADHAAR", "confidence": 1.0}, text_layer=False, ocr=0.1))
    assert result.action == "REDACT_AND_PUBLISH"


def test_low_ocr_without_findings_blocks():
    result = decide(request(text_layer=False, ocr=0.1))
    assert result.action == "BLOCK_FOR_REVIEW"
    assert "LOW_OCR_CONFIDENCE" in result.reason_codes


def test_unsafe_optional_backend_is_guarded():
    class Unsafe:
        def decide(self, _):
            return DecisionResponse(action="PUBLISH", confidence=1, backend="fake")

    result = decide(request({"type": "FINGERPRINT", "confidence": 0.9, "sources": ["classical"]}), Unsafe())
    assert result.action == "REDACT_AND_PUBLISH"
    assert result.backend == "rules-guard"


def test_optional_backend_timeout_falls_back():
    class Slow:
        def decide(self, _):
            time.sleep(0.5)
            return DecisionResponse(action="PUBLISH", confidence=1, backend="slow")

    result = decide(request(), Slow())
    assert result.backend == "rules-fallback"
    assert result.fallback is True


def finding(box, confidence, source):
    return Finding(type="FINGERPRINT", page=0, bbox_pt=box, confidence=confidence, source=source)


def test_fusion_matches_and_adds_configured_bonus():
    result = fuse_candidates([finding((0, 0, 100, 100), 0.4, "classical")], [finding((10, 10, 90, 90), 0.7, "onnx")])
    assert len(result) == 1
    assert result[0].confidence == 0.8
    assert result[0].source == "classical+onnx"


def test_fusion_preserves_unmatched_findings():
    result = fuse_candidates([finding((0, 0, 10, 10), 0.4, "classical")], [finding((100, 100, 120, 120), 0.7, "onnx")])
    assert len(result) == 2


def test_missing_model_is_not_reported_as_available(tmp_path):
    info = model_info(tmp_path / "missing.onnx")
    assert info["available"] is False
    try:
        from backend.app.core.fp_onnx import OnnxDetector
        OnnxDetector(tmp_path / "missing.onnx")
    except DetectorUnavailable:
        pass
    else:
        raise AssertionError("missing ONNX model must fail closed")
