# Synthetic data contract (v0)

All data is synthetic. Every PDF page carries the diagonal watermark
"SYNTHETIC SAMPLE – NOT A REAL DOCUMENT".

## Fingerprint generator
`synth.fingerprint_gen.generate(seed: int, style: dict | None = None) -> np.ndarray`
- Returns RGBA uint8 (H, W, 4). RGB = ink colour, A = ink coverage. Background alpha 0.
- `style` keys: see `synth.styles.sample_fp_style`. `style=None` samples the train space from `seed`.
- Deterministic: same (seed, style) -> identical array.
- Never written to disk on its own. Prints exist only composited into pages / page images.

## Coordinates (the one thing that must not be wrong)
- `bbox_pt = [x0, y0, x1, y1]` in PDF points, **top-left origin, y down** (PyMuPDF convention).
  reportlab draws bottom-left-origin, so convert: `y0 = page_h - (y_rl + h)`, `y1 = page_h - y_rl`.
- `bbox_px = round(bbox_pt * 200 / 72)` — pixels of the page rendered at 200 dpi.
- Pages are 0-indexed.
- Scanned mode keeps the original page size. The image is inserted into the full page rect.
  Bboxes are the axis-aligned bounds of the original box after the skew rotation (about the
  page centre), clipped to the page.

## Ground-truth JSON (`<doc_id>.json`, next to `<doc_id>.pdf`)
```json
{
  "doc_id": "train_00012",
  "split": "train",
  "seed": 123,
  "mode": "born_digital" | "scanned",
  "dpi_px": 200,
  "pages": [{"index": 0, "size_pt": [595.28, 841.89]}],
  "annotations": [
    {"page": 0, "type": "FINGERPRINT" | "AADHAAR" | "VID" | "MASKED_AADHAAR" | "DECOY_NUMBER",
     "subtype": "bad_checksum" | "phone" | "survey" | "date" | "spaced" | "plain" | "hyphen" | null,
     "bbox_pt": [x0, y0, x1, y1], "bbox_px": [x0, y0, x1, y1],
     "value_masked": "XXXX XXXX 0124" | null}
  ],
  "hard_negatives": [
    {"page": 0, "type": "SIGNATURE" | "SEAL" | "GUILLOCHE" | "QR" | "PHOTO" | "SECURITY_LINES",
     "bbox_pt": [...], "bbox_px": [...]}
  ]
}
```
- Full Aadhaar/VID values are never written to ground truth or logs; only `value_masked`
  (last 4 digits visible). Ground truth is for evaluating detectors, not for recovering numbers.

## Splits
`data/datasets/deeds/{train,val,test}` — 300 / 60 / 60 documents, 1–4 pages each.
Seed ranges are disjoint per split. `test` samples from the held-out style space in
`synth/styles.py` (unseen ink colours, stronger blur, harsher scan degradation).

## YOLO export
`data/datasets/yolo/{images,labels}/{train,val,test}/<doc_id>_p<page>.jpg|.txt`, one class
(`0 = fingerprint`), normalised `cx cy w h` from `bbox_px`, plus `data/datasets/yolo/data.yaml`.
Page images are 200-dpi renders (for scanned docs: the degraded scan itself).
