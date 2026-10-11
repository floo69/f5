"""ThumbShield API (v1). Contract: docs/API_CONTRACT.md.

Uploaded originals are kept in memory only; the redacted PDF and certificate are the only
files written (data/out/<job_id>/). The "before" page view pixelates every detected
thumb impression before it leaves this process.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.app.api.agents import router as agents_router
from backend.app.api.armor import router as armor_router
from backend.app.core.report import certificate_dict, certificate_pdf
from backend.app.pipeline import process_pdf

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
    log.warning("SurakshitID / ThumbShield running locally — no document leaves this machine")
    yield


app = FastAPI(title="SurakshitID + ThumbShield API", lifespan=lifespan)
app.include_router(armor_router)
app.include_router(agents_router)
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "local_only": True}


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
            job["error"] = f"processing failed: {type(e).__name__}"


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
