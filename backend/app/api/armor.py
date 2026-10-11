"""SurakshitID routes (docs/ARMOR_CONTRACT.md).

Captures live in memory only (bounded, oldest evicted). Armored outputs are kept in memory
too; the badge registry/ledger (hashes + purpose only) is the one thing persisted. Every
image this router serves has thumb impressions and QR codes pixelated, except the armored
output, where they are already 0x00.
"""

from __future__ import annotations

import io
import logging
import math
import secrets
import threading
import uuid
from collections import OrderedDict
from functools import lru_cache

import cv2
import numpy as np
import pymupdf
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

from backend.app.armor_pipeline import STEPS, ArmorOutput, armor
from backend.app.core import badge as badge_mod
from backend.app.core.presets import PRESETS
from backend.app.core.verify_raster import pdf_facts, pdf_pixels, png_chunks
from backend.app.core.voice_intent import parse as parse_voice
from backend.app.settings import settings

log = logging.getLogger("surakshitid")
router = APIRouter(prefix="/api")
MAX_UPLOAD = 25 * 1024 * 1024
MAX_JOBS = 6  # laptop RAM: each job holds a few full-resolution arrays
MOSAIC = 14
PIXELATE_TYPES = ("FINGERPRINT", "QR", "BARCODE")

SEALER = badge_mod.Sealer(settings.armor_dir)

# name -> (label, kind, seed, photo, blur). Synthetic, deterministic, watermarked.
ID_SAMPLES = {
    "aadhaar-front-photo": ("Aadhaar front · phone photo", "aadhaar_front", 3, True, 0.0),
    "aadhaar-back-photo": ("Aadhaar back · QR + address", "aadhaar_back", 3, True, 0.0),
    "pan-card-photo": ("PAN card · phone photo", "pan", 4, True, 0.0),
    "kyc-sheet-thumbprint": ("KYC photocopy with thumbprint", "kyc_sheet", 2, False, 0.0),
    "aadhaar-blurry": ("Blurry photo (should be refused)", "aadhaar_front", 5, True, 3.5),
}

_jobs: OrderedDict[str, dict] = OrderedDict()
_private: dict[str, ArmorOutput] = {}
_attacks: OrderedDict[str, dict] = OrderedDict()  # id -> {png, report, job_id}
_lock = threading.Lock()
_heavy = threading.Semaphore(1)


# ---- helpers ---------------------------------------------------------------------------

def _png(rgb: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise HTTPException(500, "encode failed")
    return buf.tobytes()


def _pixelate(img: np.ndarray, box, block: int = MOSAIC) -> None:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    roi = img[y0:y1, x0:x1]
    small = cv2.resize(roi, (max(1, (x1 - x0) // block), max(1, (y1 - y0) // block)),
                       interpolation=cv2.INTER_AREA)
    img[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)


def _safe_preview(rgb: np.ndarray, boxes: list, dpi: int) -> np.ndarray:
    out = rgb.copy()
    for b in boxes:
        _pixelate(out, b, max(MOSAIC, dpi // 20))
    return out


@lru_cache(maxsize=8)
def _sample(name: str) -> tuple[bytes, bytes]:
    """(original JPEG with fake EXIF — server side only, preview JPEG with prints/QR
    pixelated — the only version sent to the browser)."""
    from synth.idcard_gen import phone_photo, render_id, to_jpeg_with_exif

    _, kind, seed, photo, blur = ID_SAMPLES[name]
    rgb, gt = render_id(seed, kind)
    if photo:
        rgb, gt = phone_photo(rgb, gt, seed, blur=blur)
    boxes = [a["bbox_px"] for a in gt["annotations"] if a["type"] in PIXELATE_TYPES]
    preview = _safe_preview(rgb, [[b[0] - 6, b[1] - 6, b[2] + 6, b[3] + 6] for b in boxes], 200)
    s = 640 / max(preview.shape[:2])
    preview = cv2.resize(preview, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, prev = cv2.imencode(".jpg", cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))
    return to_jpeg_with_exif(rgb), prev.tobytes()


def _job(job_id: str) -> dict:
    j = _jobs.get(job_id)
    if j is None:
        raise HTTPException(404, "unknown job")
    return j


def _out(job_id: str, need_issue: bool = False) -> ArmorOutput:
    j = _job(job_id)
    o = _private.get(job_id)
    if j["status"] != "done" or o is None:
        raise HTTPException(409, "job not finished")
    if need_issue and o.png is None:
        raise HTTPException(409, "no armored copy: " + j["result"]["decision"])
    return o


def _start(data: bytes, preset: str, recipient: str, valid_days: int, source: str,
           background: BackgroundTasks) -> dict:
    job_id = uuid.uuid4().hex[:12]
    job = {"job_id": job_id, "status": "queued", "error": None, "source": source,
           "steps": [{"key": k, "label": lbl, "status": "pending", "ms": None}
                     for k, lbl in STEPS],
           "result": None}
    with _lock:
        _jobs[job_id] = job
        while len(_jobs) > MAX_JOBS:
            old, _ = _jobs.popitem(last=False)
            _private.pop(old, None)
    background.add_task(_run, job_id, data, preset, recipient, valid_days)
    return {"job_id": job_id}


def _run(job_id: str, data: bytes, preset: str, recipient: str, valid_days: int) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    steps = {s["key"]: s for s in job["steps"]}

    def step(key: str, status: str, ms: float | None) -> None:
        steps[key].update(status=status, ms=ms)

    with _heavy:
        job["status"] = "processing"
        try:
            out = armor(data, preset, recipient, valid_days, SEALER, step)
            del data
            for s in job["steps"]:
                if s["status"] == "running":
                    s["status"] = "failed" if out.result["decision"] != "ARMOR_AND_ISSUE" \
                        else "done"
            _private[job_id] = out
            job["result"] = out.result
            job["status"] = "done"
        except Exception as e:  # clean error; details (never document content) go to the log
            log.exception("armor failed for job %s", job_id)
            job["status"], job["error"] = "error", f"armoring failed: {type(e).__name__}"


# ---- routes ----------------------------------------------------------------------------

@router.get("/presets")
def presets() -> list[dict]:
    return [p.public() for p in PRESETS.values()]


class VoiceIn(BaseModel):
    text: str


@router.post("/voice/parse")
def voice(body: VoiceIn) -> dict:
    return parse_voice(body.text)


@router.get("/id-samples")
def id_samples() -> list[dict]:
    return [{"name": k, "label": v[0], "kind": v[1]} for k, v in ID_SAMPLES.items()]


@router.get("/id-samples/{name}.jpg")
def id_sample_preview(name: str) -> Response:
    if name not in ID_SAMPLES:
        raise HTTPException(404, "unknown sample")
    return Response(_sample(name)[1], media_type="image/jpeg")


@router.post("/id-samples/{name}/armor")
def armor_sample(name: str, background: BackgroundTasks, preset: str = Form(""),
                 recipient: str = Form(""), valid_days: int = Form(1)) -> dict:
    if name not in ID_SAMPLES:
        raise HTTPException(404, "unknown sample")
    return _start(_sample(name)[0], preset, recipient, valid_days, "sample", background)


@router.post("/armor")
async def armor_upload(file: UploadFile, background: BackgroundTasks, preset: str = Form(""),
                       recipient: str = Form(""), valid_days: int = Form(1),
                       source: str = Form("upload")) -> dict:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file larger than 25 MB")
    if not data:
        raise HTTPException(400, "empty file")
    return _start(data, preset, recipient, valid_days, source, background)


@router.get("/armor/{job_id}")
def armor_job(job_id: str) -> dict:
    j = _job(job_id)
    return {k: j[k] for k in ("job_id", "status", "error", "steps", "result")}


@router.get("/armor/{job_id}/view.png")
def armor_view(job_id: str, which: str = "after") -> Response:
    o = _out(job_id)
    if which == "after":
        if o.final_rgb is None:
            raise HTTPException(409, "no armored copy")
        return Response(_png(o.final_rgb), media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    if which != "before" or o.prepared is None:
        raise HTTPException(400, "which must be before|after")
    img = _safe_preview(o.prepared.rgb,
                        [f.bbox_px for f in o.findings if f.type in PIXELATE_TYPES],
                        o.prepared.dpi)
    colors = {"MASK": (220, 38, 38), "MASK_PARTIAL": (217, 119, 6), "KEEP": (22, 163, 74)}
    t = max(2, img.shape[1] // 400)
    for f in o.result["findings"]:
        x0, y0, x1, y1 = f["bbox_px"]
        cv2.rectangle(img, (x0 - t, y0 - t), (x1 + t, y1 + t), colors[f["action"]], t)
    return Response(_png(img), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/armor/{job_id}/armored.png")
def armored_png(job_id: str) -> Response:
    o = _out(job_id, need_issue=True)
    aid = o.result["armor_id"]
    return Response(o.png, media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="{aid}.png"'})


@router.get("/armor/{job_id}/armored.pdf")
def armored_pdf(job_id: str) -> Response:
    o = _out(job_id, need_issue=True)
    aid = o.result["armor_id"]
    return Response(o.pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{aid}.pdf"'})


@router.get("/armor/{job_id}/badge.json")
def badge_json(job_id: str) -> dict:
    o = _out(job_id, need_issue=True)
    return o.result["badge"]


def _entropy(a: np.ndarray) -> float:
    if a.size == 0:
        return 0.0
    counts = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    p = counts[counts > 0] / a.size
    return float(-(p * np.log2(p)).sum()) + 0.0


@router.get("/armor/{job_id}/inspect")
def inspect(job_id: str) -> dict:
    """Proof for the Adversarial Inspector, computed from the exported bytes."""
    o = _out(job_id, need_issue=True)
    dec = cv2.cvtColor(cv2.imdecode(np.frombuffer(o.png, np.uint8), cv2.IMREAD_COLOR),
                       cv2.COLOR_BGR2RGB)
    masks = []
    bright_max = 0
    for x0, y0, x1, y1 in o.result["masks_px"]:
        r = dec[y0:y1, x0:x1]
        bright_max = max(bright_max, int(np.clip(r.astype(np.int32) * 255, 0, 255).max(
            initial=0)))
        masks.append({"bbox_px": [x0, y0, x1, y1], "pixels": int(r.shape[0] * r.shape[1]),
                      "min": int(r.min(initial=0)), "max": int(r.max(initial=0)),
                      "unique_values": int(len(np.unique(r))), "entropy_bits": _entropy(r),
                      "hex_sample": " ".join(f"{b:02X}" for b in r.ravel()[:24])})
    f = pdf_facts(o.pdf)
    exif = bool(Image.open(io.BytesIO(o.png)).getexif())
    return {"masks": masks,
            "pdf": {k: f[k] for k in ("text_chars", "text_sample", "metadata", "images",
                                      "annotations", "pages")},
            "png": {"chunks": list(dict.fromkeys(png_chunks(o.png))), "exif": exif},
            "brightened_mask_max": bright_max}


class AttackIn(BaseModel):
    kind: str


def _attack_image(o: ArmorOutput, kind: str) -> np.ndarray:
    img = o.final_rgb.copy()
    h_doc = o.prepared.rgb.shape[0]
    w = img.shape[1]
    faces = [f.bbox_px for f in o.findings if f.type == "FACE"]
    if kind == "erase_watermark":
        # what an inpainting/"magic eraser" tool does: wipe the thin watermark strokes in a band
        y0, y1 = int(h_doc * 0.30), int(h_doc * 0.62)
        x0, x1 = int(w * 0.05), int(w * 0.55)
        band = img[y0:y1, x0:x1]
        img[y0:y1, x0:x1] = cv2.medianBlur(band, 7)
    elif kind == "swap_photo":
        x0, y0, x1, y1 = faces[0] if faces else (int(w * .04), int(h_doc * .2), int(w * .3),
                                                 int(h_doc * .7))
        img[y0:y1, x0:x1] = img[y0:y1, x0:x1][:, ::-1]  # a different "face" in the same frame
        cv2.ellipse(img, ((x0 + x1) // 2, (y0 + y1) // 2), ((x1 - x0) // 4, (y1 - y0) // 3), 0,
                    0, 360, (150, 110, 80), -1)
    elif kind == "unmask":
        # brighten x4: tries to pull hidden digits out of the black boxes. 0 x 4 is still 0.
        img = np.clip(img.astype(np.int32) * 4, 0, 255).astype(np.uint8)
    elif kind == "crop":
        img = img[int(h_doc * 0.18) :, :]  # cut the top off, keep the badge strip
    else:
        raise HTTPException(400, "kind must be erase_watermark|swap_photo|unmask|crop")
    return img


@router.post("/armor/{job_id}/attack")
def attack(job_id: str, body: AttackIn) -> dict:
    o = _out(job_id, need_issue=True)
    img = _attack_image(o, body.kind)
    aid = secrets.token_hex(6)
    report = badge_mod.verify_image(img, SEALER)
    with _lock:
        _attacks[aid] = {"png": _png(img), "report": report, "job_id": job_id}
        while len(_attacks) > 8:
            _attacks.popitem(last=False)
    return {"attack_id": aid, "image_url": f"/api/attacks/{aid}.png", "verify": report}


def attack_context(attack_id: str) -> tuple[dict, np.ndarray, list] | None:
    """(report, tampered RGB, face boxes) for the agent layer."""
    a = _attacks.get(attack_id)
    if a is None:
        return None
    rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(a["png"], np.uint8), cv2.IMREAD_COLOR),
                       cv2.COLOR_BGR2RGB)
    o = _private.get(a["job_id"])
    faces = [list(f.bbox_px) for f in o.findings if f.type == "FACE"] if o else []
    return a["report"], rgb, faces


@router.get("/attacks/{attack_id}.png")
def attack_png(attack_id: str) -> Response:
    a = _attacks.get(attack_id)
    if a is None:
        raise HTTPException(404, "unknown attack")
    return Response(a["png"], media_type="image/png")


@router.get("/copies")
def copies() -> list[dict]:
    return SEALER.copies()


@router.post("/copies/{armor_id}/revoke")
def revoke(armor_id: str) -> dict:
    c = SEALER.revoke(armor_id)
    if c is None:
        raise HTTPException(404, "unknown copy")
    return c


@router.post("/verify")
async def verify(file: UploadFile) -> dict:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD or not data:
        raise HTTPException(400, "file empty or larger than 25 MB")
    if data[:5] == b"%PDF-":
        try:
            rgb = pdf_pixels(data)
            if rgb is None:
                doc = pymupdf.open(stream=data, filetype="pdf")
                pix = doc[0].get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
                rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
        except Exception as e:
            raise HTTPException(400, "not a readable PDF") from e
    else:
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise HTTPException(400, "not a readable image")
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    if math.prod(rgb.shape[:2]) > 40_000_000:
        raise HTTPException(413, "image too large")
    return badge_mod.verify_image(np.ascontiguousarray(rgb), SEALER)
