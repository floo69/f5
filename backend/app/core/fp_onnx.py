"""CPU-only ONNX fingerprint detector with safe model lifecycle handling."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz

from .types import Finding


class DetectorUnavailable(RuntimeError):
    pass


class DetectorInferenceError(RuntimeError):
    pass


def model_info(model_path: str | Path) -> dict:
    path = Path(model_path)
    return {
        "path": str(path),
        "available": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "quantization": "int8" if "int8" in path.name.lower() else "fp32",
        "providers": ["CPUExecutionProvider"],
    }


class OnnxDetector:
    def __init__(self, model_path: str | Path):
        path = Path(model_path)
        if not path.is_file():
            raise DetectorUnavailable(f"ONNX model not found: {path}")
        try:
            import onnxruntime as ort

            self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            inputs = self.session.get_inputs()
            if not inputs:
                raise ValueError("model has no inputs")
            self.input_name = inputs[0].name
        except Exception as exc:  # noqa: BLE001 - expose a safe structured failure
            raise DetectorUnavailable(f"ONNX model is unavailable or incompatible: {type(exc).__name__}") from exc

    @staticmethod
    def _letterbox(image: np.ndarray, size: int = 960):
        height, width = image.shape[:2]
        scale = min(size / width, size / height)
        resized = cv2.resize(image, (round(width * scale), round(height * scale)))
        canvas = np.full((size, size, 3), 114, np.uint8)
        left = (size - resized.shape[1]) // 2
        top = (size - resized.shape[0]) // 2
        canvas[top : top + resized.shape[0], left : left + resized.shape[1]] = resized
        return canvas, scale, left, top

    def detect(self, page: fitz.Page, page_number: int = 0) -> list[Finding]:
        pix = page.get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
        image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
        boxed, scale, left, top = self._letterbox(image)
        tensor = boxed[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
        try:
            outputs = self.session.run(None, {self.input_name: tensor})
            raw = np.asarray(outputs[0])
        except Exception as exc:  # noqa: BLE001
            raise DetectorInferenceError(f"ONNX inference failed: {type(exc).__name__}") from exc

        raw = raw[0] if raw.ndim == 3 else raw
        if raw.ndim == 2 and raw.shape[0] < raw.shape[1]:
            raw = raw.T
        candidates: list[tuple[float, tuple[float, float, float, float]]] = []
        for row in raw:
            if len(row) < 5:
                continue
            if len(row) == 6:
                x0, y0, x1, y1, confidence, cls = row
            else:
                x, y, width, height = row[:4]
                scores = row[4:]
                cls = int(np.argmax(scores))
                confidence = float(scores[cls])
                x0, y0, x1, y1 = x - width / 2, y - height / 2, x + width / 2, y + height / 2
            if int(cls) != 0 or float(confidence) < 0.15:
                continue
            x0, x1 = (x0 - left) / scale, (x1 - left) / scale
            y0, y1 = (y0 - top) / scale, (y1 - top) / scale
            candidates.append((float(confidence), (x0 * 72 / 200, y0 * 72 / 200, x1 * 72 / 200, y1 * 72 / 200)))

        candidates.sort(reverse=True, key=lambda item: item[0])
        kept: list[tuple[float, tuple[float, float, float, float]]] = []
        for confidence, box in candidates:
            if all(self._iou(box, other) < 0.30 for _, other in kept):
                kept.append((confidence, box))
        return [Finding(type="FINGERPRINT", bbox_pt=box, page=page_number, confidence=confidence, source="onnx") for confidence, box in kept]

    @staticmethod
    def _iou(a, b):
        x0, y0 = max(a[0], b[0]), max(a[1], b[1])
        x1, y1 = min(a[2], b[2]), min(a[3], b[3])
        intersection = max(0, x1 - x0) * max(0, y1 - y0)
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
        return intersection / union if union else 0.0


_sessions: dict[str, OnnxDetector] = {}


def detect_fingerprint_regions(page, page_number=0, model_path=None):
    if not model_path:
        raise DetectorUnavailable("ONNX model path is not configured")
    key = str(Path(model_path).resolve())
    if key not in _sessions:
        _sessions[key] = OnnxDetector(key)
    return _sessions[key].detect(page, page_number)
