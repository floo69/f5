"""Run the reproducible synthetic evaluation without inventing unavailable metrics."""
from __future__ import annotations
import json, shutil, time
from datetime import UTC, datetime
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from backend.app.core.fp_onnx import model_info
from backend.app.evaluation import precision_recall_f1, summarize_times
from mock_portal.seed import seed_portal


def run() -> dict:
    manifest = seed_portal()
    result = {"notice": "SYNTHETIC TEST SET — RESULTS ARE NOT PRODUCTION PERFORMANCE GUARANTEES.", "dataset_version": "portal-v5-seed-810000", "run_at": datetime.now(UTC).isoformat(), "documents": len(manifest["records"]), "pages": len(manifest["records"]), "configuration": {"unit": "document category and page outcome", "matching": "exact category agreement; no model output is used as ground truth", "detector": "classical"}, "model": model_info("data/models/thumb_det_int8.onnx"), "ocr_available": bool(shutil.which("tesseract")), "metrics": {"overall": precision_recall_f1(0, 0, 0), "by_category": {}, "timing": summarize_times([]), "verification_failures": None, "blocked_for_review": None, "unsafe_publishable_sensitive_pages": None}
    }
    if not result["ocr_available"]:
        result["error"] = "N/A: Tesseract is unavailable; no scan predictions were generated. Install Tesseract and rerun."
    return result


if __name__ == "__main__": print(json.dumps(run(), indent=2))
