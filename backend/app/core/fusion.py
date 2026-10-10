from __future__ import annotations

from .types import Finding
from ..settings import settings


def iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1]); x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x1 - x0) * max(0, y1 - y0)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1]); area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intersection / (area_a + area_b - intersection) if area_a + area_b - intersection else 0.0


def fuse_candidates(
    classical: list[Finding],
    edge: list[Finding],
    threshold: float | None = None,
    agreement_bonus: float | None = None,
) -> list[Finding]:
    threshold = settings.fusion_iou_threshold if threshold is None else threshold
    agreement_bonus = settings.fusion_agreement_bonus if agreement_bonus is None else agreement_bonus
    merged = list(classical)
    for candidate in edge:
        match = next((i for i, existing in enumerate(merged) if existing.type == candidate.type and iou(existing.bbox_pt, candidate.bbox_pt) >= threshold), None)
        if match is None:
            merged.append(candidate); continue
        existing = merged[match]; sources = sorted(set(existing.source.split('+') + candidate.source.split('+')))
        merged[match] = existing.model_copy(update={
            'confidence': round(min(1.0, max(existing.confidence, candidate.confidence) + agreement_bonus), 6),
            'source': '+'.join(sources),
        })
    return merged
