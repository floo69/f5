"""Mock web portals (port 8100) for the agentic auditor. SYNTHETIC DATA ONLY.

- /            "Sunrise Stays" hotel guest-KYC archive that (wrongly) publishes unmasked
               synthetic Aadhaar scans — what the Auditor agent should find and report.
- /uidai-mock  MOCK biometric-lock flow (NOT UIDAI). The agent may navigate up to the OTP
               step and must hand over to the human there; OTPs are never automated.
Images contain no thumb impressions (the browser agent never sees fingerprints).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Mock portals (SYNTHETIC)")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# guest id -> (seed, kind, masked?)
GUESTS = {
    101: (11, "aadhaar_front", False),
    102: (12, "aadhaar_back", False),
    103: (13, "pan", False),
    104: (14, "aadhaar_front", True),
}


@lru_cache(maxsize=8)
def _image(gid: int) -> bytes:
    from synth.idcard_gen import render_id

    seed, kind, masked = GUESTS[gid]
    rgb, gt = render_id(seed, kind)
    rgb = rgb.copy()
    if masked:  # a correctly masked copy: first 8 digits and the QR blacked out
        for a in gt["annotations"]:
            if a["type"] == "QR":
                x0, y0, x1, y1 = a["bbox_px"]
                rgb[y0 - 6 : y1 + 6, x0 - 6 : x1 + 6] = 0
            if a["type"] in ("AADHAAR", "VID") and a.get("parts_px"):
                for p in a["parts_px"][: 2 if a["type"] == "AADHAAR" else 4]:
                    x0, y0, x1, y1 = p
                    rgb[y0 - 4 : y1 + 4, x0 - 4 : x1 + 4] = 0
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return buf.tobytes()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "synthetic": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"guests": GUESTS})


@app.get("/guests/{gid}", response_class=HTMLResponse)
def guest(request: Request, gid: int):
    if gid not in GUESTS:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "guest.html", {"gid": gid, "kind": GUESTS[gid][1]})


@app.get("/uploads/kyc_{gid}.jpg")
def upload(gid: int) -> Response:
    if gid not in GUESTS:
        raise HTTPException(404)
    return Response(_image(gid), media_type="image/jpeg")


@app.get("/uidai-mock", response_class=HTMLResponse)
def uidai_home(request: Request):
    return templates.TemplateResponse(request, "uidai_home.html", {})


@app.get("/uidai-mock/lock", response_class=HTMLResponse)
def uidai_lock(request: Request):
    return templates.TemplateResponse(request, "uidai_lock.html", {"error": None})


@app.post("/uidai-mock/lock", response_class=HTMLResponse)
def uidai_lock_submit(request: Request, uid_last4: str = Form(""), captcha: str = Form("")):
    if captcha.strip().upper() != "K7Q2X" or not (uid_last4.isdigit() and len(uid_last4) == 4):
        return templates.TemplateResponse(
            request, "uidai_lock.html",
            {"error": "Enter the last 4 digits and the captcha shown (K7Q2X)."})
    return templates.TemplateResponse(request, "uidai_otp.html", {"last4": uid_last4})
