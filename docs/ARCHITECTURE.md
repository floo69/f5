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
