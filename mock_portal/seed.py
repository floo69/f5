"""Reproducibly seed the local synthetic registry portal."""

from __future__ import annotations

import json
from pathlib import Path

from synth.deed_gen import generate_deed

PORTAL_ROOT = Path("data/portal")
TARGETS = {"clean": 36, "thumbprint": 48, "aadhaar": 24, "masked": 12}


def _category(gt: dict) -> str:
    kinds = {a["type"] for a in gt["annotations"]}
    if "FINGERPRINT" in kinds:
        return "thumbprint"
    if kinds & {"AADHAAR", "VID"}:
        return "aadhaar"
    if "MASKED_AADHAAR" in kinds:
        return "masked"
    return "clean"


def seed_portal(root: Path = PORTAL_ROOT) -> dict:
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    deeds = root / "deeds"
    deeds.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    counts = {key: 0 for key in TARGETS}
    seed = 810000
    while len(records) < sum(TARGETS.values()):
        mode = "scanned" if seed % 3 == 0 else "born_digital"
        doc_id = f"REG-{2018 + (seed % 7)}-{len(records) + 1:04d}"
        pdf, gt, _ = generate_deed(seed, "train", mode, n_pages=1, doc_id=doc_id)
        category = _category(gt)
        (deeds / f"{doc_id}.pdf").write_bytes(pdf)
        sro = ["SRO Thiruvananthapuram", "SRO Ernakulam", "SRO Kottayam", "SRO Thrissur", "SRO Kozhikode"][seed % 5]
        year = 2018 + (seed % 7)
        records.append({
            "doc_id": doc_id, "sro": sro, "year": year,
            "doc_no": f"{seed % 9999 + 1}/{year}",
            "party_name": f"Synthetic Party {seed % 1000:03d}",
            "category": category,
            "expected_findings": sorted({a["type"] for a in gt["annotations"]}),
            "pdf": str((deeds / f"{doc_id}.pdf").as_posix()), "seed": seed,
        })
        counts[category] = counts.get(category, 0) + 1
        seed += 1
    manifest = {
        "synthetic_only": True,
        "counting_convention": "One deed belongs to exactly one category: thumbprint takes precedence over Aadhaar, then Aadhaar over masked, then clean.",
        "targets": TARGETS, "counts": counts, "records": records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(seed_portal(), indent=2))
