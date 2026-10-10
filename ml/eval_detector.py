"""Evaluate the deterministic detectors against synthetic ground truth.

    uv run python -m ml.eval_detector --detector classical --split val [--limit N] [--out docs/metrics_v1.md]
    uv run python -m ml.eval_detector --detector aadhaar   --split val

Pages are processed one at a time (low memory). Ground truth never contains full Aadhaar/VID
numbers and neither does the report. Fingerprint pixels are never written anywhere.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "datasets" / "deeds"
MODES = ("born_digital", "scanned")
IOU_MIN = 0.3
COVER_MIN = 0.5
MATCH_RULE = (
    f"A finding matches a ground-truth (GT) box if IoU >= {IOU_MIN} OR the finding covers >= "
    f"{COVER_MIN:.0%} of the GT box (rotated prints have loose axis-aligned GT boxes). Greedy by "
    "descending confidence, one finding per GT box and vice versa."
)
CAVEAT = (
    "Caveat: synthetic test set. Numbers measure behaviour on generated deeds (with the held-out "
    "style space for `test`), not on real registry scans."
)


# ------------------------------------------------------------------ geometry
def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def iou(a, b) -> float:
    i = _inter(a, b)
    return i / (_area(a) + _area(b) - i + 1e-9)


def covers(finding, gt) -> float:
    """Fraction of the GT box covered by the finding."""
    return _inter(finding, gt) / (_area(gt) + 1e-9)


def is_match(finding, gt) -> bool:
    return iou(finding, gt) >= IOU_MIN or covers(finding, gt) >= COVER_MIN


def greedy_match(findings, gts):
    """findings: list of (conf, bbox); gts: list of bbox. Returns (matched {gt_idx: f_idx}, unmatched f idx)."""
    order = sorted(range(len(findings)), key=lambda i: -findings[i][0])
    gt_taken: dict[int, int] = {}
    unmatched = []
    for fi in order:
        best, best_score = None, -1.0
        for gi, g in enumerate(gts):
            if gi in gt_taken or not is_match(findings[fi][1], g):
                continue
            sc = max(iou(findings[fi][1], g), covers(findings[fi][1], g))
            if sc > best_score:
                best, best_score = gi, sc
        if best is None:
            unmatched.append(fi)
        else:
            gt_taken[best] = fi
    return gt_taken, unmatched


# ------------------------------------------------------------------ data
def iter_docs(split: str, limit: int | None):
    paths = sorted((DATA / split).glob("*.json"))
    if limit:
        paths = paths[:limit]
    for jp in paths:
        gt = json.loads(jp.read_text())
        yield jp.with_suffix(".pdf"), gt


def _pct(xs, q):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return p, r, f


def _fmt(x, nd=3):
    return "n/a" if x != x else f"{x:.{nd}f}"


# ------------------------------------------------------------------ classical
def _classify_fp(box, hns, text_words) -> str:
    specific = [h for h in hns if h["type"] != "GUILLOCHE"]
    best, best_frac = None, 0.0
    for h in specific:
        hb = h["bbox_pt"]
        frac = _inter(box, hb) / (_area(box) + 1e-9)
        if frac > best_frac:
            best, best_frac = h["type"], frac
    if best and best_frac >= 0.2:
        return best
    for h in hns:
        if h["type"] == "GUILLOCHE" and _inter(box, h["bbox_pt"]) / (_area(box) + 1e-9) >= 0.5:
            return "GUILLOCHE"
    if text_words:
        tw = sum(_inter(box, w) for w in text_words)
        if tw / (_area(box) + 1e-9) >= 0.2:
            return "text"
    return "other"


def eval_classical(split: str, limit: int | None):
    from backend.app.core import fp_classical

    stats = {m: Counter() for m in (*MODES, "all")}
    fp_types = {m: Counter() for m in (*MODES, "all")}
    lat_total, lat_detect = [], []
    cover_frac = {m: [] for m in (*MODES, "all")}
    ndocs = Counter()
    npages = Counter()
    misses = []
    for pdf, gt in iter_docs(split, limit):
        mode = gt["mode"]
        ndocs[mode] += 1
        with pymupdf.open(pdf) as doc:
            for pi, page in enumerate(doc):
                npages[mode] += 1
                t0 = time.perf_counter()
                pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
                import numpy as np

                gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.stride)[:, : pix.w]
                t1 = time.perf_counter()
                findings = fp_classical.detect_gray(gray, pi, 200)
                t2 = time.perf_counter()
                lat_total.append((t2 - t0) * 1000)
                lat_detect.append((t2 - t1) * 1000)
                gts = [
                    a["bbox_pt"]
                    for a in gt["annotations"]
                    if a["type"] == "FINGERPRINT" and a["page"] == pi
                ]
                hns = [h for h in gt["hard_negatives"] if h["page"] == pi]
                fl = [(f.confidence, f.bbox_pt) for f in findings]
                taken, unmatched = greedy_match(fl, gts)
                words = [w[:4] for w in page.get_text("words")] if mode == "born_digital" else []
                for m in (mode, "all"):
                    stats[m]["tp"] += len(taken)
                    stats[m]["fn"] += len(gts) - len(taken)
                    stats[m]["fp"] += len(unmatched)
                    stats[m]["gt"] += len(gts)
                    for gi, fi in taken.items():
                        cover_frac[m].append(min(1.0, covers(fl[fi][1], gts[gi])))
                    for fi in unmatched:
                        fp_types[m][_classify_fp(fl[fi][1], hns, words)] += 1
                for gi in range(len(gts)):
                    if gi not in taken:
                        misses.append((pdf.name, pi, [round(v) for v in gts[gi]]))
    return {
        "stats": stats, "fp_types": fp_types, "lat_total": lat_total, "lat_detect": lat_detect,
        "ndocs": ndocs, "npages": npages, "cover": cover_frac, "misses": misses,
    }  # fmt: skip


def render_classical(res, split: str) -> str:
    L = [f"### Classical thumb-impression detector - `{split}` split", ""]
    nd, npg = res["ndocs"], res["npages"]
    L += [
        f"Date: {dt.date.today().isoformat()}. Docs: {sum(nd.values())} "
        f"(born_digital {nd['born_digital']}, scanned {nd['scanned']}); pages: {sum(npg.values())} "
        f"(born_digital {npg['born_digital']}, scanned {npg['scanned']}).",
        "",
        f"Matching rule: {MATCH_RULE}",
        "",
        "| mode | GT prints | TP | FP | FN | precision | recall | F1 | mean GT coverage |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in ("born_digital", "scanned", "all"):
        s = res["stats"][m]
        p, r, f = _prf(s["tp"], s["fp"], s["fn"])
        cv = res["cover"][m]
        mc = sum(cv) / len(cv) if cv else float("nan")
        L.append(
            f"| {m} | {s['gt']} | {s['tp']} | {s['fp']} | {s['fn']} | {_fmt(p)} | {_fmt(r)} | {_fmt(f)} | {_fmt(mc)} |"
        )
    kinds = ["SIGNATURE", "SEAL", "GUILLOCHE", "QR", "PHOTO", "SECURITY_LINES", "text", "other"]
    L += ["", "False positives by overlapped hard-negative type (`text` = overlaps text-layer words, born-digital only):", "",
          "| mode | " + " | ".join(kinds) + " | total |", "|---|" + "---|" * (len(kinds) + 1)]  # fmt: skip
    for m in ("born_digital", "scanned", "all"):
        c = res["fp_types"][m]
        L.append(f"| {m} | " + " | ".join(str(c[k]) for k in kinds) + f" | {sum(c.values())} |")
    lt, ld = res["lat_total"], res["lat_detect"]
    L += [
        "",
        "Latency per page, single CPU thread (ms):",
        "",
        "| | p50 | p95 | max |",
        "|---|---|---|---|",
        f"| render 200 dpi + detect | {_pct(lt, 0.5):.0f} | {_pct(lt, 0.95):.0f} | {max(lt):.0f} |",
        f"| detect only | {_pct(ld, 0.5):.0f} | {_pct(ld, 0.95):.0f} | {max(ld):.0f} |",
        "",
        CAVEAT,
        "",
    ]
    return "\n".join(L)


# ------------------------------------------------------------------ aadhaar
def eval_aadhaar(split: str, limit: int | None):
    from backend.app.core.aadhaar import find_numbers
    from backend.app.core.ocr import get_page_text

    types = ("AADHAAR", "VID", "MASKED_AADHAAR")
    tp = {m: Counter() for m in MODES}
    gt_n = {m: Counter() for m in MODES}
    sub_tp = defaultdict(Counter)
    sub_n = defaultdict(Counter)
    decoy_fp = {m: Counter() for m in MODES}
    decoy_n = {m: 0 for m in MODES}
    other_fp = {m: Counter() for m in MODES}
    ndocs, npages = Counter(), Counter()
    lat = []
    for pdf, gt in iter_docs(split, limit):
        mode = gt["mode"]
        ndocs[mode] += 1
        with pymupdf.open(pdf) as doc:
            for pi, page in enumerate(doc):
                npages[mode] += 1
                t0 = time.perf_counter()
                findings = find_numbers(get_page_text(page), pi)
                lat.append((time.perf_counter() - t0) * 1000)
                anns = [a for a in gt["annotations"] if a["page"] == pi]
                for t in types:
                    gts = [a for a in anns if a["type"] == t]
                    fl = [(f.confidence, tuple(f.bbox_pt)) for f in findings if f.type == t]
                    taken, unmatched = greedy_match(fl, [a["bbox_pt"] for a in gts])
                    gt_n[mode][t] += len(gts)
                    tp[mode][t] += len(taken)
                    for gi, a in enumerate(gts):
                        key = (t, a.get("subtype") or "-")
                        sub_n[mode][key] += 1
                        sub_tp[mode][key] += gi in taken
                decoys = [a["bbox_pt"] for a in anns if a["type"] == "DECOY_NUMBER"]
                decoy_n[mode] += len(decoys)
                other_boxes = [a["bbox_pt"] for a in anns if a["type"] in types]
                for f in findings:
                    if f.type not in ("AADHAAR", "VID"):
                        continue
                    b = tuple(f.bbox_pt)
                    if any(iou(b, d) >= IOU_MIN for d in decoys):
                        decoy_fp[mode][f.type] += 1
                    elif not any(is_match(b, o) for o in other_boxes):
                        other_fp[mode][f.type] += 1
    return {
        "types": types, "tp": tp, "gt": gt_n, "sub_tp": sub_tp, "sub_n": sub_n, "decoy_fp": decoy_fp,
        "decoy_n": decoy_n, "other_fp": other_fp, "ndocs": ndocs, "npages": npages, "lat": lat,
    }  # fmt: skip


def render_aadhaar(res, split: str) -> str:
    nd, npg = res["ndocs"], res["npages"]
    L = [f"### Aadhaar / VID number detector (text layer + OCR) - `{split}` split", ""]
    L += [
        f"Date: {dt.date.today().isoformat()}. Docs: {sum(nd.values())} (born_digital {nd['born_digital']}, "
        f"scanned {nd['scanned']}); pages: {sum(npg.values())}.",
        "",
        f"Matching rule: findings of the same type match a GT box with IoU >= {IOU_MIN} or covering >= "
        f"{COVER_MIN:.0%} of it (greedy by confidence). Decoy false positive = any AADHAAR/VID finding with "
        f"IoU >= {IOU_MIN} against a DECOY_NUMBER box. Reports contain counts only, never number values.",
        "",
        "Recall per type:",
        "",
        "| mode | type | GT | found | recall |",
        "|---|---|---|---|---|",
    ]
    for m in MODES:
        for t in res["types"]:
            n, k = res["gt"][m][t], res["tp"][m][t]
            L.append(f"| {m} | {t} | {n} | {k} | {_fmt(k / n if n else float('nan'))} |")
    L += [
        "",
        "Recall per subtype:",
        "",
        "| mode | type | subtype | GT | recall |",
        "|---|---|---|---|---|",
    ]
    for m in MODES:
        for key in sorted(res["sub_n"][m]):
            n, k = res["sub_n"][m][key], res["sub_tp"][m][key]
            L.append(f"| {m} | {key[0]} | {key[1]} | {n} | {_fmt(k / n)} |")
    L += ["", "False positives:", "", "| mode | decoy boxes | decoy FPs (AADHAAR) | decoy FPs (VID) | other unmatched AADHAAR/VID |",
          "|---|---|---|---|---|"]  # fmt: skip
    for m in MODES:
        L.append(
            f"| {m} | {res['decoy_n'][m]} | {res['decoy_fp'][m]['AADHAAR']} | {res['decoy_fp'][m]['VID']} | "
            f"{sum(res['other_fp'][m].values())} |"
        )
    lat = res["lat"]
    L += [
        "",
        f"Latency per page (ms): p50 {_pct(lat, 0.5):.0f}, p95 {_pct(lat, 0.95):.0f}.",
        "",
        CAVEAT,
        "",
    ]
    return "\n".join(L)


# ------------------------------------------------------------------ output
def write_section(out: Path, key: str, body: str) -> None:
    start, end = f"<!-- eval:{key}:start -->", f"<!-- eval:{key}:end -->"
    block = f"{start}\n{body}\n{end}\n"
    text = out.read_text() if out.exists() else "# ThumbShield metrics (v1)\n\n"
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.S)
    text = (
        pat.sub(lambda _m: block, text) if pat.search(text) else text.rstrip("\n") + "\n\n" + block
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--detector", choices=("classical", "aadhaar"), required=True)
    ap.add_argument("--split", choices=("val", "test", "train"), default="val")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--show-misses", action="store_true")
    a = ap.parse_args()
    if a.detector == "classical":
        res = eval_classical(a.split, a.limit)
        body = render_classical(res, a.split)
        if a.show_misses:
            for m in res["misses"]:
                print("MISS", *m)
    else:
        res = eval_aadhaar(a.split, a.limit)
        body = render_aadhaar(res, a.split)
    print(body)
    if a.out:
        write_section(
            a.out if a.out.is_absolute() else ROOT / a.out, f"{a.detector}:{a.split}", body
        )


if __name__ == "__main__":
    main()
