# ThumbShield

A defensive privacy tool for Indian land-registration documents. Fraudsters have copied thumb
impressions from published sale deeds to clone fingerprints and drain Aadhaar-linked bank
accounts through AePS. ThumbShield finds thumb impressions and Aadhaar numbers in deed PDFs and
truly redacts them before publication, on the clerk's own machine. It also audits deeds that are
already published.

**All data in this repo is synthetic.** Every generated PDF carries a
"SYNTHETIC SAMPLE – NOT A REAL DOCUMENT" watermark. No real fingerprints, names or Aadhaar
numbers are used.

See [`docs/BRIEF.md`](docs/BRIEF.md) for the full brief and hard rules, and
[`BUILD_PROMPTS.md`](BUILD_PROMPTS.md) for the version plan (v0 → v5).

## Quick start

```sh
uv sync                 # Python 3.11 env
make doctor             # checks tesseract (eng+mal), Node >= 20, Playwright Chromium
make data               # synthetic deeds + ground truth + YOLO export -> data/datasets/
make test               # uv run pytest -q
make lint               # uv run ruff check .
```

For the local demo use three terminals:

```powershell
.\.venv\Scripts\python.exe -m mock_portal.seed
.\.venv\Scripts\python.exe -m uvicorn mock_portal.app:app --host 127.0.0.1 --port 8100
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
cd frontend; npm install; npm run dev
```

V4 adds Mission Control at the frontend, plural mission/SSE/report routes, review and notice
read-only routes, bounded Auditor → Reviewer → Notice orchestration, and bilingual drafts.
See [`docs/MCP.md`](docs/MCP.md) for the stdio servers. Optional live Anthropic/Playwright
execution remains disabled unless explicitly configured; deterministic synthetic scanning stays
authoritative.

## v2 detector and decision controls

The default remains the V1 classical detector. Select another mode explicitly with an
environment variable before starting the API:

```powershell
$env:DETECTOR = "classical"   # classical, onnx, or fused
uv run uvicorn backend.app.main:app --reload --port 8000
```

`onnx` requires a locally supplied `data/models/thumb_det_fp32.onnx` or
`data/models/thumb_det_int8.onnx` configured by `MODEL_PATH`; `fused` reports degraded status
and keeps the classical detector active if the ONNX model is unavailable. Check
`/api/health` for actual detector availability and offline capability status.

Optional training/export commands are:

```powershell
uv sync --extra train
uv run python -m synth.make_dataset
uv run python -m ml.train_yolo --data data/datasets/yolo/data.yaml --imgsz 960 --device 0
uv run python -m ml.export_onnx data/models/runs/thumb-det/weights/best.pt
```

Training results are not considered available until the generated run metrics and export
validation files are inspected. See `docs/metrics_v2.md` and `docs/GPU.md`.

## Synthetic data (v0)

- `synth/fingerprint_gen.py` — procedural thumb impressions (orientation field from singular
  points + iterated oriented Gabor filtering, ink effects). No real fingerprint datasets.
- `synth/deed_gen.py` — Kerala-style sale deeds: Verhoeff-valid Aadhaar/VID numbers, masked
  numbers, decoys (bad checksums, phones, survey numbers, dates), hard negatives (signatures,
  seals, guilloche, QR codes, photo placeholders, security lines). Born-digital and scanned
  (image-only) modes.
- `synth/make_dataset.py` — train/val/test = 300/60/60 docs. The test split uses held-out
  ink colours and blur/scan levels (`synth/styles.py`).
- Ground-truth format: [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).

## Running on a budget

Designed for a laptop with no GPU and very little Claude API credit:
- Models per agent (`.env`): Sonnet 5.5 for Orchestrator, Auditor and Reviewer; Haiku 5.5 for
  the Notice agent. Opus 5.5 only by explicit override.
- `LLM_MODE=replay` (default) replays recorded agent runs at zero API cost; `live` records them;
  `off` disables agents (the detect → redact → verify pipeline never needs an LLM).
- `MAX_USD_PER_RUN` hard-stops any agent run that exceeds the budget.
- `uv sync --extra train` installs CPU-only torch. Train YOLO on a free Kaggle/Colab GPU.

## Notes and licences

- Fonts in `synth/fonts/` are Noto Sans / Noto Sans Malayalam under the SIL OFL 1.1
  (`synth/fonts/OFL.txt`). reportlab only partly shapes Malayalam: chillu letters render correctly,
  but some conjuncts (e.g. മ്പ) show a visible virama instead of a stacked form. That's fine for
  synthetic data, but Malayalam OCR on these pages may differ from real deeds.
- The optional `train` extra installs `ultralytics` (YOLOv8), which is **AGPL-3.0**. It's used
  only for training/exporting the edge model. That's fine for a hackathon, but check the
  licence before any other distribution.
