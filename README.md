# SurakshitID (सुरक्षित ID) + ThumbShield

**SurakshitID** protects your Aadhaar or PAN before you share it. Take a photo; it straightens
and cleans it, strips metadata, permanently destroys what the recipient doesn't need (first 8
Aadhaar digits, QR code, thumbprints…), stamps a purpose watermark ("FOR TAJ HOTEL CHECK-IN
ONLY · NOT VALID FOR BANKING, SIM, LOANS") and seals the copy so any edit is detected. Copies
expire and can be revoked. A leak scanner finds IDs exposed on websites and drafts a DPDP Act
takedown notice. Everything runs on your own machine.

- **Demo script for judges:** [`docs/DEMO.md`](docs/DEMO.md)
- **API:** [`docs/ARMOR_CONTRACT.md`](docs/ARMOR_CONTRACT.md) (SurakshitID), [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) (deeds)
- **Tabs:** Protect · My copies · Check a copy · Leak alerts · Deeds (registry offices)
- Agents run on built-in rules by default (`LLM_MODE=replay`, $0). With Claude enabled on
  your account, set `LLM_MODE=live` in `.env`.

## ThumbShield (deeds)

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

## Run it

You need two terminals, both opened in the project folder:

```sh
cd ~/Documents/f5
```

**Terminal 0 (only for the Leak alerts tab), the mock hotel website:** `make portal`

**Terminal 1, the backend** (it does the detection and redaction):
```sh
make api
```
Wait for the line `SurakshitID / ThumbShield running locally — no document leaves this machine`.

**Terminal 2, the website:**
```sh
make web
```
Wait for `Local: http://localhost:5173/`.

Then open **http://localhost:5173** in your browser. On **Protect**, try a sample or take a photo of an ID card. Deed PDFs go in the **Deeds** tab.

- **No backend running:** **http://localhost:5173/?mock=1** shows a demo result without the backend. It's a good backup during a presentation.
- **First time on a new machine:** run `uv sync` once (and `make doctor` to check that tesseract, Node and Playwright are installed) before the steps above. `make web` installs the website's packages by itself.

## Turn it off

Press **Ctrl + C** in each of the two terminals. That stops both.

The backend server started earlier may still be running in the background without a terminal window, so Ctrl + C won't reach it. Stop it (and any leftover website server) with:
```sh
pkill -f '[u]vicorn backend.app.main'; pkill -f '[u]vicorn mock_portal'; pkill -f '[v]ite --port 5173'
```

If you ever get "address already in use" when starting, an old server is still running; run that same command and start again.

## Other useful commands

| Command | What it does |
|---|---|
| `make test` | Runs all automated tests (about 20 s) |
| `make lint` | Checks code style |
| `make data` | Regenerates the synthetic dataset (about 70 s) |
| `make doctor` | Checks that tesseract, Node and Playwright are installed |

Redacted PDFs and certificates from your runs are saved in `data/out/`. Delete that folder any time to clean up.

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
