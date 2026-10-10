"""Build the synthetic deed dataset + YOLO export.

    uv run python -m synth.make_dataset [--out data/datasets] [--n-train 300 --n-val 60 --n-test 60]
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import time
from collections import Counter
from pathlib import Path

import cv2

SEED_BASE = {"train": 1_000_000, "val": 2_000_000, "test": 3_000_000}


def _mode_for(seed: int) -> str:
    return "scanned" if ((seed * 2654435761) >> 16) & 1 else "born_digital"


def _init_worker() -> None:
    cv2.setNumThreads(1)


def _build_one(task: tuple[str, int, str]) -> dict:
    from synth.deed_gen import generate_deed

    split, i, out = task
    root = Path(out)
    seed = SEED_BASE[split] + i
    doc_id = f"{split}_{i:05d}"
    pdf, gt, images = generate_deed(seed, split, _mode_for(seed), doc_id=doc_id)
    (root / "deeds" / split / f"{doc_id}.pdf").write_bytes(pdf)
    (root / "deeds" / split / f"{doc_id}.json").write_text(json.dumps(gt, indent=1))
    n_fp = 0
    for k, img in enumerate(images):
        name = f"{doc_id}_p{k}"
        h, w = img.shape[:2]
        cv2.imwrite(
            str(root / "yolo" / "images" / split / f"{name}.jpg"),
            cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
            [cv2.IMWRITE_JPEG_QUALITY, 90],
        )
        lines = []
        for a in gt["annotations"]:
            if a["type"] == "FINGERPRINT" and a["page"] == k:
                x0, y0, x1, y1 = a["bbox_px"]
                x0, x1 = max(0, x0), min(w, x1)
                y0, y1 = max(0, y0), min(h, y1)
                lines.append(
                    f"0 {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
                    f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"
                )
                n_fp += 1
        (root / "yolo" / "labels" / split / f"{name}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else "")
        )
    return {
        "split": split,
        "mode": gt["mode"],
        "pages": len(images),
        "ann": dict(Counter(a["type"] for a in gt["annotations"])),
        "sub": dict(
            Counter(f"{a['type']}:{a['subtype']}" for a in gt["annotations"] if a["subtype"])
        ),
        "hn": dict(Counter(h["type"] for h in gt["hard_negatives"])),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/datasets")
    ap.add_argument("--n-train", type=int, default=300)
    ap.add_argument("--n-val", type=int, default=60)
    ap.add_argument("--n-test", type=int, default=60)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    workers = args.workers or int(
        os.environ.get("THUMBSHIELD_WORKERS", min(4, os.cpu_count() or 1))
    )
    out = Path(args.out).resolve()
    counts = {"train": args.n_train, "val": args.n_val, "test": args.n_test}
    for split in counts:
        for sub in (out / "deeds" / split, out / "yolo" / "images" / split,
                    out / "yolo" / "labels" / split):  # fmt: skip
            shutil.rmtree(sub, ignore_errors=True)
            sub.mkdir(parents=True)
    tasks = [(s, i, str(out)) for s, n in counts.items() for i in range(n)]
    t0 = time.time()
    results = []
    if workers <= 1:
        _init_worker()
        it = map(_build_one, tasks)
        pool = None
    else:
        pool = mp.Pool(workers, initializer=_init_worker)
        it = pool.imap_unordered(_build_one, tasks, chunksize=1)
    for n, res in enumerate(it, 1):
        results.append(res)
        if n % 20 == 0 or n == len(tasks):
            print(f"[{n}/{len(tasks)}] {time.time() - t0:.1f}s", flush=True)
    if pool:
        pool.close()
        pool.join()

    manifest: dict = {}
    for split in counts:
        rs = [r for r in results if r["split"] == split]
        ann, sub, hn = Counter(), Counter(), Counter()
        for r in rs:
            ann.update(r["ann"])
            sub.update(r["sub"])
            hn.update(r["hn"])
        manifest[split] = {
            "documents": len(rs),
            "pages": sum(r["pages"] for r in rs),
            "modes": dict(Counter(r["mode"] for r in rs)),
            "annotations": dict(sorted(ann.items())),
            "subtypes": dict(sorted(sub.items())),
            "hard_negatives": dict(sorted(hn.items())),
        }
    (out / "deeds" / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "yolo" / "data.yaml").write_text(
        f"path: {out / 'yolo'}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: fingerprint\n"
    )
    print(json.dumps(manifest, indent=2))
    print(f"total wall time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
