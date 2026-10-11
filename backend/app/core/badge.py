"""Tamper-evident badge: Ed25519 signature over per-tile pixel hashes + an append-only ledger.

The armored image is cut into `tile_px` squares. Each tile's SHA-256 (with its grid position)
goes into a Merkle tree; the root, the purpose fields and the previous ledger hash form a
block whose hash is signed with the device key. Verification recomputes the tile hashes of a
submitted image, so any edited pixel is located to its tile, i.e. exact coordinates.

The badge QR printed on the image carries only `SKID1|<armor_id>|<root prefix>` — no personal
data. Its own square is zero-filled before hashing (it cannot contain its own hash).

Honest limit: hashes are exact, so only lossless copies (PNG / our PDF) verify. A JPEG
re-encode or a photo of the screen reports FORGERY_DETECTED, never a false AUTHENTIC.
Stored per badge (data/armor/registry/<id>.json): hashes, purpose, recipient, mask rects.
Never the image, never document text.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

TILE_PX = 32
QR_PREFIX = "SKID1|"
GENESIS = "0" * 64
_lock = threading.Lock()

Rect = tuple[int, int, int, int]


def _canon(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _blank(rgb: np.ndarray, exclude: Rect | None) -> np.ndarray:
    if exclude is None:
        return rgb
    out = rgb.copy()
    x0, y0, x1, y1 = exclude
    out[y0:y1, x0:x1] = 0
    return out


def tile_hashes(rgb: np.ndarray, tile_px: int = TILE_PX, exclude: Rect | None = None
                ) -> list[str]:
    """Row-major per-tile hashes (hex, 128-bit). Edge tiles are partial."""
    img = np.ascontiguousarray(_blank(rgb, exclude))
    h, w = img.shape[:2]
    out = []
    for ty, y in enumerate(range(0, h, tile_px)):
        for tx, x in enumerate(range(0, w, tile_px)):
            m = hashlib.sha256(f"{tx},{ty}|".encode())
            m.update(np.ascontiguousarray(img[y : y + tile_px, x : x + tile_px]).tobytes())
            out.append(m.hexdigest()[:32])
    return out


def pixel_sha256(rgb: np.ndarray, exclude: Rect | None = None) -> str:
    return hashlib.sha256(np.ascontiguousarray(_blank(rgb, exclude)).tobytes()).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    level = [bytes.fromhex(x) for x in leaves] or [b""]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(a + b).digest() for a, b in zip(level[::2], level[1::2],
                                                               strict=True)]
    return hashlib.sha256(level[0]).hexdigest()


def qr_payload(armor_id: str, root: str) -> str:
    return f"{QR_PREFIX}{armor_id}|{root[:24]}"


def render_qr(payload: str, module_px: int) -> np.ndarray:
    """Black-on-white RGB QR with the standard 4-module quiet zone."""
    q = cv2.QRCodeEncoder.create().encode(payload)  # 0/255 grey, 1px per module
    q = cv2.copyMakeBorder(q, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    q = cv2.resize(q, None, fx=module_px, fy=module_px, interpolation=cv2.INTER_NEAREST)
    return np.repeat(q[:, :, None], 3, axis=2)


def find_badge_qr(rgb: np.ndarray) -> tuple[str, Rect] | None:
    """Locate our own badge QR; other QR payloads are never returned or logged.
    Tries the whole image, then the bottom strip (where the badge lives) at 1x and 2x."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    det = cv2.QRCodeDetector()
    y_strip = int(gray.shape[0] * 0.6)
    strip = gray[y_strip:]
    for img, oy, scale in ((gray, 0, 1.0), (strip, y_strip, 1.0), (strip, y_strip, 2.0)):
        if scale != 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        ok, texts, pts, _ = det.detectAndDecodeMulti(img)
        if not ok or pts is None:
            continue
        for t, p in zip(texts, pts, strict=False):
            if t.startswith(QR_PREFIX):
                xs, ys = p[:, 0] / scale, p[:, 1] / scale + oy
                return t, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return None


class Sealer:
    """Device key, append-only ledger and badge registry under `root`."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.reg = self.root / "registry"
        self.ledger = self.root / "ledger.jsonl"

    # ---- key
    def _key(self) -> Ed25519PrivateKey:
        path = self.root / "keys" / "device_ed25519.pem"
        if path.exists():
            k = serialization.load_pem_private_key(path.read_bytes(), password=None)
            assert isinstance(k, Ed25519PrivateKey)
            return k
        path.parent.mkdir(parents=True, exist_ok=True)
        k = Ed25519PrivateKey.generate()
        path.write_bytes(k.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
        path.chmod(0o600)
        return k

    def public_key_hex(self) -> str:
        return self._key().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()

    # ---- ledger
    def _tail(self) -> tuple[int, str]:
        if not self.ledger.exists():
            return -1, GENESIS
        last = None
        with self.ledger.open() as f:
            for line in f:
                if line.strip():
                    last = line
        if last is None:
            return -1, GENESIS
        e = json.loads(last)
        return e["index"], e["block_hash"]

    def seal(self, core: dict, tiles: list[str], extra: dict | None = None) -> dict:
        """Sign `core` (purpose fields + tiles_root + sha256), chain it, store the registry
        entry and return the full badge."""
        with _lock:
            idx, prev = self._tail()
            block = {**core, "prev_hash": prev, "ledger_index": idx + 1}
            block_hash = hashlib.sha256(_canon(block)).hexdigest()
            key = self._key()
            sig = key.sign(bytes.fromhex(block_hash)).hex()
            badge = {**block, "block_hash": block_hash, "public_key": self.public_key_hex(),
                     "signature": sig}
            self.root.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a") as f:
                f.write(json.dumps({"index": idx + 1, "armor_id": core["armor_id"],
                                    "issued_at": core["issued_at"], "prev_hash": prev,
                                    "block_hash": block_hash}) + "\n")
            self.reg.mkdir(parents=True, exist_ok=True)
            (self.reg / f"{core['armor_id']}.json").write_text(
                json.dumps({"badge": badge, "tiles": tiles, **(extra or {})}))
        return badge

    def lookup(self, armor_id: str) -> dict | None:
        if not armor_id.replace("-", "").isalnum():
            return None
        p = self.reg / f"{armor_id}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def revoke(self, armor_id: str) -> dict | None:
        """Owner withdraws a copy: marked in the registry and appended to the ledger chain."""
        with _lock:
            entry = self.lookup(armor_id)
            if entry is None:
                return None
            if not entry.get("revoked_at"):
                now = datetime.now(UTC).isoformat(timespec="seconds")
                entry["revoked_at"] = now
                idx, prev = self._tail()
                ev = {"index": idx + 1, "armor_id": armor_id, "event": "revoke",
                      "issued_at": now, "prev_hash": prev}
                ev["block_hash"] = hashlib.sha256(_canon(ev)).hexdigest()
                with self.ledger.open("a") as f:
                    f.write(json.dumps(ev) + "\n")
                (self.reg / f"{armor_id}.json").write_text(json.dumps(entry))
        return copy_summary(entry)

    def copies(self) -> list[dict]:
        if not self.reg.exists():
            return []
        out = [copy_summary(json.loads(p.read_text())) for p in self.reg.glob("SKID-*.json")]
        return sorted(out, key=lambda c: c["issued_at"], reverse=True)

    def ledger_ok(self) -> bool:
        """Re-walk the chain: every entry links to its predecessor."""
        prev = GENESIS
        if not self.ledger.exists():
            return True
        for i, line in enumerate(self.ledger.read_text().splitlines()):
            e = json.loads(line)
            if e["index"] != i or e["prev_hash"] != prev:
                return False
            prev = e["block_hash"]
        return True


def copy_summary(entry: dict, now: datetime | None = None) -> dict:
    from .presets import PRESETS

    b = entry["badge"]
    now = now or datetime.now(UTC)
    revoked = entry.get("revoked_at")
    status = ("revoked" if revoked else
              "expired" if datetime.fromisoformat(b["expires_at"]) < now else "active")
    p = PRESETS.get(b["preset"])
    return {"armor_id": b["armor_id"], "preset": b["preset"],
            "preset_label": p.label if p else b["preset"], "recipient": b["recipient"],
            "purpose": b["purpose"], "issued_at": b["issued_at"], "expires_at": b["expires_at"],
            "status": status, "revoked_at": revoked}


def check_signature(badge: dict) -> bool:
    block = {k: v for k, v in badge.items() if k not in ("block_hash", "public_key", "signature")}
    if hashlib.sha256(_canon(block)).hexdigest() != badge.get("block_hash"):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(badge["public_key"])).verify(
            bytes.fromhex(badge["signature"]), bytes.fromhex(badge["block_hash"]))
    except (InvalidSignature, ValueError, KeyError):
        return False
    return True


def _merge(rects: list[list[int]]) -> list[list[int]]:
    """Merge touching/overlapping rects (tile-aligned) into larger regions."""
    rects = [list(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out: list[list[int]] = []
        for r in rects:
            for o in out:
                if r[0] <= o[2] and o[0] <= r[2] and r[1] <= o[3] and o[1] <= r[3]:
                    o[:] = [min(o[0], r[0]), min(o[1], r[1]), max(o[2], r[2]), max(o[3], r[3])]
                    changed = True
                    break
            else:
                out.append(r)
        rects = out
    return sorted(rects, key=lambda r: (r[1], r[0]))


def verify_image(rgb: np.ndarray, sealer: Sealer, now: datetime | None = None) -> dict:
    """VerifyReport (docs/ARMOR_CONTRACT.md) for a submitted RGB image."""
    h, w = rgb.shape[:2]
    rep = {"status": "NO_BADGE", "armor_id": None, "purpose": None, "recipient": None,
           "expires_at": None, "signature_ok": False, "width": w, "height": h,
           "tile_px": TILE_PX, "altered_regions": [], "altered_tiles": 0, "total_tiles": 0,
           "detail": "No SurakshitID badge QR found on this image"}
    found = find_badge_qr(rgb)
    if found is None:
        return rep
    payload, _ = found
    _, armor_id, root_prefix = (payload.split("|") + ["", ""])[:3]
    entry = sealer.lookup(armor_id)
    rep["armor_id"] = armor_id
    if entry is None:
        rep.update(status="UNKNOWN_BADGE",
                   detail="Badge not issued by this verifier (no ledger entry)")
        return rep
    b = entry["badge"]
    rep.update(purpose=b["purpose"], recipient=b["recipient"], expires_at=b["expires_at"],
               signature_ok=check_signature(b), tile_px=b["tile_px"])
    tiles = entry["tiles"]
    rep["total_tiles"] = len(tiles)
    problems = []
    if not rep["signature_ok"]:
        problems.append("badge signature invalid")
    if not b["tiles_root"].startswith(root_prefix):
        problems.append("badge QR does not match the ledger")
    if (w, h) != (b["width"], b["height"]):
        rep.update(status="FORGERY_DETECTED",
                   detail=f"Image size changed from {b['width']}x{b['height']} to {w}x{h} "
                          "(cropped, resized or re-captured)")
        return rep
    tp = b["tile_px"]
    got = tile_hashes(rgb, tp, tuple(b["qr_rect"]))
    cols = (w + tp - 1) // tp
    bad = [i for i, (a, e) in enumerate(zip(got, tiles, strict=True)) if a != e]
    regions = _merge([[(i % cols) * tp, (i // cols) * tp, min((i % cols + 1) * tp, w),
                       min((i // cols + 1) * tp, h)] for i in bad])
    rep.update(altered_tiles=len(bad), altered_regions=regions)
    if bad:
        problems.append(f"{len(bad)} of {len(tiles)} tiles altered")
    if problems:
        rep.update(status="FORGERY_DETECTED", detail="; ".join(problems))
        return rep
    if entry.get("revoked_at"):
        rep.update(status="REVOKED",
                   detail=f"The owner withdrew this copy on {entry['revoked_at'][:10]}")
        return rep
    now = now or datetime.now(UTC)
    if datetime.fromisoformat(b["expires_at"]) < now:
        rep.update(status="EXPIRED", detail=f"Valid until {b['expires_at']}; copy has expired")
        return rep
    rep.update(status="AUTHENTIC", detail="Every pixel matches the sealed copy")
    return rep
