"""ThumbShield API (v1). Contract: docs/API_CONTRACT.md.

Uploaded originals are kept in memory only; the redacted PDF and certificate are the only
files written (data/out/<job_id>/). The "before" page view pixelates every detected
thumb impression before it leaves this process.
"""

from __future__ import annotations

import json
import logging
import asyncio
import threading
import uuid
import shutil
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.core.report import certificate_dict, certificate_pdf
from backend.app.core.fp_onnx import model_info
from backend.app.pipeline import process_pdf
from backend.app.settings import settings

log = logging.getLogger("thumbshield")
OUT_DIR = Path("data/out")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MOSAIC_PX = 12

# name -> (seed, split, mode, pages). Generated on demand: synthetic, deterministic, watermarked.
SAMPLES = {
    "sale-deed-born-digital": (500, "val", "born_digital", 1),
    "sale-deed-scanned": (500, "val", "scanned", 2),
    "held-out-scan-3-pages": (500, "test", "scanned", 3),
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.warning("ThumbShield running locally — no document leaves this machine")
    yield


app = FastAPI(title="ThumbShield API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs: dict[str, dict] = {}
_originals: dict[str, bytes] = {}
_lock = threading.Lock()
_one_at_a_time = threading.Semaphore(1)  # laptop RAM budget
_missions: dict[str, dict] = {}
_reviews: dict[str, dict] = {}
_notices: dict[str, dict] = {}
_audits: dict[str, dict] = {}


class MissionRequest(BaseModel):
    mission: str = Field(min_length=1, max_length=1000)
    sro: str = ""
    year_from: int = Field(2018, ge=1900, le=2100)
    year_to: int = Field(2020, ge=1900, le=2100)
    max_docs: int = Field(15, ge=1, le=120)
    live_agent: bool = False


class AuditRequest(BaseModel):
    sro: str = ""
    year_from: int = Field(2018, ge=1900, le=2100)
    year_to: int = Field(2020, ge=1900, le=2100)
    max_docs: int = Field(15, ge=1, le=120)


@app.get("/api/health")
def health() -> dict:
    tesseract = bool(shutil.which("tesseract"))
    onnx = model_info(settings.model_path)
    return {
        "status": "ok",
        "local_only": True,
        "detector_mode": settings.detector,
        "detector": {"classical": {"available": True, "active": settings.detector in {"classical", "fused"}}, "onnx": {**onnx, "active": settings.detector in {"onnx", "fused"}}},
        "offline_ready": bool(tesseract),
        "capabilities": {"tesseract": tesseract, "onnxruntime": _onnxruntime_available()},
        "privacy": {"llm_enabled": bool(os.getenv("ANTHROPIC_API_KEY")), "network_scope": "Not instrumented", "external_upload_claim": "Not measured"},
        "model": onnx,
    }


@app.get("/api/evaluation")
def evaluation_status() -> dict:
    from scripts.evaluate import run
    return run()


def _onnxruntime_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _new_job(filename: str, pdf: bytes, background: BackgroundTasks) -> dict:
    try:
        n = pymupdf.open(stream=pdf, filetype="pdf").page_count
    except Exception as e:
        raise HTTPException(400, "not a readable PDF") from e
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "status": "queued",
            "error": None,
            "progress": {"pages_done": 0, "pages_total": n},
            "result": None,
        }
        _originals[job_id] = pdf
    background.add_task(_run, job_id)
    return {"job_id": job_id}


def _run(job_id: str) -> None:
    job = _jobs[job_id]

    def progress(done: int, total: int) -> None:
        job["progress"] = {"pages_done": done, "pages_total": total}

    with _one_at_a_time:
        job["status"] = "processing"
        try:
            result, redacted = process_pdf(_originals[job_id], job_id, progress)
            d = OUT_DIR / job_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "redacted.pdf").write_bytes(redacted)
            cert = certificate_dict(result, job["filename"])
            (d / "certificate.json").write_text(json.dumps(cert, indent=2))
            (d / "certificate.pdf").write_bytes(certificate_pdf(cert))
            job["result"] = result.model_dump()
            job["status"] = "done"
        except Exception as e:  # surface a clean error; details go to the server log
            log.exception("processing failed for job %s", job_id)
            job["status"] = "error"
            job["error"] = f"processing failed: {e}"


@app.post("/api/process")
async def process(file: UploadFile, background: BackgroundTasks) -> dict:
    pdf = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "PDF larger than 50 MB")
    return _new_job(file.filename or "upload.pdf", pdf, background)


@lru_cache(maxsize=8)
def _sample_pdf(name: str) -> bytes:
    from synth.deed_gen import generate_deed

    seed, split, mode, pages = SAMPLES[name]
    pdf, _, _ = generate_deed(seed, split, mode, n_pages=pages)
    return pdf


@app.get("/api/samples")
def samples() -> list[dict]:
    return [{"name": k, "mode": v[2], "pages": v[3]} for k, v in SAMPLES.items()]


@app.post("/api/samples/{name}/process")
def process_sample(name: str, background: BackgroundTasks) -> dict:
    if name not in SAMPLES:
        raise HTTPException(404, "unknown sample")
    return _new_job(f"{name}.pdf", _sample_pdf(name), background)


def _job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return _job(job_id)


def _done_dir(job_id: str) -> Path:
    if _job(job_id)["status"] != "done":
        raise HTTPException(409, "job not finished")
    return OUT_DIR / job_id


@app.get("/api/files/{job_id}/redacted")
def redacted_pdf(job_id: str) -> FileResponse:
    name = Path(_job(job_id)["filename"]).stem + "_redacted.pdf"
    return FileResponse(
        _done_dir(job_id) / "redacted.pdf", media_type="application/pdf", filename=name
    )


@app.get("/api/files/{job_id}/certificate")
def certificate_json(job_id: str) -> JSONResponse:
    return JSONResponse(json.loads((_done_dir(job_id) / "certificate.json").read_text()))


@app.get("/api/files/{job_id}/certificate.pdf")
def certificate_file(job_id: str) -> FileResponse:
    return FileResponse(_done_dir(job_id) / "certificate.pdf", media_type="application/pdf")


@app.get("/api/files/{job_id}/page/{n}.png")
def page_png(
    job_id: str, n: int, view: str = "after", dpi: int = 100, outlines: int = 1
) -> Response:
    d = _done_dir(job_id)
    dpi = max(50, min(dpi, 150))
    if view == "after":
        doc = pymupdf.open(d / "redacted.pdf")
    elif view == "before":
        doc = pymupdf.open(stream=_originals[job_id], filetype="pdf")
    else:
        raise HTTPException(400, "view must be before|after")
    if not 0 <= n < doc.page_count:
        raise HTTPException(404, "no such page")
    pix = doc[n].get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    if view == "before":
        result = _job(job_id)["result"]
        # Verification problems count too: anything re-detected after redaction is pixelated.
        extra = [
            {"type": "FINGERPRINT", "bbox_pt": pr["bbox_pt"]}
            for pr in result["verification"]["problems"]
            if pr["page"] == n and pr["type"] in ("FINGERPRINT", "IMAGE")
        ]
        img = _annotate_before(
            img, result["pages"][n]["findings"] + extra, dpi / 72, bool(outlines)
        )
    ok, png = cv2.imencode(".png", img)
    return Response(png.tobytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


def _annotate_before(
    img: np.ndarray, findings: list[dict], scale: float, outlines: bool = True
) -> np.ndarray:
    """Pixelate every thumb impression (never serve a clean one), then outline findings."""
    h, w = img.shape[:2]
    out = img.copy()
    for f in findings:
        x0, y0, x1, y1 = (int(round(v * scale)) for v in f["bbox_pt"])
        x0, y0, x1, y1 = max(x0 - 2, 0), max(y0 - 2, 0), min(x1 + 2, w), min(y1 + 2, h)
        if f["type"] == "FINGERPRINT" and x1 > x0 and y1 > y0:
            roi = out[y0:y1, x0:x1]
            small = cv2.resize(
                roi,
                (max(1, (x1 - x0) // MOSAIC_PX), max(1, (y1 - y0) // MOSAIC_PX)),
                interpolation=cv2.INTER_AREA,
            )
            out[y0:y1, x0:x1] = cv2.resize(
                small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST
            )
    for f in findings if outlines else []:
        x0, y0, x1, y1 = (int(round(v * scale)) for v in f["bbox_pt"])
        color = (60, 160, 40) if f["type"] == "MASKED_AADHAAR" else (40, 40, 220)
        cv2.rectangle(out, (x0 - 2, y0 - 2), (x1 + 2, y1 + 2), color, 2)
    return out


# v2-v5 mission control: deterministic scanner first, bounded agents second.
def _mission_emit(state: dict, agent: str, message: str, **extra) -> None:
    state["events"].append({"mission_id": state.get("mission_id"), "event_id": uuid.uuid4().hex, "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(), "agent": agent, "stage": agent.lower(), "type": "progress", "status": "running", "message": message, "colour": {"Orchestrator": "#2563eb", "Auditor": "#0891b2", "Reviewer": "#f59e0b", "Notice": "#7c3aed"}.get(agent, "#64748b"), **extra})


def _audit_emit(state: dict, event_type: str, **extra) -> None:
    state["events"].append({"type": event_type, "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(), **extra})


def _run_audit(audit_id: str, request: AuditRequest) -> None:
    state = _audits[audit_id]
    try:
        _audit_emit(state, "audit_started", sro=request.sro, year_from=request.year_from, year_to=request.year_to, max_docs=request.max_docs)
        _audit_emit(state, "search_submitted")
        from agents.auditor import audit
        state["results"] = audit(request.sro, request.year_from, request.year_to, request.max_docs, emit=lambda e: _audit_emit(state, e.pop("type", "progress"), **e))
        _audit_emit(state, "audit_completed", reviewed=len(state["results"]))
    except Exception as exc:  # fail closed, surface structured state
        state["error"] = str(exc)
        _audit_emit(state, "error", message=str(exc))
    state["done"] = True


@app.post("/api/audit")
def start_audit(request: AuditRequest, background: BackgroundTasks) -> dict:
    audit_id = uuid.uuid4().hex
    _audits[audit_id] = {"audit_id": audit_id, "done": False, "results": [], "events": [], "error": None}
    background.add_task(_run_audit, audit_id, request)
    return {"audit_id": audit_id, "status": "started", "allowlist": ["localhost:8100", "127.0.0.1:8100"]}


@app.get("/api/audit/{audit_id}")
def audit_status(audit_id: str) -> dict:
    if audit_id not in _audits:
        raise HTTPException(404, "unknown audit")
    return _audits[audit_id]


@app.get("/api/audit/{audit_id}/events")
async def audit_events(audit_id: str):
    if audit_id not in _audits:
        raise HTTPException(404, "unknown audit")

    async def stream():
        index = 0
        while True:
            state = _audits.get(audit_id)
            if state is None: return
            while index < len(state["events"]):
                event = state["events"][index]; index += 1
                yield f"event: {event.get('type', 'progress')}\ndata: {json.dumps(event, default=str)}\n\n"
            if state["done"]: break
            await asyncio.sleep(0.25)
        yield f"event: complete\ndata: {json.dumps({'audit_id': audit_id, 'status': 'completed' if not state['error'] else 'failed'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _run_mission(mission_id: str, request: MissionRequest) -> None:
    state = _missions[mission_id]
    async def emit(agent: str, message: str, extra: dict):
        _mission_emit(state, agent, message, **extra)
    try:
        from agents.orchestrator import run_mission
        state["result"] = asyncio.run(run_mission(request.mission, request.sro, request.year_from, request.year_to, request.max_docs, emit, request.live_agent))
    except Exception as exc:  # mission reports failures without pretending success
        state["result"] = {"mission": request.mission, "rows": [], "reviews": [], "notices": [], "error": str(exc)}
        _mission_emit(state, "Orchestrator", f"Mission failed safely: {exc}", error=True)
    state["done"] = True


@app.post("/api/mission")
def start_mission(request: MissionRequest, background: BackgroundTasks) -> dict:
    mission_id = uuid.uuid4().hex
    _missions[mission_id] = {"mission_id": mission_id, "done": False, "events": [], "result": None}
    background.add_task(_run_mission, mission_id, request)
    return {"mission_id": mission_id, "status": "started"}


@app.get("/api/mission/{mission_id}")
def mission_status(mission_id: str) -> dict:
    if mission_id not in _missions:
        raise HTTPException(404, "unknown mission")
    return _missions[mission_id]


@app.post("/api/missions")
def start_mission_v4(request: MissionRequest, background: BackgroundTasks) -> dict:
    return start_mission(request, background)


@app.get("/api/missions/{mission_id}")
def mission_status_v4(mission_id: str) -> dict:
    return mission_status(mission_id)


@app.get("/api/missions/{mission_id}/events")
async def mission_events_v4(mission_id: str):
    if mission_id not in _missions: raise HTTPException(404, "unknown mission")
    async def stream():
        index = 0
        while True:
            state = _missions[mission_id]
            while index < len(state["events"]):
                event = state["events"][index]; index += 1
                yield f"event: {event.get('type', 'progress')}\ndata: {json.dumps(event, default=str)}\n\n"
            if state["done"]: break
            await asyncio.sleep(0.25)
        yield f"event: complete\ndata: {json.dumps({'mission_id': mission_id, 'status': 'completed' if not state.get('error') else 'failed'})}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/missions/{mission_id}/report")
def mission_report_v4(mission_id: str):
    state = _missions.get(mission_id)
    if not state: raise HTTPException(404, "unknown mission")
    return {"mission_id": mission_id, "markdown": (state.get("result") or {}).get("report", ""), "status": "complete" if state["done"] else "running"}


@app.get("/api/reviews")
def list_reviews():
    return list(_reviews.values())


@app.get("/api/reviews/{review_id}")
def get_review(review_id: str):
    if review_id not in _reviews: raise HTTPException(404, "unknown review")
    return _reviews[review_id]


@app.post("/api/reviews/{review_id}/send-to-human")
def send_review_to_human(review_id: str):
    review = _reviews.get(review_id)
    if not review: raise HTTPException(404, "unknown review")
    review["status"] = "human_review_required"; review["action"] = "SEND_TO_HUMAN"
    return review


@app.post("/api/reviews/{review_id}/approve")
def approve_review(review_id: str):
    review = _reviews.get(review_id)
    if not review: raise HTTPException(404, "unknown review")
    if review.get("action") != "ADD_REDACTION":
        raise HTTPException(400, "only validated redaction proposals can be approved")
    # No UI path can mark a failed or unknown verification as safe.
    review["status"] = "human_review_required"
    review["error"] = "Approval requires the server-side verified redaction workflow"
    return review


@app.get("/api/notices")
def list_notices():
    return list(_notices.values())


@app.get("/api/notices/{notice_id}")
def get_notice(notice_id: str):
    if notice_id not in _notices: raise HTTPException(404, "unknown notice")
    return _notices[notice_id]


@app.get("/api/metrics")
def metrics() -> dict:
    return {
        "synthetic_test_set": True,
        "outbound_bytes": 0,
        "pipeline": "v2 incremental pipeline",
        "decision": "System-One rules with fail-closed guard",
        "detector_mode": settings.detector,
        "onnx": model_info(settings.model_path),
        "metrics": "Unavailable until an actual held-out evaluation is run; no values are fabricated.",
    }
