"""SurakshitID: decision gate, presets, badge/ledger, voice parser and the armor pipeline."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pymupdf
import pytest
from PIL import Image

from backend.app.armor_pipeline import armor, mask_rects
from backend.app.core import badge, decision, id_detect, presets, voice_intent
from backend.app.core.decision import ArmorSummary, decide_armor
from backend.app.core.verify_raster import pdf_facts, png_chunks
from synth.idcard_gen import phone_photo, render_id, to_jpeg_with_exif


def _summary(**kw) -> ArmorSummary:
    base = dict(preset="hotel", recipient="Taj Hotel", valid_days=2, doc_found=True,
                blur_score=500.0, ocr_quality=0.9, finding_types=("AADHAAR", "FACE"))
    return ArmorSummary(**{**base, **kw})


# ---- System-One gate -------------------------------------------------------------------

def test_gate_rules_and_order():
    assert decide_armor(_summary()).decision == "ARMOR_AND_ISSUE"
    assert decide_armor(_summary(blur_score=5)).decision == "BLOCK_FOR_REVIEW"
    # hard-to-read text no longer refuses: careful mode issues the copy and hides more
    assert decide_armor(_summary(ocr_quality=0.2)).decision == "ARMOR_AND_ISSUE"
    assert decide_armor(_summary(finding_types=("FACE",))).decision == "BLOCK_FOR_REVIEW"
    assert decide_armor(_summary(unmaskable=1)).decision == "BLOCK_FOR_REVIEW"
    assert decide_armor(_summary(preset=None)).decision == "INSUFFICIENT_PURPOSE"
    assert decide_armor(_summary(recipient=" a ")).decision == "INSUFFICIENT_PURPOSE"
    assert decide_armor(_summary(valid_days=8)).decision == "INSUFFICIENT_PURPOSE"
    assert decide_armor(_summary(verification="fail")).decision == "BLOCK_FOR_REVIEW"
    # safety outranks purpose: blurry AND no purpose -> blocked, not "insufficient purpose"
    g = decide_armor(_summary(blur_score=5, preset=None))
    assert g.decision == "BLOCK_FOR_REVIEW" and g.reasons[0] == "Cannot verify safely"


def test_gate_is_fast():
    s = _summary()
    worst = max(decide_armor(s).elapsed_us for _ in range(2000))
    assert worst < 5000  # < 5 ms, every call


def test_agents_can_only_escalate():
    ok = decide_armor(_summary())
    assert decision.escalate(ok, "BLOCK_FOR_REVIEW", "tamper").decision == "BLOCK_FOR_REVIEW"
    blocked = decide_armor(_summary(blur_score=1))
    assert decision.escalate(blocked, "ARMOR_AND_ISSUE", "looks fine") is blocked


def test_every_preset_destroys_prints_and_vid():
    for p in presets.PRESETS.values():
        assert presets.action_for(p, "FINGERPRINT") == "MASK"
        assert presets.action_for(p, "VID") == "MASK"
        assert presets.action_for(p, "FACE") == "KEEP"
        assert presets.action_for(p, "AADHAAR") in ("MASK", "MASK_PARTIAL")
    assert presets.action_for(presets.PRESETS["xerox"], "NUMBER") == "MASK"
    assert presets.action_for(presets.PRESETS["hotel"], "QR") == "MASK"
    assert presets.action_for(presets.PRESETS["bank_loan"], "PAN") == "KEEP"


def test_partial_mask_keeps_last_four():
    digits = [(100 + 30 * i + 15 * (i // 4), 50, 125 + 30 * i + 15 * (i // 4), 90)
              for i in range(12)]
    f = id_detect.IdFinding(type="AADHAAR", bbox_px=(100, 50, 485, 90), digits_px=digits,
                            confidence=1, source="t")
    (r,) = mask_rects(f, "MASK_PARTIAL", 300, (600, 1000))
    assert r[0] <= digits[0][0] and r[2] >= digits[7][2]  # first 8 covered
    assert r[2] <= digits[8][0]  # 9th digit untouched


def test_pan_ocr_repair():
    assert id_detect.pan_candidate("ABCPE01234F") is None  # 11 chars
    assert id_detect.pan_candidate("ABCP01234F") == "ABCPO1234F"  # 0->O in a letter slot
    assert id_detect.pan_candidate("ABCPE1234F") == "ABCPE1234F"
    assert id_detect.pan_candidate("ABCPE12З4F") is None
    assert id_detect.pan_candidate("A8CPEI234F") == "ABCPE1234F"  # 8->B, I->1 by position


# ---- badge / ledger --------------------------------------------------------------------

def _sealed(tmp_path, rgb):
    s = badge.Sealer(tmp_path)
    qr_rect = (0, 0, 10, 10)
    tiles = badge.tile_hashes(rgb, 32, qr_rect)
    now = datetime.now(UTC)
    core = {"v": 1, "armor_id": "SKID-TEST-0001", "preset": "hotel", "recipient": "X",
            "purpose": "HOTEL CHECK-IN ONLY", "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(), "width": rgb.shape[1],
            "height": rgb.shape[0], "tile_px": 32, "qr_rect": list(qr_rect),
            "sha256": badge.pixel_sha256(rgb, qr_rect), "tiles_root": badge.merkle_root(tiles)}
    return s, s.seal(core, tiles)


def test_signature_ledger_and_tamper_detection(tmp_path):
    rgb = np.random.default_rng(0).integers(0, 255, (200, 300, 3), dtype=np.uint8)
    s, b = _sealed(tmp_path, rgb)
    assert badge.check_signature(b)
    assert b["ledger_index"] == 0 and b["prev_hash"] == badge.GENESIS
    forged = {**b, "recipient": "Someone else"}
    assert not badge.check_signature(forged)
    _, b2 = _sealed(tmp_path, rgb)
    assert b2["prev_hash"] == b["block_hash"] and s.ledger_ok()
    tiles = s.lookup("SKID-TEST-0001")["tiles"]
    edited = rgb.copy()
    edited[100, 150] ^= 1  # one bit in one pixel
    got = badge.tile_hashes(edited, 32, (0, 0, 10, 10))
    bad = [i for i, (x, y) in enumerate(zip(got, tiles, strict=True)) if x != y]
    cols = (300 + 31) // 32
    assert bad == [(100 // 32) * cols + 150 // 32]


def test_ledger_detects_rewrite(tmp_path):
    rgb = np.zeros((64, 64, 3), np.uint8)
    s, _ = _sealed(tmp_path, rgb)
    _sealed(tmp_path, rgb)
    lines = s.ledger.read_text().splitlines()
    s.ledger.write_text("\n".join([lines[1].replace('"index": 1', '"index": 0')]) + "\n")
    assert not s.ledger_ok()


# ---- voice -----------------------------------------------------------------------------

def test_voice_command():
    r = voice_intent.parse("Hey Surakshit, armor my Aadhaar for Goa Taj Hotel for 2 days")
    assert (r["preset"], r["recipient"], r["valid_days"], r["document"]) == (
        "hotel", "Goa Taj Hotel", 2, "aadhaar")
    assert r["ok"] and r["parse_ms"] < 5
    r = voice_intent.parse("armour my pan for HDFC bank loan")
    assert r["preset"] == "bank_loan" and r["document"] == "pan" and r["valid_days"] == 15
    r = voice_intent.parse("protect my aadhaar for xerox")
    assert not r["ok"] and r["missing"] == ["recipient"]
    r = voice_intent.parse("armor aadhaar for Taj hotel for 3 weeks")
    assert r["valid_days"] == 7 and any("max" in m for m in r["missing"])


# ---- pipeline --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sealer(tmp_path_factory):
    return badge.Sealer(tmp_path_factory.mktemp("armor"))


@pytest.fixture(scope="module")
def hotel_front(sealer):
    rgb, gt = render_id(1, "aadhaar_front")
    photo, _ = phone_photo(rgb, gt, 1)
    return armor(to_jpeg_with_exif(photo), "hotel", "Taj Hotel, Goa", 2, sealer)


def test_hotel_armor_end_to_end(hotel_front, sealer):
    o = hotel_front
    r = o.result
    assert r["decision"] == "ARMOR_AND_ISSUE", r["reasons"]
    assert r["verification"]["status"] == "pass"
    assert {"EXIF:GPSInfo", "EXIF:Make"} <= set(r["preprocess"]["metadata_removed"])
    assert r["decision_us"] < 5000
    types = {f["type"]: f["action"] for f in r["findings"]}
    assert types["AADHAAR"] == "MASK_PARTIAL" and types["VID"] == "MASK"
    # masks are 0x00 in the exported PNG and PDF
    png = cv2.cvtColor(cv2.imdecode(np.frombuffer(o.png, np.uint8), 1), cv2.COLOR_BGR2RGB)
    assert all(png[y0:y1, x0:x1].max() == 0 for x0, y0, x1, y1 in r["masks_px"])
    assert set(png_chunks(o.png)) == {"IHDR", "IDAT", "IEND"}
    assert not Image.open(io.BytesIO(o.png)).getexif()
    f = pdf_facts(o.pdf)
    assert f["text_chars"] == 0 and not f["metadata"] and f["images"] == 1
    assert "".join(p.get_text() for p in pymupdf.open(stream=o.pdf, filetype="pdf")) == ""
    # findings never carry a full number
    for x in r["findings"]:
        v = x["value_masked"] or ""
        assert sum(c.isdigit() for c in v) <= 4
    # the badge verifies, and lives in the hash-chained ledger
    assert badge.verify_image(o.final_rgb, sealer)["status"] == "AUTHENTIC"
    assert sealer.ledger_ok()


def test_tamper_is_located(hotel_front, sealer):
    img = hotel_front.final_rgb.copy()
    img[200:240, 60:120] = 255  # paint over part of the photo/watermark
    rep = badge.verify_image(img, sealer)
    assert rep["status"] == "FORGERY_DETECTED"
    x0, y0, x1, y1 = rep["altered_regions"][0]
    assert x0 <= 60 and y0 <= 200 and x1 >= 120 and y1 >= 240
    assert x1 - x0 <= 128 and y1 - y0 <= 96  # localised to tiles, not the whole page
    crop = hotel_front.final_rgb[50:]
    assert badge.verify_image(crop, sealer)["status"] == "FORGERY_DETECTED"
    jpeg = cv2.imdecode(cv2.imencode(".jpg", hotel_front.final_rgb)[1], 1)
    assert badge.verify_image(jpeg, sealer)["status"] in ("FORGERY_DETECTED", "NO_BADGE")


def test_expired_copy(hotel_front, sealer):
    later = datetime.now(UTC) + timedelta(days=30)
    assert badge.verify_image(hotel_front.final_rgb, sealer, now=later)["status"] == "EXPIRED"


def test_blurry_photo_is_refused(sealer):
    rgb, gt = render_id(5, "aadhaar_front")
    photo, _ = phone_photo(rgb, gt, 5, blur=3.5)
    o = armor(to_jpeg_with_exif(photo), "hotel", "Taj Hotel", 2, sealer)
    assert o.result["decision"] == "BLOCK_FOR_REVIEW"
    assert o.result["reasons"][0] == "Cannot verify safely"
    assert o.png is None and o.result["badge"] is None


def test_insufficient_purpose(sealer):
    rgb, _ = render_id(2, "pan")
    png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))[1].tobytes()
    o = armor(png, "xerox", "", 1, sealer)
    assert o.result["decision"] == "INSUFFICIENT_PURPOSE" and o.png is None


def test_kyc_sheet_thumbprint_destroyed(sealer):
    rgb, gt = render_id(3, "kyc_sheet")
    png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))[1].tobytes()
    o = armor(png, "xerox", "Sharma Xerox", 1, sealer)
    assert o.result["decision"] == "ARMOR_AND_ISSUE", o.result["reasons"]
    zero = np.zeros(rgb.shape[:2], bool)
    for x0, y0, x1, y1 in o.result["masks_px"]:
        zero[y0:y1, x0:x1] = True
    for a in gt["annotations"]:
        if a["type"] in ("FINGERPRINT", "QR", "PAN", "AADHAAR"):
            x0, y0, x1, y1 = a["bbox_px"]
            assert zero[y0:y1, x0:x1].mean() > 0.97, a["type"]
            if a["type"] == "FINGERPRINT":  # every pixel of the print is 0x00
                assert o.final_rgb[y0:y1, x0:x1].max() == 0


def test_careful_mode_hides_more():
    from backend.app.core.decision import needs_care
    s = _summary(ocr_quality=0.3, verified_tokens=0)
    assert needs_care(s) and decide_armor(s).decision == "ARMOR_AND_ISSUE"
    assert any("hard to read" in r for r in decide_armor(s).reasons)
    assert decide_armor(_summary(finding_types=("FACE",))).decision == "BLOCK_FOR_REVIEW"
