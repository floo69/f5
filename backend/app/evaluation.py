"""Small, deterministic metric helpers used by the V5 evaluation command."""
from __future__ import annotations

from statistics import mean


def precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"precision": precision, "recall": recall, "f1": f1, "false_positive": fp, "false_negative": fn}


def percentile(values: list[float], p: float) -> float | None:
    if not values: return None
    ordered = sorted(values); index = (len(ordered) - 1) * p / 100
    low, high = int(index), min(len(ordered) - 1, int(index) + 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def summarize_times(values: list[float]) -> dict[str, float | None]:
    return {"mean_ms": mean(values) if values else None, "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95)}
