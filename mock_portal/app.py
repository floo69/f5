"""Local synthetic registry portal. Never connects to a real registry."""

from __future__ import annotations

import math
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .seed import seed_portal

app = FastAPI(title="ThumbShield Mock Registry Portal — Synthetic Only")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_manifest: dict | None = None


def data() -> dict:
    global _manifest
    if _manifest is None:
        _manifest = seed_portal()
    return _manifest


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "synthetic_only": True, "records": len(data()["records"])}


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "terms.html", {"title": "Terms"})


@app.post("/agree")
def agree(agree: str = Form(default="")):
    response = RedirectResponse("/search", status_code=303)
    if agree == "on":
        response.set_cookie("terms_accepted", "1", httponly=True, samesite="lax")
    return response


@app.get("/search")
def search(request: Request, page: int = Query(1, ge=1), sro: str = "", year: int | None = Query(None, ge=2000, le=2100), document_number: str = "", party_name: str = ""):
    if request.cookies.get("terms_accepted") != "1":
        return templates.TemplateResponse(request, "terms.html", {"title": "Terms"})
    all_rows = data()["records"]
    rows = [r for r in all_rows if (not sro or r["sro"] == sro) and (not year or r["year"] == year) and (not document_number or document_number.lower() in r["doc_no"].lower()) and (not party_name or party_name.lower() in r["party_name"].lower())]
    total_pages = max(1, math.ceil(len(rows) / 10))
    page = min(page, total_pages)
    shown = rows[(page - 1) * 10 : page * 10]
    return templates.TemplateResponse(request, "search.html", {
        "title": "E-search", "rows": shown, "page": page, "total_pages": total_pages,
        "sros": sorted({r["sro"] for r in all_rows}), "years": sorted({r["year"] for r in all_rows}),
        "filters": {"sro": sro, "year": year or "", "document_number": document_number, "party_name": party_name},
    })


@app.get("/deed/{doc_id}")
def detail(request: Request, doc_id: str):
    record = next((r for r in data()["records"] if r["doc_id"] == doc_id), None)
    if record is None:
        return templates.TemplateResponse(request, "not_found.html", {"title": "Not found"}, status_code=404)
    return templates.TemplateResponse(request, "detail.html", {"title": doc_id, "record": record})


@app.get("/deed/{doc_id}/pdf")
def pdf(doc_id: str):
    record = next((r for r in data()["records"] if r["doc_id"] == doc_id), None)
    if record is None:
        return RedirectResponse("/search", status_code=303)
    return FileResponse(Path(record["pdf"]), media_type="application/pdf", filename=f"{doc_id}.pdf")
