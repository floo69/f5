import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.api import armor as armor_api
from backend.app.core import badge


def _wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/api/armor/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.1)
    raise TimeoutError


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(armor_api, "SEALER", badge.Sealer(tmp_path / "armor"))
    monkeypatch.setattr(main, "OUT_DIR", tmp_path / "out")
    with TestClient(main.app) as c:
        yield c


def test_armor_sample_inspect_attack_verify(client, tmp_path):
    assert {p["key"] for p in client.get("/api/presets").json()} >= {"hotel", "xerox"}
    names = [s["name"] for s in client.get("/api/id-samples").json()]
    assert "kyc-sheet-thumbprint" in names
    prev = client.get("/api/id-samples/kyc-sheet-thumbprint.jpg")
    assert prev.status_code == 200 and prev.content[:2] == b"\xff\xd8"

    r = client.post("/api/id-samples/aadhaar-front-photo/armor",
                    data={"preset": "hotel", "recipient": "Taj Hotel, Goa", "valid_days": 2})
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    res = job["result"]
    assert res["decision"] == "ARMOR_AND_ISSUE", res["reasons"]
    assert all(s["status"] == "done" for s in job["steps"])
    jid = job["job_id"]

    for which in ("before", "after"):
        v = client.get(f"/api/armor/{jid}/view.png", params={"which": which})
        assert v.status_code == 200 and v.content[:4] == b"\x89PNG"
    png = client.get(f"/api/armor/{jid}/armored.png").content
    pdf = client.get(f"/api/armor/{jid}/armored.pdf").content
    assert pdf[:4] == b"%PDF"
    assert client.get(f"/api/armor/{jid}/badge.json").json()["armor_id"] == res["armor_id"]

    ins = client.get(f"/api/armor/{jid}/inspect").json()
    assert ins["masks"] and all(m["max"] == 0 and m["unique_values"] == 1
                                and m["entropy_bits"] == 0 for m in ins["masks"])
    assert ins["masks"][0]["hex_sample"].startswith("00 00 00")
    assert ins["pdf"]["text_chars"] == 0 and ins["pdf"]["metadata"] == {}
    assert ins["png"]["chunks"] == ["IHDR", "IDAT", "IEND"] and not ins["png"]["exif"]
    assert ins["brightened_mask_max"] == 0

    for kind in ("erase_watermark", "swap_photo", "unmask", "crop"):
        a = client.post(f"/api/armor/{jid}/attack", json={"kind": kind}).json()
        assert a["verify"]["status"] == "FORGERY_DETECTED", kind
        if kind != "crop":
            assert a["verify"]["altered_regions"]
        assert client.get(a["image_url"]).content[:4] == b"\x89PNG"

    for name, data in (("copy.png", png), ("copy.pdf", pdf)):
        rep = client.post("/api/verify", files={"file": (name, data)}).json()
        assert rep["status"] == "AUTHENTIC" and rep["armor_id"] == res["armor_id"], rep
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    img[100:140, 300:400] = 0
    tampered = cv2.imencode(".png", img)[1].tobytes()
    rep = client.post("/api/verify", files={"file": ("t.png", tampered)}).json()
    assert rep["status"] == "FORGERY_DETECTED" and rep["altered_regions"]
    blank = cv2.imencode(".png", np.full((50, 50, 3), 255, np.uint8))[1].tobytes()
    assert client.post("/api/verify", files={"file": ("b.png", blank)}).json()["status"] == \
        "NO_BADGE"
    # My copies: listed, revocable, and a revoked copy fails verification instantly
    cps = client.get("/api/copies").json()
    assert cps[0]["armor_id"] == res["armor_id"] and cps[0]["status"] == "active"
    rv = client.post(f"/api/copies/{res['armor_id']}/revoke").json()
    assert rv["status"] == "revoked"
    rep = client.post("/api/verify", files={"file": ("copy.png", png)}).json()
    assert rep["status"] == "REVOKED"
    assert client.post("/api/copies/SKID-NOPE-NOPE/revoke").status_code == 404
    # the original capture is never written anywhere; only the ledger/registry/key exist
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                     if p.is_file())
    assert written == ["armor/keys/device_ed25519.pem", "armor/ledger.jsonl",
                       f"armor/registry/{res['armor_id']}.json"]


def test_blocked_job_has_no_downloads(client):
    r = client.post("/api/id-samples/aadhaar-blurry/armor",
                    data={"preset": "hotel", "recipient": "Taj Hotel", "valid_days": 2})
    job = _wait(client, r.json()["job_id"])
    assert job["result"]["decision"] == "BLOCK_FOR_REVIEW"
    jid = job["job_id"]
    assert client.get(f"/api/armor/{jid}/armored.png").status_code == 409
    assert client.get(f"/api/armor/{jid}/view.png", params={"which": "before"}).status_code == 200


def test_voice_route(client):
    r = client.post("/api/voice/parse",
                    json={"text": "Hey Surakshit, armor my Aadhaar for Goa Taj Hotel for 2 days"})
    assert r.json()["recipient"] == "Goa Taj Hotel"


def test_rejects_garbage_upload(client):
    r = client.post("/api/armor", files={"file": ("x.jpg", b"not an image")},
                    data={"preset": "hotel", "recipient": "Taj", "valid_days": 1})
    job = _wait(client, r.json()["job_id"])
    assert job["result"]["decision"] == "BLOCK_FOR_REVIEW"
