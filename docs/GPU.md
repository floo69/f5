# Optional GPU training and export

Normal ThumbShield inference is CPU-only and does not need a GPU, cloud account, or network
access. Training is optional. Check the current cloud-provider price before starting a VM.

## GPU VM

Use a compatible CUDA VM such as a GCP L4/T4 or Azure NC-series machine. Transfer this repo
and the synthetic dataset only; never upload real documents or biometric material.

```bash
uv sync --extra train
uv run python -m synth.make_dataset
uv run python -m ml.train_yolo --data data/datasets/yolo/data.yaml --imgsz 960 --device 0
uv run python -m ml.export_onnx data/models/runs/thumb-det/weights/best.pt
```

Copy `data/models/thumb_det_fp32.onnx`, `data/models/thumb_det_int8.onnx` when produced, and
`data/models/onnx_export_validation.json` back to the local machine. Verify locally:

```bash
uv run python -c "import onnxruntime as o; print(o.InferenceSession('data/models/thumb_det_fp32.onnx', providers=['CPUExecutionProvider']).get_inputs()[0].shape)"
uv run python -c "import onnxruntime as o; print(o.InferenceSession('data/models/thumb_det_int8.onnx', providers=['CPUExecutionProvider']).get_inputs()[0].shape)"
```

If INT8 quantization is unsupported for an operator, retain FP32 and record the reason in the
export validation JSON. Shut down and delete unused VM, disk, IP, and snapshot resources when
finished.
