# API contract (v1)

Backend: FastAPI on :8000. Frontend (Vite dev server) proxies `/api` → `http://localhost:8000`.
Everything runs locally; no endpoint calls an external service.

## Endpoints
| Method | Path | Returns |
|---|---|---|
| POST | `/api/process` (multipart field `file`, a PDF) | `{"job_id": str}` immediately; processing runs in the background |
| GET | `/api/jobs/{job_id}` | `Job` (poll every ~500 ms until `status` is `done` or `error`) |
| GET | `/api/files/{job_id}/redacted` | redacted PDF (`application/pdf`, attachment) |
| GET | `/api/files/{job_id}/certificate` | certificate JSON |
| GET | `/api/files/{job_id}/certificate.pdf` | one-page certificate PDF |
| GET | `/api/files/{job_id}/page/{n}.png?view=before\|after&dpi=100` | page PNG |
| GET | `/api/samples` | `[{"name": str, "mode": "born_digital"\|"scanned"}]` bundled synthetic samples |
| POST | `/api/samples/{name}/process` | `{"job_id": str}` — process a sample without uploading |
| GET | `/api/health` | `{"status": "ok", "local_only": true}` |

`view=before` is the ORIGINAL page with every FINGERPRINT bbox **pixelated (12 px mosaic)** and
red outlines on all findings (green outline for MASKED_AADHAAR). A clean fingerprint image is
never served or written to disk. `view=after` is the redacted PDF's page.

## Job
```json
{
  "job_id": "a1b2c3",
  "filename": "deed.pdf",
  "status": "queued" | "processing" | "done" | "error",
  "error": null,
  "progress": {"pages_done": 2, "pages_total": 3},
  "result": null | Result
}
```

## Result
```json
{
  "doc_id": "a1b2c3",
  "sha256_in": "…", "sha256_out": "…",
  "page_count": 3,
  "status": "VERIFIED_CLEAN" | "BLOCKED_FOR_REVIEW",
  "pages": [
    {
      "page": 0,
      "size_pt": [595.28, 841.89],
      "text_layer": true,
      "ocr_quality": 1.0,
      "decision": "PUBLISH" | "REDACT_AND_PUBLISH" | "BLOCK_FOR_REVIEW",
      "reasons": ["2 thumb impressions", "1 Aadhaar number"],
      "findings": [
        {"type": "FINGERPRINT" | "AADHAAR" | "VID" | "MASKED_AADHAAR",
         "page": 0, "bbox_pt": [x0, y0, x1, y1], "confidence": 0.91,
         "source": "textlayer" | "ocr" | "classical", "value_masked": "XXXX XXXX 0124" | null,
         "redact": true}
      ],
      "counts": {"FINGERPRINT": 2, "AADHAAR": 1, "VID": 0, "MASKED_AADHAAR": 1},
      "timings_ms": {"render": 12.1, "text": 3.0, "aadhaar": 0.4, "fingerprint": 180.2}
    }
  ],
  "verification": {"status": "pass" | "fail", "problems": [{"page": 0, "type": "AADHAAR", "bbox_pt": [], "detail": "…"}]},
  "timings_ms": {"detect": 300.0, "redact": 40.0, "verify": 250.0, "total": 610.0},
  "detector_versions": {"aadhaar": "1.0", "fp_classical": "1.0"}
}
```
Bboxes: PDF points, top-left origin (same as ground truth).
Decision rule (v1, temporary until v2's engine): verification fail → BLOCK_FOR_REVIEW; any
redactable finding → REDACT_AND_PUBLISH; scanned page with ocr_quality < 0.55 →
BLOCK_FOR_REVIEW; else PUBLISH. Document status = BLOCKED_FOR_REVIEW if any page is blocked.
