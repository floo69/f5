# ThumbShield — project brief

```
PROJECT: ThumbShield — defensive privacy tool for Indian land-registration documents.

PROBLEM: Fraudsters copy thumb impressions from publicly available land sale deeds, make
silicone/rubber fingerprint clones, and drain Aadhaar-linked bank accounts through AePS
point-of-sale machines. Police have reported this in Haryana (Palwal), Bihar and West Bengal; Kolkata police
asked the state to mask fingerprints and Aadhaar numbers on registration websites.

WHAT WE BUILD: (1) detect + truly redact thumb impressions and Aadhaar numbers in deed PDFs
BEFORE publication, on-device; (2) audit deeds ALREADY published on a (mock) registry portal
with an agentic browser; (3) multi-agent layer that triages, reviews and drafts notices.

HARD RULES
- Defensive only. Never build anything that extracts, enhances, stores or exports fingerprint
  images for reuse. Detected fingerprint regions are only ever destroyed (redacted) or shown
  blurred/pixelated in the UI. Never save crops of fingerprints to disk. Review images that
  go to an LLM must be the page with the region pixelated, plus bbox coordinates.
- Synthetic data only. All deeds, names, Aadhaar numbers, fingerprints are generated. Every
  synthetic PDF carries a visible "SYNTHETIC SAMPLE – NOT A REAL DOCUMENT" watermark.
- The browser agent may ONLY access hosts in an allowlist (default: localhost:8100, the mock
  portal). Enforce in code, not just in the prompt.
- LLMs never decide that something is safe. Deterministic detectors + rules decide. An LLM
  may only ESCALATE (add a redaction / send to review), never remove one.
- Fail closed: if verification after redaction finds anything, or OCR quality is too low
  to verify absence, the page becomes BLOCK_FOR_REVIEW.

STACK
- Python 3.11, uv for env management. FastAPI backend. PyMuPDF (fitz) for PDF render/redact.
  OpenCV + NumPy for classical vision. pytesseract + Tesseract (eng + mal traineddata) for OCR.
  onnxruntime for the edge model. ultralytics YOLOv8n only for training/export (AGPL-3.0 —
  fine for a hackathon, note it in README). reportlab + Faker(en_IN) for synthetic deeds.
- MCP: official `mcp` Python SDK (FastMCP) for our servers; `npx @playwright/mcp@latest`
  for browser automation.
- Claude: official `anthropic` Python SDK with the MCP extra (`anthropic[mcp]`). Use the beta tool
  runner (`client.beta.messages.tool_runner`) and the MCP conversion helpers
  (`from anthropic.lib.tools.mcp import async_mcp_tool`) to hand local stdio MCP server tools
  to Claude. Do NOT use the remote `mcp_servers` connector (our servers are local stdio).
  Models come from env: ORCHESTRATOR_MODEL (default "claude-opus-5-5"), WORKER_MODEL (default
  "claude-opus-5-5"; set "claude-haiku-5-5" to save credits). Exact IDs, no date suffixes.
  Opus 5.5: don't send budget_tokens or thinking:{type:"disabled"} (400); set
  output_config={"effort": ...} explicitly (default is medium); never use forced tool_choice
  any/tool (400) — use auto + clear instructions. Always check stop_reason (handle "refusal")
  before reading content. Enable server-side refusal fallback
  (betas=["server-side-fallback-2026-07-01"], fallbacks="default") on Opus calls if the SDK
  version accepts it; otherwise handle refusal explicitly.
- Frontend: React + Vite + TypeScript + Tailwind. Server-sent events for live agent timelines.

REPO LAYOUT
thumbshield/
  backend/app/{main.py, api/, core/, pipeline.py, settings.py}
  backend/app/core/{verhoeff.py, aadhaar.py, ocr.py, fp_classical.py, fp_onnx.py,
                    fusion.py, redact.py, verify.py, decision.py, report.py}
  mcp_servers/{scanner_server.py, casestore_server.py, policy_server.py}
  agents/{runner.py, orchestrator.py, auditor.py, reviewer.py, notice.py, prompts/}
  mock_portal/  (FastAPI + Jinja2, port 8100)
  synth/{fingerprint_gen.py, deed_gen.py, make_dataset.py}
  ml/{train_yolo.py, export_onnx.py, eval_detector.py}
  frontend/
  tests/
  data/ (gitignored: inbox/, out/, datasets/, models/)
  docs/{BRIEF.md, ARCHITECTURE.md, DEMO.md}
```
