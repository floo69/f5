# V5 deterministic demo

From the project root:

```powershell
.\.venv\Scripts\python.exe scripts\demo.py
```

This creates only `data/demo-data/`, seeds the local 120-record portal, creates two deterministic watermarked fixtures, starts the local API and portal when their ports are free, and runs the real V2 pipeline. The generated report is `data/demo-data/demo-report.json`. A scanned fixture that needs OCR is blocked when Tesseract is unavailable; this is an honest safety result.

Reset only the explicitly marked demo directory:

```powershell
.\.venv\Scripts\python.exe scripts\demo.py --reset --no-start-services
```

Run metrics with:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py
```

Metrics are `N/A` when the configured OCR/model prerequisites are unavailable. The evaluation notice is not a production-performance guarantee. The frontend contains Demo/Mission, Offline & Privacy, and Evaluation panels alongside the existing upload, review, audit, and notice workflows.
