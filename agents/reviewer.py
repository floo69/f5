"""Forensic Tamper Reviewer: explains a VerifyReport; can only escalate, never clear.

The image sent to Claude is the sealed copy downscaled, with any thumb-impression box
pixelated (they are already 0x00 after armoring; this is belt and braces) and the altered
regions outlined, plus the report's coordinates. Deterministic fallback: geometry rules.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np

from agents.runner import AgentRun, Budget, Emit, run_llm, spec


def _review_image(rgb: np.ndarray, regions: list[list[int]], fingerprints: list) -> str:
    img = rgb.copy()
    for x0, y0, x1, y1 in fingerprints:
        roi = img[y0:y1, x0:x1]
        if roi.size:
            small = cv2.resize(roi, (max(1, roi.shape[1] // 14), max(1, roi.shape[0] // 14)))
            img[y0:y1, x0:x1] = cv2.resize(small, (roi.shape[1], roi.shape[0]),
                                           interpolation=cv2.INTER_NEAREST)
    t = max(2, img.shape[1] // 300)
    for x0, y0, x1, y1 in regions:
        cv2.rectangle(img, (x0, y0), (x1, y1), (230, 0, 0), t)
    s = min(1.0, 1000 / max(img.shape[:2]))
    img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.standard_b64encode(buf.tobytes()).decode()


def deterministic(report: dict, faces: list | None = None) -> dict:
    status = report.get("status")
    if status != "FORGERY_DETECTED":
        return {"attack_type": "none", "recommend_escalation": status not in ("AUTHENTIC",),
                "explanation": report.get("detail", "")}
    total = max(1, report.get("total_tiles") or 1)
    frac = report.get("altered_tiles", 0) / total
    detail = report.get("detail", "")
    if "size changed" in detail:
        kind = "crop"
        why = ("The image size no longer matches the sealed copy, so part of it was cut away "
               "or it was resized.")
    elif frac > 0.5:
        kind = "global_edit"
        why = ("Most tiles changed: the whole image was re-saved, filtered or brightened. "
               "Masked areas stay black, so nothing hidden was recovered.")
    else:
        regions = report.get("altered_regions", [])
        if any(_overlap(r, f) > 0.3 for r in regions for f in (faces or [])):
            kind = "photo_substitution"
            why = "The altered tiles cover the portrait: the photo was replaced or edited."
        else:
            kind = "watermark_erasure"
            why = ("A local band of tiles changed where the purpose watermark runs: someone "
                   "tried to erase or paint over it.")
    return {"attack_type": kind, "recommend_escalation": True, "explanation": why}


def _overlap(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy / max(1, (a[2] - a[0]) * (a[3] - a[1]))


async def review(report: dict, rgb: np.ndarray | None, emit: Emit, budget: Budget,
                 faces: list | None = None, fingerprints: list | None = None) -> AgentRun:
    sp = spec("reviewer")
    facts = {k: report.get(k) for k in ("status", "armor_id", "purpose", "width", "height",
                                        "tile_px", "altered_regions", "altered_tiles",
                                        "total_tiles", "detail")}
    content: list[dict] = []
    if rgb is not None:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                        "data": _review_image(rgb, report.get("altered_regions", []),
                                              fingerprints or [])}})
    content.append({"type": "text", "text": f"Verification report: {facts}\nFaces at: {faces}"})
    run = await run_llm(sp, content, {"report": facts, "faces": faces}, emit, budget)
    det = deterministic(report, faces)
    if run is None:
        emit({"agent": "reviewer", "type": "result", "output": det, "deterministic": True})
        return AgentRun("reviewer", "deterministic", det)
    out = run.output or {}
    # the LLM can add an escalation, never remove one
    out["recommend_escalation"] = bool(out.get("recommend_escalation")) or det[
        "recommend_escalation"]
    run.output = out
    return run
