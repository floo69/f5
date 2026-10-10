"""Primary deterministic V5 demo runner. Safe reset only removes data/demo-data."""
from __future__ import annotations
import argparse, json, os, shutil, socket, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
DEMO_ROOT = ROOT / "data" / "demo-data"
MARKER = DEMO_ROOT / ".thumbshield-demo-root"


def _seed_documents() -> dict:
    from synth.deed_gen import generate_deed
    target = DEMO_ROOT / "documents"; target.mkdir(parents=True, exist_ok=True)
    selected = []
    seed = 910000
    while len(selected) < 2:
        mode = "born_digital" if not selected else "scanned"
        pdf, gt, _ = generate_deed(seed, "val", mode, n_pages=1, doc_id=f"V5-{len(selected)+1}")
        types = {a["type"] for a in gt["annotations"]}
        if len(selected) == 0 and {"FINGERPRINT", "AADHAAR", "MASKED_AADHAAR"}.issubset(types) and sum(a["type"] == "FINGERPRINT" for a in gt["annotations"]) >= 2:
            name = "document-a-born-digital.pdf"; selected.append((name, pdf, gt, mode))
        elif len(selected) == 1 and "FINGERPRINT" in types and "AADHAAR" in types:
            name = "document-b-scanned-style.pdf"; selected.append((name, pdf, gt, mode))
        seed += 1
    records = []
    for name, pdf, gt, mode in selected:
        path = target / name; path.write_bytes(pdf); records.append({"path": str(path), "mode": mode, "ground_truth": gt})
    (DEMO_ROOT / "ground_truth.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return {"documents": records, "seed_start": 910000}


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _start_services() -> list[subprocess.Popen]:
    processes = []
    for port, module in ((8100, "mock_portal.app:app"), (8000, "backend.app.main:app")):
        if _port_open(port): continue
        processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not all(_port_open(p) for p in (8000, 8100)): time.sleep(.2)
    return processes


def run(reset: bool = False, start_services: bool = True) -> dict:
    if reset:
        if DEMO_ROOT.exists() and not MARKER.exists(): raise RuntimeError("refusing reset: demo marker is missing")
        if DEMO_ROOT.exists(): shutil.rmtree(DEMO_ROOT)
    DEMO_ROOT.mkdir(parents=True, exist_ok=True); MARKER.write_text("ThumbShield V5 demo data only\n", encoding="utf-8")
    os.environ["THUMBSHIELD_DATA_ROOT"] = str(DEMO_ROOT)
    os.environ["THUMBSHIELD_DB_PATH"] = str(DEMO_ROOT / "cases.db")
    seeded = _seed_documents()
    from mock_portal.seed import seed_portal
    portal = seed_portal()
    processes = _start_services() if start_services else []
    outcomes = []
    from backend.app.pipeline import process_pdf
    from mcp_servers.casestore_server import register_document, record_scan
    for item in seeded["documents"]:
        payload = Path(item["path"]).read_bytes(); doc_id = Path(item["path"]).stem
        started = time.monotonic()
        try:
            result, redacted = process_pdf(payload, doc_id=doc_id)
            out = DEMO_ROOT / "out" / doc_id; out.mkdir(parents=True, exist_ok=True); (out / "redacted.pdf").write_bytes(redacted)
            registered = register_document("http://127.0.0.1:8100/demo/" + doc_id, "Demo SRO", 2025, doc_id, item["path"])
            record_scan(registered, result.model_dump())
            outcomes.append({"document": doc_id, "status": result.status, "verification": result.verification.status, "processing_ms": round((time.monotonic()-started)*1000, 1), "pages": result.page_count})
        except Exception as exc:
            outcomes.append({"document": doc_id, "status": "BLOCKED_FOR_REVIEW", "error": str(exc), "processing_ms": round((time.monotonic()-started)*1000, 1)})
    report = {"synthetic_only": True, "portal_records": len(portal["records"]), "documents": outcomes, "services": {"api": "http://127.0.0.1:8000", "portal": "http://127.0.0.1:8100", "frontend": "start separately with npm run dev"}, "optional_llm": bool(os.getenv("ANTHROPIC_API_KEY")), "network_measurement": "Not instrumented outside the explicitly started local services"}
    (DEMO_ROOT / "demo-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2)); return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--reset", action="store_true"); parser.add_argument("--no-start-services", action="store_true")
    args = parser.parse_args(); run(args.reset, not args.no_start_services)
