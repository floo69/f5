"""Train YOLOv8n on the synthetic fingerprint dataset.

Training is optional and never runs during inference. The command writes the exact
configuration beside the run so metrics cannot be confused with a held-out result.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/datasets/yolo/data.yaml")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--patience", type=int, default=12)
    args = parser.parse_args()
    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"Dataset manifest not found: {data_path}. Run the synthetic dataset generator first.")

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Training requires the optional train dependencies: uv sync --extra train") from exc

    project = Path("data/models/runs").resolve()
    config = vars(args) | {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "augmentations": {
            "rotation_degrees": 35,
            "blur": True,
            "brightness_contrast": True,
            "jpeg_compression": True,
            "mosaic": 1.0,
            "mixup": 0.15,
            "hsv": [0.03, 0.5, 0.4],
        },
        "early_stopping": {"patience": args.patience},
    }
    project.mkdir(parents=True, exist_ok=True)
    (project / "requested_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    model = YOLO("yolov8n.pt")
    model.train(
        data=str(data_path), imgsz=args.imgsz, epochs=args.epochs, fraction=args.fraction,
        device=args.device, patience=args.patience, degrees=35, hsv_h=0.03, hsv_s=0.5,
        hsv_v=0.4, mosaic=1.0, mixup=0.15, project=str(project), name="thumb-det",
    )
    print(f"Training finished. Inspect {project / 'thumb-det'}/results.csv for measured precision, recall and mAP50.")


if __name__ == "__main__":
    main()
