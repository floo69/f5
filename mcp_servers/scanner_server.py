"""Scanner MCP server backed by the V2 scan/redaction/verification pipeline."""
from __future__ import annotations

import base64, hashlib, io, json, os, re
from pathlib import Path

import pymupdf as fitz
from mcp.server.mcpserver import MCPServer
from PIL import Image

from backend.app.core.decision import DecisionRequest, decide
from backend.app.pipeline import process_pdf

mcp = MCPServer("thumbshield-scanner")
DATA_ROOT = Path(os.getenv("THUMBSHIELD_DATA_ROOT", "data")).resolve()
CASE_ROOT = DATA_ROOT / "out" / "cases"


def _safe(path: str | Path) -> Path:
    raw = Path(path)
    if raw.suffix.lower() != ".pdf":
        raise ValueError("only PDF files are supported")
    resolved = raw.resolve(strict=False)
    if resolved != DATA_ROOT and DATA_ROOT not in resolved.parents:
        raise ValueError("path must resolve inside data/")
    if not resolved.is_file() or resolved.read_bytes()[:5] != b"%PDF-":
        raise ValueError("missing file or invalid PDF signature")
    return resolved


def _run(path: Path) -> dict:
    payload = path.read_bytes()
    doc_id = hashlib.sha256(payload).hexdigest()[:12]
    result, redacted = process_pdf(payload, doc_id=doc_id)
    case = CASE_ROOT / doc_id
    case.mkdir(parents=True, exist_ok=True)
    (case / "input.pdf").write_bytes(payload)
    (case / "result.json").write_text(json.dumps(result.model_dump(), default=str), encoding="utf-8")
    return {"result": result.model_dump(), "redacted_pdf": redacted}


def _finding(f: dict) -> dict:
    return {"type": f.get("type"), "confidence": f.get("confidence"), "source": f.get("source"),
            "bbox_pt": f.get("bbox_pt"), "value_masked": f.get("value_masked"), "redact": f.get("redact", True)}


def _public(result: dict) -> dict:
    result = result["result"]
    return {"doc_id": result["doc_id"],
            "pages": [{"page": p["page"], "findings": [_finding(f) for f in p["findings"]],
                        "decision": p.get("decision"), "system_one": p.get("system_one")} for p in result["pages"]],
            "verification": result.get("verification"), "decision": result.get("decision"),
            "detector_mode": result.get("detector_mode"), "detector_status": result.get("detector_status")}


@mcp.tool()
def scan_pdf(path: str) -> dict:
    """Scan a data-local PDF and return masked findings only."""
    return _public(_run(_safe(path)))


@mcp.tool()
def redact_pdf(path: str) -> dict:
    """Permanently redact a data-local PDF and report verification honestly."""
    result = _run(_safe(path))
    case = CASE_ROOT / result["result"]["doc_id"]
    out, certificate = case / "redacted.pdf", case / "certificate.json"
    out.write_bytes(result["redacted_pdf"])
    result_data = result["result"]
    certificate.write_text(json.dumps({"doc_id": result_data["doc_id"], "sha256_in": result_data["sha256_in"], "sha256_out": result_data["sha256_out"], "verification": result_data["verification"]}, indent=2), encoding="utf-8")
    verification = result_data.get("verification", {}).get("status")
    return {"doc_id": result_data["doc_id"], "out_path": str(out), "certificate_path": str(certificate),
            "verification": verification, "status": "redacted" if verification == "pass" else "blocked"}


@mcp.tool()
def verify_pdf(path: str) -> dict:
    """Run the independent verification stage on a data-local PDF."""
    result = _run(_safe(path))
    result_data = result["result"]
    return {"doc_id": result_data["doc_id"], "status": result_data.get("verification", {}).get("status"), "problems": result_data.get("verification", {}).get("problems", [])}


@mcp.tool()
def decide_page(request: dict) -> dict:
    """Apply the typed V2 decision engine; callers cannot downgrade controls."""
    return decide(DecisionRequest.model_validate(request)).model_dump()


@mcp.tool()
def get_review_view(doc_id: str, page: int) -> dict:
    """Return a safe review PNG: fingerprint pixels are blurred and other sensitive boxes blacked."""
    if not re.fullmatch(r"[0-9a-f]{12}", doc_id):
        raise ValueError("invalid document id")
    result_path, input_path = CASE_ROOT / doc_id / "result.json", CASE_ROOT / doc_id / "input.pdf"
    if not result_path.exists() or not input_path.exists():
        raise ValueError("unknown document")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if page < 0 or page >= len(result["pages"]):
        raise ValueError("page out of range")
    doc = fitz.open(input_path); pix = doc[page].get_pixmap(dpi=120, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples); scale = 120 / 72; boxes = []
    for finding in result["pages"][page]["findings"]:
        box = finding.get("bbox_pt")
        if not box: continue
        x0, y0, x1, y1 = [max(0, int(float(x) * scale)) for x in box]
        x1, y1 = min(image.width, x1), min(image.height, y1)
        if finding.get("type") == "FINGERPRINT":
            crop = image.crop((x0, y0, x1, y1)); crop = crop.resize((max(1, crop.width // 12), max(1, crop.height // 12))).resize(crop.size, Image.Resampling.NEAREST); image.paste(crop, (x0, y0))
        else: image.paste((0, 0, 0), (x0, y0, x1, y1))
        boxes.append({"type": finding.get("type"), "bbox_pt": box, "confidence": finding.get("confidence"), "source": finding.get("source")})
    doc.close(); buf = io.BytesIO(); image.save(buf, format="PNG")
    return {"doc_id": doc_id, "page": page, "png_base64": base64.b64encode(buf.getvalue()).decode(), "bboxes": boxes}


if __name__ == "__main__":
    mcp.run()
