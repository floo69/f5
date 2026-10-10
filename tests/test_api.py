import time

from fastapi.testclient import TestClient

from backend.app import main


def _wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.2)
    raise TimeoutError


def test_process_upload_end_to_end(born_digital_deed, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OUT_DIR", tmp_path)
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["local_only"] is True
        r = client.post("/api/process", files={"file": ("deed.pdf", born_digital_deed.pdf)})
        job = _wait(client, r.json()["job_id"])
        assert job["status"] == "done", job["error"]
        res = job["result"]
        assert res["page_count"] == 2
        assert res["status"] in ("VERIFIED_CLEAN", "BLOCKED_FOR_REVIEW")
        for p in res["pages"]:
            for f in p["findings"]:
                v = f["value_masked"]
                assert v is None or sum(c.isdigit() for c in v) <= 4

        jid = job["job_id"]
        pdf = client.get(f"/api/files/{jid}/redacted")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        cert = client.get(f"/api/files/{jid}/certificate").json()
        assert cert["sha256_out"] == res["sha256_out"]
        assert client.get(f"/api/files/{jid}/certificate.pdf").content[:4] == b"%PDF"
        for view in ("before", "after"):
            png = client.get(f"/api/files/{jid}/page/0.png", params={"view": view})
            assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
        # Only the redacted output + certificate are written; never the original.
        assert sorted(p.name for p in (tmp_path / jid).iterdir()) == [
            "certificate.json",
            "certificate.pdf",
            "redacted.pdf",
        ]


def test_rejects_non_pdf():
    with TestClient(main.app) as client:
        r = client.post("/api/process", files={"file": ("x.pdf", b"not a pdf")})
        assert r.status_code == 400


def test_samples_listed():
    with TestClient(main.app) as client:
        names = [s["name"] for s in client.get("/api/samples").json()]
        assert "sale-deed-born-digital" in names
