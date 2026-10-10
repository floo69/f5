# ThumbShield v2 metrics

Status: unavailable until the held-out synthetic test split is evaluated with the selected
model artifacts. No precision, recall, mAP50, latency, or model-size values are fabricated.

Required comparison: classical, ONNX FP32, ONNX INT8, and fused detectors on the digital and
scanned held-out splits. Record the command, date, CPU/GPU, dataset split, detector mode,
thresholds, precision, recall, mAP50, false positives, over-redaction, decision latency,
full processing latency, and artifact sizes after running the evaluation.
