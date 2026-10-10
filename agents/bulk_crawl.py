"""Deterministic, synthetic-only crawler for repeatable evaluation."""
from __future__ import annotations

import re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import httpx

from mcp_servers.casestore_server import fetch_pdf, record_scan, register_document
from mcp_servers.scanner_server import scan_pdf

ALLOWLIST = {"localhost:8100", "127.0.0.1:8100"}


def _checked(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in ALLOWLIST:
        raise ValueError("browser URL host is not allowlisted")
    return url


def crawl(base_url: str = "http://127.0.0.1:8100", sro: str = "", year_from: int = 2018,
          year_to: int = 2024, max_docs: int = 120, emit=None) -> list[dict]:
    if max_docs < 1: return []
    _checked(base_url); results = []; seen = set(); last_request = 0.0

    def request(client, method, url, **kwargs):
        nonlocal last_request
        delay = 1.0 - (time.monotonic() - last_request)
        if delay > 0: time.sleep(delay)
        checked = _checked(url); response = client.request(method, checked, **kwargs); last_request = time.monotonic(); response.raise_for_status(); return response

    def event(kind, **data):
        if emit: emit({"type": kind, "timestamp": time.time(), **data})

    with httpx.Client(follow_redirects=False, timeout=20) as client:
        response = request(client, "GET", urljoin(base_url, "/"))
        client.cookies.update(response.cookies)
        request(client, "POST", urljoin(base_url, "/agree"), data={"agree": "on"})
        for page in range(1, 100):
            response = request(client, "GET", urljoin(base_url, "/search"), params={"page": page, "sro": sro} if sro else {"page": page})
            links = list(dict.fromkeys(re.findall(r'href="(/deed/[^"/]+)"', response.text)))
            if not links: break
            event("results_discovered", page=page, count=len(links))
            for link in links:
                portal_id = link.rsplit("/", 1)[-1]
                if portal_id in seen: continue
                seen.add(portal_id)
                detail = request(client, "GET", urljoin(base_url, link)).text
                year_match = re.search(r"Year:</strong>\s*(\d{4})", detail)
                year = int(year_match.group(1)) if year_match else 0
                if not year_from <= year <= year_to: continue
                doc_match = re.search(r"Document number:</strong>\s*([^<]+)", detail)
                party_match = re.search(r"Party:</strong>\s*([^<]+)", detail)
                pdf_url = _checked(urljoin(base_url, f"/deed/{portal_id}/pdf"))
                local = fetch_pdf(pdf_url, sro=sro or "all", year=year)
                registration = register_document(pdf_url, sro, year, doc_match.group(1).strip() if doc_match else portal_id, local)
                event("pdf_fetched", doc_id=registration)
                summary = scan_pdf(local)
                record_scan(registration, summary)
                thumbprints = sum(sum(f["type"] == "FINGERPRINT" for f in p["findings"]) for p in summary["pages"])
                aadhaar = sum(sum(f["type"] in {"AADHAAR", "VID"} for f in p["findings"]) for p in summary["pages"])
                row = {"portal_id": portal_id, "doc_id": registration, "local_path": local,
                       "doc_no": doc_match.group(1).strip() if doc_match else portal_id,
                       "party_name": party_match.group(1).strip() if party_match else "Synthetic Party",
                       "year": year, "thumbprints": thumbprints, "aadhaar": aadhaar,
                       "decision": summary.get("decision"), "status": summary.get("verification")}
                results.append(row); event("scan_completed", doc_id=row["doc_id"])
                if len(results) >= max_docs: return results
    return results
