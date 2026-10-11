# SurakshitID (सुरक्षित ID)

A purpose-bound identity-sharing prototype built on the original ThumbShield local redaction
pipeline. The frontend demonstrates purpose presets, on-device raster flattening, manual mask
placement, a tiled purpose watermark, masked-pixel checks, and a tamper-demo inspector. The
existing backend detects Aadhaar numbers and thumb impressions in PDFs and fails closed when its
verification cannot prove a clean result.

**All generated sample data is synthetic.** The current image-sharing UI is a prototype: it does
not automatically detect fields, prove image quality, enforce a real expiry, or prevent a
recipient from reusing a downloaded copy. The browser raster flow accepts images; PDF files use
the existing Aadhaar / thumbprint scanner and do not receive the purpose watermark. The broader
PAN / QR / face detection stack is not implemented.

See [`docs/BRIEF.md`](docs/BRIEF.md) for the original PDF pipeline brief and hard rules, and
[`BUILD_PROMPTS.md`](BUILD_PROMPTS.md) for the version plan (v0 → v5).

## Quick start

```sh
uv sync                 # Python 3.11 env
make doctor             # checks tesseract (eng+mal), Node >= 20, Playwright Chromium
make data               # synthetic deeds + ground truth + YOLO export -> data/datasets/
make test               # uv run pytest -q
make lint               # uv run ruff check .
```

`make api` (FastAPI :8000), `make portal` (mock registry :8100) and `make web` (frontend) are
placeholders until v1/v3.

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
