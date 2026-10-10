# Architecture

v0 contains only the synthetic data pipeline:

```
synth/styles.py ──> synth/fingerprint_gen.py ──┐
                                               ├─> synth/deed_gen.py ─> synth/make_dataset.py
backend/app/core/verhoeff.py ──────────────────┘        │
                                                         ├─> data/datasets/deeds/{split}/*.pdf + *.json
                                                         └─> data/datasets/yolo/{images,labels}/{split}
```

Data formats and coordinate conventions: `docs/DATA_CONTRACT.md`. The detection, redaction,
decision, MCP and agent layers land in v1–v4 (see `BUILD_PROMPTS.md`).
## V3 additions

The local Jinja2 portal at `127.0.0.1:8100` is synthetic-only and seeds 120 deterministic deeds. The FastAPI API at `127.0.0.1:8000` starts bounded audits and exposes an SSE event stream. The scanner, case store, and policy services communicate through stdio MCP; the case store uses `data/cases.db` with a SHA-256 chained audit log. Secure fetching validates the allowlist, redirects, PDF signature, size, and destination path before registration.

The deterministic Playwright/HTTP crawler is the repeatable evaluation path. The Auditor module is the live-demo integration point and may use Playwright MCP/Anthropic only when those optional dependencies are configured. Neither path can leave the local allowlist, bypass CAPTCHA/access controls, or override the fail-closed scanner.
