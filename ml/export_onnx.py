"""Export trained YOLO weights and validate FP32/INT8 ONNX artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("weights")
    parser.add_argument("--out", default="data/models")
    args = parser.parse_args()
    weights = Path(args.weights)
    if not weights.exists():
        raise SystemExit(f"Weights not found: {weights}. Complete training first.")
    try:
        from ultralytics import YOLO
        import onnxruntime as ort
        from onnxruntime.quantization import QuantType, quantize_dynamic
    except ImportError as exc:
        raise SystemExit("Export requires the optional train dependencies and onnxruntime") from exc

    target = Path(args.out)
    target.mkdir(parents=True, exist_ok=True)
    exported = Path(YOLO(str(weights)).export(format="onnx", imgsz=960, opset=17, dynamic=False, simplify=True))
    fp32 = target / "thumb_det_fp32.onnx"
    exported.replace(fp32)
    int8 = target / "thumb_det_int8.onnx"
    quant_error = None
    try:
        quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QUInt8)
    except Exception as exc:  # architecture/operator support is model-dependent
        quant_error = f"{type(exc).__name__}: {exc}"

    validation = {}
    for path in (fp32, int8):
        if not path.exists():
            continue
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        shape = session.get_inputs()[0].shape
        validation[path.name] = {"bytes": path.stat().st_size, "input_shape": shape, "providers": session.get_providers()}
    if quant_error:
        validation["int8_error"] = quant_error
    (target / "onnx_export_validation.json").write_text(json.dumps(validation, indent=2, default=str), encoding="utf-8")
    print(json.dumps(validation, indent=2, default=str))


if __name__ == "__main__":
    main()
