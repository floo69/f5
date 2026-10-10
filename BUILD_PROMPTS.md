# ThumbShield — versioned build prompts (v0 → v5)

How to use this file:
1. Paste **Prompt v0** into Claude Code (or another coding agent) from the repo root. It scaffolds the project and writes `CLAUDE.md` with the project brief, so later prompts stay short.
2. After each version: run the tests, commit, and tag (`git tag v1` …). Only move on once the "Done when" checklist passes.
3. If you fall behind, follow the **cut-line** at the bottom. v1 + v2 on their own already make a demoable, defensible project.

### Parallel tracks (team of 3–4)
- **Person A (core):** v0 → v1 → v2 detectors/decision.
- **Person B (ML):** as soon as v0 finishes (~hour 2), start YOLO training on the cloud GPU (v2 §1) **in the background**, so training is off the critical path. If training fails, ship the classical detector and keep retrying. The edge-model checkbox needs the ONNX model, so protect this track.
- **Person C (web):** React shell (v1 §9) and the mock portal (v3 §1) from hour 2; neither depends on the detectors.
- **Person D (agents/pitch):** MCP servers (v3 §2–4) against stub scanner functions from hour 4, then agents (v4), demo script, slides.

Expected tech covered (5 of 6, each where it fits naturally):

| Tech | Where it lives in ThumbShield | Version |
|---|---|---|
| **Edge model** | ONNX thumbprint detector + local OCR running on the clerk's machine. Documents never leave the device. | v2 (v5 stretch: runs inside the browser) |
| **System-One decision** | Per-page PUBLISH / REDACT_AND_PUBLISH / BLOCK_FOR_REVIEW decision engine, typed-question interface, under 5 ms, rules-first; Jev adapter optional | v2 |
| **MCP** | 3 of our own MCP servers (scanner, case-store, policy) + Microsoft's Playwright MCP | v3 |
| **Agentic browser** | Auditor agent drives a *mock* land-registry portal through Playwright MCP to find deeds that are already exposed | v3 |
| **Multi-agent** | Orchestrator → Auditor, Reviewer, Notice agents | v4 |
| Ultra-low-latency voice | **Skipped on purpose.** No natural user moment needs real-time voice. Don't force it. | — |

---

## Shared project brief (v0 writes this into CLAUDE.md; paste it on top of any prompt if your agent has no memory)

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

---

## Prompt v0 — scaffold + synthetic data (Hours 0–2)

```
Read the PROJECT BRIEF below and follow its hard rules for this and all future tasks.
[paste the shared project brief]

TASK v0: scaffold the repo and build the synthetic data generators.

1. Scaffolding
   - Create the repo layout from the brief. pyproject.toml managed with uv (Python 3.11).
     Deps: fastapi, uvicorn[standard], pymupdf, opencv-python-headless, numpy, pillow,
     pytesseract, reportlab, faker, pydantic>=2, pydantic-settings, onnxruntime, jinja2,
     python-multipart, sse-starlette, mcp, "anthropic[mcp]", httpx, pytest, ruff.
     Separate optional group "train": ultralytics.
   - Write CLAUDE.md containing the full project brief plus: how to run tests (`uv run
     pytest -q`), lint (`uv run ruff check .`), and start services (Makefile targets:
     `make api`, `make portal`, `make web`, `make test`, `make data`).
   - .gitignore: data/, *.onnx, *.pt, node_modules, .env. Add .env.example with
     ANTHROPIC_API_KEY, ORCHESTRATOR_MODEL, WORKER_MODEL, BROWSER_ALLOWLIST, JEV_* (blank).
   - `make doctor`: check that `tesseract --list-langs` includes eng and mal (else print
     `sudo apt install tesseract-ocr-mal`), Node >= 20, and that a Playwright Chromium is
     installed (else print `npx playwright install chromium`).

2. synth/fingerprint_gen.py — procedural SYNTHETIC thumb impressions (no real datasets)
   - Orientation field from singular points (Sherlock–Monro style: 1 core + 0–2 deltas,
     plus arch/loop/whorl presets). Ridge frequency 1/7–1/11 px (randomised).
   - Grow ridges by iterated oriented Gabor filtering of random noise (8–15 iterations),
     binarise softly, crop to an elliptical thumb mask (aspect 0.65–0.8).
   - "Ink impression" effects: uneven pressure (low-frequency multiplicative noise),
     smudge/blur, partial/clipped prints, ink bleed (dilation), faded prints,
     purple/blue/black ink colours, random rotation ±35°, scale 120–260 px tall at 200 dpi.
   - Deterministic with a seed. Function: generate(seed, style) -> RGBA numpy image.

3. synth/deed_gen.py — synthetic Kerala-style sale deeds
   - reportlab PDF, A4/legal. Header "SALE DEED (SYNTHETIC SAMPLE)", SRO name (pick from a
     list of Kerala sub-registry office names), document number "1234/2019" style,
     executant/claimant names (Faker en_IN), survey numbers, schedule of property,
     witness blocks, some Malayalam paragraphs (bundle Noto Sans Malayalam font in
     synth/fonts/, OFL licence).
   - Boxes captioned "Left thumb impression of executant" / "LTI" with 0–4 synthetic
     thumbprints per page; some pages with none.
   - Aadhaar numbers in text, generated Verhoeff-valid with first digit 2–9, formats:
     "2345 6789 0124", "234567890124", "2345-6789-0124"; some already masked
     ("XXXX XXXX 0124"); some 16-digit VIDs; also DECOYS that must NOT match: 12-digit
     numbers with a bad checksum, phone numbers, survey numbers, dates.
   - HARD NEGATIVES on pages: handwritten-looking signatures, round rubber-stamp seals,
     guilloche/textured stamp-paper backgrounds, QR codes, passport photos (use flat
     generated face-like placeholders, not real faces), wavy security lines.
   - Two output modes: (a) "born-digital" (text layer present), (b) "scanned" — render
     page to image, add skew ±2°, JPEG artefacts, blur, noise, yellowing, then wrap the image
     back into a PDF with NO text layer.
   - Visible diagonal watermark "SYNTHETIC SAMPLE – NOT A REAL DOCUMENT" on every page.
   - Emit ground-truth JSON per document: page, type (FINGERPRINT|AADHAAR|VID|
     MASKED_AADHAAR|DECOY_NUMBER), bbox in PDF points and in 200-dpi pixels.

4. synth/make_dataset.py + `make data`
   - Generate data/datasets/deeds/{train,val,test}: 300/60/60 documents (1–4 pages each).
     The test split uses DIFFERENT seeds AND held-out style parameters (e.g. ink colours
     and blur levels unseen in train) so later evaluation is honest.
   - Also export YOLO-format page images + labels (class 0 = fingerprint) for v2.

5. tests/
   - test_verhoeff.py (known-good/known-bad vectors; property test: every generated
     number validates, every single-digit mutation fails).
   - test_synth.py: generator determinism with a seed; ground-truth bboxes lie inside page.

DONE WHEN: `make data` produces the dataset + ground truth in < 5 min on a laptop;
`make test` passes; opening 3 random PDFs shows watermarks, thumbprints, Aadhaar numbers,
decoys and hard negatives. Commit as "v0: scaffold + synthetic data".
```

---

## Prompt v1 — deterministic core MVP: detect → truly redact → verify (Hours 2–6)

```
Read CLAUDE.md. Implement v1: the deterministic core plus a minimal UI. No LLMs in this version.

1. backend/app/core/verhoeff.py — Verhoeff checksum (validate + compute check digit).

2. backend/app/core/ocr.py
   - get_words(page) -> list[Word(text, bbox_pt, conf, line_id)].
     If the page has a text layer (PyMuPDF page.get_text("words")) use it; otherwise render
     at 300 dpi and run pytesseract image_to_data(lang="eng+mal"), mapping pixel bboxes
     back to PDF points.
   - Return page-level ocr_quality = mean word confidence over alphanumeric words (0–1),
     and a flag text_layer: bool.

3. backend/app/core/aadhaar.py
   - Join adjacent digit tokens on the same line (handles "2345 6789 0124" split into 3
     words and "2345-6789-0124").
   - AADHAAR: exactly 12 digits, first digit 2–9, Verhoeff-valid. Confidence boost if
     context keywords within 40 chars: "Aadhaar", "Aadhar", "UID", "ആധാർ".
   - VID: 16 digits Verhoeff-valid, near "VID".
   - MASKED_AADHAAR: "XXXX XXXX dddd" / "xxxx-xxxx-dddd" → compliant, record but don't redact.
   - Never flag numbers that fail Verhoeff (decoys) — test this against ground truth.
   - Output Finding(type, bbox_pt, page, confidence, source="ocr"|"textlayer",
     value_masked="XXXX XXXX 0124") — NEVER store or log full numbers anywhere.

4. backend/app/core/fp_classical.py — classical (non-ML) thumbprint detector
   - Render page at 200 dpi grayscale. Compute structure-tensor orientation coherence and
     Gabor filter-bank energy at ridge frequencies 1/6–1/12 px over 16×16 blocks.
   - Candidate blocks: high coherence AND high Gabor energy AND ridge-frequency
     consistency; morphological close; connected components; keep blobs whose size and
     aspect match a thumb impression (≈ 0.4–1.6 inch tall, aspect 0.5–0.95).
   - Score = f(mean coherence, energy, ridge-frequency stability, ellipse fit). Return
     Finding(type="FINGERPRINT", bbox_pt, confidence, source="classical").
   - Tune thresholds on the VAL split only. Prioritise RECALL: missing a print is worse than
     over-redacting a stamp.

5. backend/app/core/redact.py — TRUE redaction (not overlays)
   - For each finding: pad the bbox (fingerprints +8 pt, numbers +2 pt), then
     page.add_redact_annot(rect, fill=(0,0,0)) and apply with
     page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS) so the underlying image
     pixels and text are removed, not just covered. (Check the installed PyMuPDF version's
     API and adapt if the constant name differs.)
   - Draw a small label in the box: "THUMB IMPRESSION REDACTED" / "AADHAAR REDACTED".
   - Strip metadata (set_metadata({}), del XMP), remove annotations/attachments/JS,
     save with garbage=4, deflate=True, clean=True.

6. backend/app/core/verify.py — fail-closed verification
   - Re-open the redacted PDF, re-run text extraction + OCR + fp_classical on it.
   - Any AADHAAR/VID/FINGERPRINT finding outside an already-redacted rectangle → FAIL.
   - Also assert: no text inside redacted rects (page.get_text("text", clip=rect) empty).

7. backend/app/pipeline.py + report.py
   - process_pdf(path) -> Result {doc_id, sha256_in, sha256_out, pages: [{findings, decision
     (temporary rule: findings→REDACT, low ocr_quality on scanned page→REVIEW, else
     PUBLISH), timings_ms}], verification: pass/fail, out_path}
   - "Redaction certificate" JSON + a one-page PDF summary (counts, page list, hashes,
     detector versions, timestamps). No full numbers, no fingerprint images in it.

8. FastAPI (backend/app/main.py)
   - POST /api/process (multipart PDF) -> Result JSON; GET /api/files/{id}/redacted;
     GET /api/files/{id}/certificate; GET /api/files/{id}/page/{n}.png?view=before|after
     — the "before" view must PIXELATE fingerprint bboxes (mosaic 12 px) and draw red
     outlines; it must never serve a clean fingerprint image.
   - CORS for the Vite dev server. Everything runs locally; add a startup log line
     "ThumbShield running locally — no document leaves this machine".

9. Frontend (frontend/, React + Vite + TS + Tailwind)
   - Single page: drag-and-drop PDF → progress → side-by-side Before (pixelated + red boxes)
     / After (black redactions) per page, with a page strip, finding chips per page
     ("2 thumbprints · 1 Aadhaar · 1 masked (OK)"), timings, verification badge
     (green "Verified clean" / red "Blocked for review"), download buttons.
   - Clean, government-friendly look; header "ThumbShield — Protect citizens' biometrics
     before you publish".

10. Evaluation: ml/eval_detector.py --detector classical --split test
    - Per-class precision/recall/F1 at IoU ≥ 0.3 against ground truth; print a table and
      save docs/metrics_v1.md. Separate numbers for born-digital vs scanned.

11. Tests: unit tests for aadhaar (decoys rejected, masked recognised, split tokens
    joined), redact (after redaction no text/pixels remain in rect — sample pixel variance
    inside rect == 0), verify (a deliberately unredacted PDF fails), API smoke test.

12. Latency: log per-stage timings (render, text/OCR, detector, redact, verify). Speed-ups:
    OCR only on pages without a text layer; run the Gabor bank on a 100-dpi downscale to find
    candidates, then confirm at 200 dpi; process pages in a thread pool.

DONE WHEN: uploading a synthetic scanned deed shows correct boxes and a verified clean
output; born-digital page pipeline p50 < 1 s and scanned p50 measured and recorded in
docs/metrics_v1.md; Aadhaar recall = 100% and decoy false positives = 0 on born-digital test docs;
fingerprint recall on test ≥ 0.90 (classical) recorded in docs/metrics_v1.md; all tests
pass. Commit "v1: deterministic core".
```

---

## Prompt v2 — edge model + System-One decision engine (Hours 6–10)

```
Read CLAUDE.md. Implement v2: on-device ML thumbprint detector fused with the classical one,
and a System-One decision engine with a typed-question interface.

1. Training (runs on a cloud GPU VM using our credits; also runnable on CPU for a smoke test)
   - ml/train_yolo.py: YOLOv8n, imgsz 960, class "fingerprint", trained on
     data/datasets/yolo (from v0). Heavy augmentation: rotation, blur, JPEG, HSV ink
     shifts, mosaic. Early stopping on val. Log mAP50 and recall.
   - docs/GPU.md: exact steps for a spot GPU VM on GCP (L4 or T4) or Azure (NC T4), with an
     image that has CUDA + PyTorch; rsync dataset up, train, rsync best.pt back, SHUT THE VM
     DOWN (include the command). Note the expected cost as "check the console price
     before starting".
   - ml/export_onnx.py: export to ONNX (opset 17, imgsz 960, dynamic=False), then dynamic INT8
     quantisation with onnxruntime.quantization; save data/models/thumb_det_int8.onnx and
     the FP32 one. Record file sizes.

2. backend/app/core/fp_onnx.py
   - onnxruntime CPU session (no torch at inference time). Letterbox preprocessing, NMS
     in NumPy. Return Finding(source="onnx", confidence).
   - Benchmark: ms/page at 200 dpi on this laptop for FP32 vs INT8; write to docs/metrics_v2.md.

3. backend/app/core/fusion.py
   - Merge classical + onnx findings by IoU ≥ 0.3. Fused confidence = max, with a +0.1
     agreement bonus when both fire. Keep single-detector findings (recall first).

4. backend/app/core/decision.py — System-One decision engine
   - Typed interface (pydantic):
     DecisionRequest {doc_id, page, text_layer: bool, ocr_quality: float,
       findings: [{type, confidence, sources[], area_ratio}],
       verification: "pass"|"fail"|"not_run"}
     DecisionResponse {action: "PUBLISH"|"REDACT_AND_PUBLISH"|"BLOCK_FOR_REVIEW",
       confidence: float, reasons: [str], backend: str, latency_ms: float}
   - Backend protocol `DecisionBackend.decide(req) -> DecisionResponse`.
   - RulesBackend (default, deterministic):
       verification == "fail"                       → BLOCK_FOR_REVIEW
       any AADHAAR/VID or FINGERPRINT conf ≥ 0.35   → REDACT_AND_PUBLISH
       scanned page AND ocr_quality < 0.55          → BLOCK_FOR_REVIEW (can't prove absence)
       FINGERPRINT 0.20–0.35 single-source          → REDACT_AND_PUBLISH + reason "low-conf, redacted fail-safe"
       else                                         → PUBLISH
     Thresholds in settings; tune on VAL only.
   - JevBackend (optional, OFF by default): TypeSafe AI's "Jev" System-One model, reached
     via a gateway (OpenRouter / Vercel AI Gateway) if credentials exist in JEV_* env vars.
     Do NOT guess the API: implement only if you can read the gateway's current docs;
     otherwise leave a stub that raises NotConfigured. Its answer goes through the SAME
     hard-rule guard: Jev may upgrade an action toward safety (PUBLISH→REDACT→BLOCK) but
     can never downgrade one. Timeout 300 ms → fall back to RulesBackend.
   - Measure decide() latency (target < 5 ms for rules); return latency_ms.

5. Pipeline update: fused detection → decision per page → redact only REDACT pages →
   verify → if verify fails, re-decide with verification="fail" (→ BLOCK). Document-level
   status = worst page status.

6. UI updates
   - Per-page decision chip + reasons tooltip; a "System-One latency" meter showing
     decide() ms and a separate "full page pipeline" ms (be honest — both visible).
   - "Edge mode" badge: "Model: thumb_det_int8.onnx · 2.9 MB · runs on this device".
     Add an "Offline check" that calls a backend endpoint confirming no outbound network
     is needed (the backend doesn't call any external service during /api/process).
   - Settings drawer: detector = classical | onnx | fused; decision backend = rules | jev.

7. Evaluation: eval_detector.py for classical, onnx, fused on TEST; decision-level metrics:
   % of ground-truth sensitive pages that ended up PUBLISH unredacted (MUST be 0 on test),
   % over-redaction (pages redacted with no ground-truth item). Save docs/metrics_v2.md.

8. Tests: decision rules table tests (every branch), "Jev can't downgrade" test with a fake
   backend, fusion IoU tests, ONNX session loads and returns boxes on a fixture page.

DONE WHEN: fused recall on test ≥ 0.98 for thumbprints, 0 sensitive pages published
unredacted, decide() p95 < 5 ms, INT8 model < 10 MB and < 400 ms/page on the laptop CPU (record
actual numbers even if they miss). Works with Wi-Fi off. Commit "v2: edge model + System-One".
```

---

## Prompt v3 — MCP servers + mock registry portal + agentic browser audit (Hours 10–14)

```
Read CLAUDE.md. Implement v3: expose ThumbShield as MCP servers, build a mock registry
portal, and an Auditor agent that browses it with Playwright MCP to find already-published
deeds that expose thumbprints/Aadhaar.

1. mock_portal/ (FastAPI + Jinja2, port 8100) — clearly a MOCK
   - Red banner on every page: "MOCK PORTAL — SYNTHETIC DATA — FOR THUMBSHIELD DEMO".
   - Looks like a typical state registration e-search: search form (SRO office dropdown,
     year, document number, party name), results table with pagination (10/page),
     detail page per deed with metadata and a "View document (PDF)" link.
   - Seed it with ~120 synthetic deeds from v0 (mix: ~30% clean, ~40% exposing thumbprints,
     ~20% exposing Aadhaar, ~10% already masked).
   - A simple "I agree to terms" checkbox gate before results (to show the agent handles real
     UI flows). NO CAPTCHA — we never build CAPTCHA bypass.
   - Bind to 127.0.0.1 only.

2. mcp_servers/scanner_server.py (FastMCP, stdio)
   Tools (clear docstrings — they become the tool descriptions):
   - scan_pdf(path: str) -> {doc_id, pages:[{page, findings(masked values only), decision}]}
   - redact_pdf(path: str) -> {out_path, certificate_path, verification}
   - verify_pdf(path: str) -> {status, problems[]}
   - decide_page(request: DecisionRequest JSON) -> DecisionResponse
   - get_review_view(doc_id: str, page: int) -> PNG (fingerprint regions PIXELATED,
     Aadhaar boxes blacked) + bbox list. Never returns a clean fingerprint.
   All paths must resolve inside data/ (path-traversal guard).

3. mcp_servers/casestore_server.py (FastMCP, stdio, SQLite data/cases.db)
   - register_document(source_url, sro, year, doc_no, local_path) -> doc_id
   - record_scan(doc_id, summary) ; list_exposed(sro?: str, year?: int) -> rows
   - stats() -> counts by type/SRO/year
   - save_notice_draft(kind: "registry_takedown"|"citizen_advisory", lang, body, doc_ids)
   - Hash-chained audit log table (each row stores sha256(prev_hash + row_json)); tool
     verify_audit_chain() -> ok/broken_at.

4. mcp_servers/policy_server.py (FastMCP, stdio)
   - get_policy(name) -> redaction policy (what to redact, padding, thresholds).
   - legal_references() -> short reference texts loaded from docs/legal_refs.md, which you
     write as clearly-labelled summaries with "verify current wording" notes (Aadhaar Act
     2016 and UIDAI rules on not publishing Aadhaar numbers; CERT-In/I4C advisories on
     masking biometrics in public land records). Don't invent section numbers — if unsure,
     write the summary without a section number.

5. agents/runner.py — shared helper
   - Async context manager that starts given stdio MCP servers (mcp.client.stdio
     stdio_client + ClientSession), lists tools, converts them with
     anthropic.lib.tools.mcp.async_mcp_tool, and runs
     client.beta.messages.tool_runner(model=..., max_tokens=16000, tools=[...],
     messages=[...], output_config={"effort": ...}) iterating with `async for`.
   - Mirror the conversation history yourself; if the last message has
     stop_reason == "pause_turn", restart the runner with the history (see SDK docs).
   - If stop_reason == "refusal", log stop_details and return a structured failure.
   - Emit every step (tool name, short args summary, result summary, timestamps) to an
     asyncio.Queue so the API can stream it over SSE.

6. agents/auditor.py — Auditor agent (agentic browser)
   - MCP servers: Playwright MCP (`npx @playwright/mcp@latest --headless` for runs,
     headed for the demo) + casestore + scanner.
   - The browser FINDS deed links; it does not need to download them. Add a
     casestore tool fetch_pdf(url) -> local_path (httpx, same allowlist enforced in code,
     content-type must be application/pdf, size cap 25 MB, saves under data/inbox/). This avoids
     depending on Playwright MCP's download behaviour, which varies by version.
   - Enforce the BROWSER_ALLOWLIST in code: wrap the Playwright navigate tool, or run Playwright MCP
     with its allowed-origins option if your version supports it, AND reject any tool call
     whose URL host isn't allowlisted before forwarding.
   - System prompt (agents/prompts/auditor.md): goal = for a given SRO + year range, search
     the portal, page through results, open each deed, download the PDF into
     data/inbox/<sro>/<year>/, register it in casestore, run scanner.scan_pdf, record the
     result. Be polite: ≤ 1 request/sec. Stop at max_docs. Return a summary.
   - Pragmatic fallback for speed: agents/bulk_crawl.py — a deterministic Python Playwright
     crawler for large batches. The LLM agent handles the live demo and odd UI flows. Document
     this split honestly in docs/ARCHITECTURE.md.

7. API + UI
   - POST /api/audit {sro, year_from, year_to, max_docs} → starts the Auditor; GET
     /api/audit/{id}/events (SSE) streams steps; include periodic Playwright screenshots
     (downscaled) in the stream.
   - New "Audit portal" page: form → live timeline (agent steps + screenshots) → exposure
     table (doc no, SRO, year, #thumbprints, #Aadhaar, status) → big counters
     ("37 deeds expose 81 thumb impressions and 29 Aadhaar numbers").

8. Also make the scanner usable from any MCP client: docs/MCP.md with a Claude Desktop /
   Claude Code config snippet pointing to scanner_server.py.

9. Tests: MCP servers start and list tools (in-process client); path-traversal rejected;
   allowlist blocks https://example.com; audit chain verifies and detects tampering;
   bulk_crawl finds all 120 seeded deeds.

DONE WHEN: from the UI, auditing "SRO Kottayam 2018–2020, max 15" visibly drives the
browser, downloads deeds, and fills the exposure table with counts matching the seed
ground truth. Commit "v3: MCP + portal audit".
```

---

## Prompt v4 — multi-agent orchestration: Orchestrator + Auditor + Reviewer + Notice (Hours 14–17)

```
Read CLAUDE.md. Implement v4: a multi-agent layer on top of v3.

Agents (each = its own tool-runner loop with its own system prompt and MCP tool subset):
1. Orchestrator (ORCHESTRATOR_MODEL, effort "medium")
   - Input: a mission, e.g. "Audit SRO Kottayam and Ettumanoor 2018–2020, remediate, and
     prepare notices" or "Process today's upload batch in data/inbox/new".
   - Tools: delegate_audit(sro, years, max_docs), delegate_review(doc_ids),
     delegate_notices(scope), plus casestore.stats and scanner.redact_pdf. Delegate tools
     are Python @beta_async_tool functions that run the sub-agent and return its summary.
   - Produces a final mission report (markdown) saved via casestore.

2. Auditor (WORKER_MODEL, effort "low") — from v3.

3. Reviewer (WORKER_MODEL, effort "medium") — the only place an LLM looks at pages
   - Input: pages with decision BLOCK_FOR_REVIEW or single-source low-confidence findings.
   - Tools: scanner.get_review_view (pixelated page image + bboxes), policy.get_policy,
     casestore.record_scan.
   - May recommend: "add redaction at bbox X (reason)", "send to human", or
     "confirm". It CANNOT remove a redaction or mark a page safe: enforce in code by
     accepting only escalation actions from its structured output (use a strict tool
     with an enum of allowed actions; additionalProperties false). Forced tool_choice is
     not available on Opus 5.5, so the model may answer in prose instead. Treat "no valid tool
     call" as SEND_TO_HUMAN, so the outcome is still fail-closed.
   - Writes a short human-readable review card per page for the clerk.

4. Notice agent (WORKER_MODEL, effort "medium")
   - Drafts (never sends): (a) a takedown/masking request to the registration department
     listing affected doc numbers by SRO/year, counts, and the remediation offered
     (re-publish redacted versions + certificates); (b) a citizen advisory in Malayalam AND
     English for affected executants: what happened, that they can lock their biometrics on
     UIDAI's official channels, and to report fraud to 1930 / cybercrime.gov.in.
   - Uses policy.legal_references; must not invent legal citations; saves via
     casestore.save_notice_draft.

Engineering requirements
- One orchestration trace per mission: every agent step goes to SSE with agent name and
  colour; the UI shows a swimlane timeline (Orchestrator / Auditor / Reviewer / Notice).
- Budget guards: max tool calls per agent, max docs per mission, total token counter shown
  in the UI from response.usage.
- Prompt caching: keep each agent's system prompt + tool list stable and put
  cache_control on it. Check usage.cache_read_input_tokens > 0 on later calls.
- Error handling: retry 429/5xx via SDK defaults; a failed sub-agent returns a structured
  error to the Orchestrator, which continues with the others.
- New UI pages: "Mission control" (mission input, swimlanes, final report), "Review queue"
  (cards with pixelated page, proposed escalations, Approve/Send-to-human buttons),
  "Notices" (drafts with copy/download, language toggle).

Tests
- Fake/mocked Anthropic client tests for: orchestrator delegates correctly; reviewer's
  attempt to "remove redaction" is rejected by the code guard; notice drafts contain no
  full Aadhaar numbers (regex check) and no fingerprint images.
- One live end-to-end test behind an env flag (RUN_LIVE=1) on 5 docs.

DONE WHEN: a single mission from Mission control runs Auditor → Reviewer → Notice end-to-end
on 10–15 deeds in under ~4 minutes, shows swimlanes live, and produces a mission report,
review cards and bilingual notice drafts. Commit "v4: multi-agent".
```

---

## Prompt v5 — polish, demo mode, benchmarks, deploy (Hours 17–20)

```
Read CLAUDE.md. Implement v5: make it demo-proof.

1. Demo mode (`make demo`): GENERATES (never commits; synthetic Aadhaar numbers pass the
   real checksum, so some may collide with real ones) a BORN-DIGITAL "hero" deed so the
   wow moment is genuinely sub-second, plus a scanned deed as the second example.
   It seeds the portal + the hero deed (2 thumbprints, 1 Aadhaar,
   1 masked Aadhaar, 1 decoy number, 1 rubber stamp) and a scripted mission. Pre-warms the ONNX
   session and the prompt cache. A "Reset demo" button.
2. The wow moment, polished: on the Upload page, an "Airplane-mode proof" panel — big
   timer, model name/size, "0 bytes sent" counter (the backend counts its own outbound
   requests during processing and shows 0). Before/after slider animation on the hero deed.
3. Metrics page: tables from docs/metrics_v1.md and v2.md (precision/recall per class,
   born-digital vs scanned, latency p50/p95, model size, 0 sensitive pages published) — a
   judge can see the numbers, with the caveat "synthetic test set".
4. Robustness: big PDFs (50 pages) stream progress per page; corrupt PDF → clear error;
   password-protected PDF → BLOCK_FOR_REVIEW with reason; concurrency limit.
5. Deploy (optional, uses credits): Dockerfiles for api, portal, web; docker-compose for
   local; deploy api + web to Cloud Run or Azure Container Apps with the mock portal protected
   by basic auth (synthetic data still shouldn't be public). The on-device story stays
   primary — the cloud deploy is only a public demo mirror.
6. STRETCH (only if everything above is done): run the INT8 ONNX detector in the browser
   with onnxruntime-web + pdf.js so the PDF never even reaches our backend. Show "Processing
   in your browser".
7. Docs: README (problem, how it works, architecture diagram in Mermaid, how to run, safety
   design: defensive-only, fail-closed, LLM-can-only-escalate, synthetic data, allowlist),
   docs/DEMO.md (90-second script), docs/ARCHITECTURE.md, LICENSES note (ultralytics AGPL,
   Noto fonts OFL).
8. Final checks: ruff clean, all tests pass, `make demo` from a fresh clone works, no
   real-looking personal data in the repo, .env not committed.

DONE WHEN: a fresh clone + `make demo` gives the full 90-second demo with no manual steps.
Commit "v5: demo-ready" and tag v5.
```

---

## Cut-line (drop in this order if behind)
1. v5 stretch (in-browser ONNX) → 2. cloud deploy → 3. Notice agent → 4. Reviewer agent
(keep the human review queue without the LLM) → 5. Jev backend (rules only) → 6. LLM Auditor (keep
bulk_crawl + Playwright, show it as "agentic system use" only if an LLM drives at least one search).

**Never cut:** synthetic data → Aadhaar Verhoeff detection → thumbprint detection (classical
or ONNX) → true redaction → fail-closed verification → System-One decision → before/after UI.

## 90-second demo (for v5)
1. (0–15 s) "Thumbprints on public land deeds are being cloned to empty Aadhaar-linked bank
   accounts. Police in Haryana and Bengal have flagged it."
2. (15–45 s) **Wow moment:** turn Wi-Fi OFF. Drop the hero deed in. In under a second, red boxes on 2
   thumb impressions + the Aadhaar number (decoy and masked number correctly ignored),
   then a black redaction plus "Verified clean · System-One 3 ms · 0 bytes sent".
   (Read out the MEASURED numbers from the UI; don't claim "under a second" unless the
   metrics page shows it.)
3. (45–75 s) Wi-Fi on. Mission control: "Audit SRO Kottayam 2018–2020." The browser drives the
   mock portal live; counters climb: "37 deeds expose 81 thumb impressions."
4. (75–90 s) The Reviewer escalates one faint print. The Notice agent shows the Malayalam citizen
   advisory. "Detect, destroy, verify — before the fraudsters get there."
