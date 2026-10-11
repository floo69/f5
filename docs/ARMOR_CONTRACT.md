# SurakshitID armor API contract (v2)

SurakshitID is the second path alongside the ThumbShield deed path (`docs/API_CONTRACT.md`,
unchanged). It turns a photo/scan/PDF of an identity document (Aadhaar, PAN, KYC sheet) into a
**purpose-locked, flattened, sealed** raster that cannot be reused for anything else.

Everything runs on the local backend (FastAPI :8000). No endpoint calls an external service.
All examples use synthetic data only.

## Output invariants (enforced by `backend/app/core/verify_raster.py`, fail closed)
1. Output is a lossless RGB PNG and an image-only PDF made from the same pixels. Never JPEG.
2. Every mask rectangle is exactly `0x00` in every channel (max == 0). Watermark is drawn first,
   masks are zeroed last, the badge strip is outside all masks.
3. No metadata: PNG has only IHDR/IDAT/IEND chunks; PDF has empty metadata, no text layer,
   no annotations, exactly one image.
4. Re-scan of the output finds no token the preset says must be hidden (full Aadhaar/VID,
   PAN, decodable Aadhaar QR, thumb impression). Scan quality too low to prove absence →
   `BLOCK_FOR_REVIEW`.
5. A signed badge (Ed25519) covers the SHA-256 of the final pixels and a grid of per-tile
   hashes (`tile_px` square tiles), so any pixel edit is located to exact coordinates.
   Exact hashes survive only lossless copies: a re-photographed or JPEG-recompressed copy
   does not verify (reported as `FORGERY_DETECTED`, not silently accepted).

## Coordinates
Pixel bboxes `[x0, y0, x1, y1]` in the **normalised** image (after crop/deskew), top-left
origin, y down. `dpi` tells the physical scale (ID card → 300 dpi, A4 page → 200 dpi).

## Endpoints
| Method | Path | Returns |
|---|---|---|
| GET | `/api/presets` | `Preset[]` |
| POST | `/api/voice/parse` JSON `{"text": str}` | `VoiceIntent` (deterministic, no LLM) |
| GET | `/api/id-samples` | `[{"name","label","kind"}]` synthetic ID samples |
| GET | `/api/id-samples/{name}.jpg` | synthetic phone-photo JPEG (carries fake EXIF so stripping is visible) |
| POST | `/api/armor` multipart: `file` (jpg/png/webp/pdf), `preset`, `recipient`, `valid_days` (int), `source` (`camera`\|`upload`) | `{"job_id"}` |
| GET | `/api/armor/{job_id}` | `ArmorJob` (poll ~400 ms) |
| GET | `/api/armor/{job_id}/view.png?which=before\|after` | before = normalised input with thumb impressions and QR **pixelated** + outlines; after = armored output |
| GET | `/api/armor/{job_id}/armored.png` | armored PNG (attachment) — only if decision is `ARMOR_AND_ISSUE` |
| GET | `/api/armor/{job_id}/armored.pdf` | image-only PDF (attachment) — same condition |
| GET | `/api/armor/{job_id}/badge.json` | `Badge` |
| GET | `/api/armor/{job_id}/inspect` | `Inspection` (Adversarial Inspector drawer) |
| POST | `/api/armor/{job_id}/attack` JSON `{"kind": "erase_watermark"\|"swap_photo"\|"unmask"\|"crop"}` | `{"attack_id", "image_url", "verify": VerifyReport}` |
| GET | `/api/attacks/{attack_id}.png` | the tampered image (in memory only) |
| POST | `/api/verify` multipart `file` (png/pdf) | `VerifyReport` |

## Types
```ts
type PresetKey = 'hotel' | 'xerox' | 'sim' | 'rental' | 'school' | 'bank_loan'
interface Preset {
  key: PresetKey; label: string;            // "Hotel Check-in"
  masks: string[];                          // human list: ["Aadhaar first 8 digits", "QR code", ...]
  keeps: string[];                          // ["Photo", "Name", "Address"]
  default_days: number; max_days: number;
  not_valid_for: string[];                  // ["BANKING", "SIM", "LOANS"]
}
interface VoiceIntent {
  ok: boolean; preset: PresetKey | null; recipient: string | null; valid_days: number | null;
  document: 'aadhaar' | 'pan' | 'any'; missing: string[];   // e.g. ["recipient"]
  confirmation: string;                     // speakable sentence
  parse_ms: number;
}
type Decision = 'ARMOR_AND_ISSUE' | 'INSUFFICIENT_PURPOSE' | 'BLOCK_FOR_REVIEW'
type FindingType = 'AADHAAR' | 'VID' | 'MASKED_AADHAAR' | 'PAN' | 'QR' | 'BARCODE' | 'FACE'
                 | 'FINGERPRINT' | 'DOB' | 'NUMBER'
interface IdFinding {
  type: FindingType; bbox_px: [number, number, number, number];
  action: 'MASK' | 'MASK_PARTIAL' | 'KEEP';
  masked_px: number[][];                    // rects actually zeroed for this finding
  value_masked: string | null;              // "XXXX XXXX 0124", "XXXXX1234X"; never a full value
  confidence: number; source: string;
}
interface Step { key: string; label: string; status: 'pending' | 'running' | 'done' | 'failed'; ms: number | null }
interface ArmorJob {
  job_id: string; status: 'queued' | 'processing' | 'done' | 'error'; error: string | null;
  steps: Step[];                            // capture, preprocess, detect, decide, destroy, watermark, verify, seal
  result: ArmorResult | null;
}
interface ArmorResult {
  armor_id: string;                         // "SKID-7Q2K-9F3M"
  decision: Decision; reasons: string[];
  decision_us: number;                      // System-One gate latency in microseconds
  preset: Preset; recipient: string; issued_at: string; expires_at: string;
  watermark_text: string;
  preprocess: {
    doc_kind: 'id_card' | 'a4_page' | 'unknown'; quad_found: boolean; rotation_deg: number;
    blur_score: number; blur_ok: boolean; glare_fraction: number; shadow_corrected: boolean;
    metadata_removed: string[];             // ["EXIF:Make", "EXIF:GPSInfo", ...] tag NAMES only
    width: number; height: number; dpi: number;
  };
  ocr_quality: number;
  findings: IdFinding[];
  masks_px: number[][];
  verification: { status: 'pass' | 'fail' | 'skipped'; checks: { name: string; ok: boolean; detail: string }[] };
  badge: Badge | null;
  timings_ms: Record<string, number>;
}
interface Badge {
  v: 1; armor_id: string; preset: PresetKey; recipient: string; purpose: string;
  issued_at: string; expires_at: string; width: number; height: number; tile_px: number;
  sha256: string;                           // of the raw RGB pixel buffer
  tiles_root: string;                       // Merkle root over per-tile hashes
  prev_hash: string; block_hash: string; ledger_index: number;   // append-only local ledger
  public_key: string; signature: string;    // Ed25519, hex
}
interface Inspection {
  masks: { bbox_px: number[]; pixels: number; min: number; max: number; unique_values: number;
           entropy_bits: number; hex_sample: string }[];       // hex_sample "00 00 00 …"
  pdf: { text_chars: number; text_sample: string; metadata: Record<string, string>;
         images: number; annotations: number; pages: number };
  png: { chunks: string[]; exif: boolean };
  brightened_mask_max: number;              // max after x255 gain: still 0
}
interface VerifyReport {
  status: 'AUTHENTIC' | 'FORGERY_DETECTED' | 'EXPIRED' | 'UNKNOWN_BADGE' | 'NO_BADGE';
  armor_id: string | null; purpose: string | null; recipient: string | null;
  expires_at: string | null; signature_ok: boolean;
  width: number; height: number; tile_px: number;
  altered_regions: number[][];              // merged pixel rects, exact coordinates
  altered_tiles: number; total_tiles: number;
  detail: string;
}
```

## Presets (minimum disclosure)
Thumb impressions and VIDs are destroyed under **every** preset (hard rule).

| Preset | Masks | Keeps | Days (default/max) |
|---|---|---|---|
| Hotel Check-in | Aadhaar first 8, QR/barcode, PAN, thumbprints | photo, name, address, DOB | 2 / 7 |
| Xerox / Print Shop | every number (Aadhaar, PAN, DOB, PIN, phone…), QR/barcode, thumbprints | photo, name | 1 / 1 |
| SIM / Telecom | Aadhaar first 8, PAN, thumbprints | photo, name, address, DOB, QR (offline e-KYC) | 3 / 7 |
| Rental / Landlord | Aadhaar first 8, QR/barcode, PAN, DOB, thumbprints | photo, name, address | 30 / 90 |
| School Admission | Aadhaar first 8, QR/barcode, PAN, thumbprints | photo, name, DOB, address | 30 / 90 |
| Bank Loan | Aadhaar first 8, thumbprints | photo, name, DOB, address, PAN, QR | 15 / 30 |

## Decision gate (System-One, `backend/app/core/decision.py`)
Pure function over a typed summary, no I/O, measured per call (target < 5 ms; typically µs).
Rules, first match wins:
1. blur score below threshold, no document found, or OCR quality too low to prove absence → `BLOCK_FOR_REVIEW` ("Cannot verify safely").
2. unknown preset, recipient shorter than 3 chars, `valid_days` < 1 or > preset max → `INSUFFICIENT_PURPOSE`.
3. post-export verification failed → `BLOCK_FOR_REVIEW`.
4. otherwise → `ARMOR_AND_ISSUE`.
No LLM participates. Agents may only escalate (add a mask / send to review).

## v2.1 additions

### Careful mode (unclear photos)
When a photo is readable enough to find an ID but not to prove every character, the gate still
issues the copy but hides MORE: the whole Aadhaar number, every number, and anything QR-like.
`ArmorResult.careful: boolean` and a plain reason ("Some text was hard to read, so we hid extra
details to be safe"). Refusal (`BLOCK_FOR_REVIEW`) is kept for: too blurry, no ID found at all,
or post-export verification failure.

### My copies (history + revoke)
| Method | Path | Returns |
|---|---|---|
| GET | `/api/copies` | `Copy[]` newest first |
| POST | `/api/copies/{armor_id}/revoke` | `Copy` |
```ts
interface Copy { armor_id: string; preset: PresetKey; preset_label: string; recipient: string;
  purpose: string; issued_at: string; expires_at: string;
  status: 'active' | 'expired' | 'revoked'; revoked_at: string | null }
```
`VerifyReport.status` gains `'REVOKED'` (signature fine, but the owner withdrew the copy).

### Agents (plain-language timeline)
Every SSE event now carries `say: string` (one plain sentence for the UI) and an optional
`step: 'scan' | 'found' | 'lock' | 'review' | 'notice' | 'done'`. "found" events carry
`finding: {page_url, kinds: string[], masked: string[], thumb_url}`; `thumb_url` is a server
image of the leaked document with sensitive parts already blacked out. The `done` event's
`result` has `{summary, exposed_count, risk: 'high'|'medium'|'low'|'none', notice?, escalated,
cost_usd, mode}`. Case `forgery` additionally emits `review` with `attack_type` + `say`.
