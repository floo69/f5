"""FastMCP-compatible case store and secure synthetic-PDF fetch service.

The installed MCP v2 SDK renamed FastMCP to ``MCPServer``; this module uses that
documented equivalent while retaining stdio transport through ``mcp.run()``.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from mcp.server.mcpserver import MCPServer

from backend.app.settings import settings

mcp = MCPServer("thumbshield-casestore")
DATA_ROOT = Path("data").resolve()
DB_PATH = DATA_ROOT / "cases.db"
MAX_PDF_BYTES = 25 * 1024 * 1024


def _safe_data_path(path: str | Path, *, pdf: bool = False) -> Path:
    raw = Path(path)
    if pdf and raw.suffix.lower() != ".pdf":
        raise ValueError("only PDF files are supported")
    resolved = raw.resolve(strict=False)
    if resolved != DATA_ROOT and DATA_ROOT not in resolved.parents:
        raise ValueError("path must resolve inside data/")
    # A symlink is permitted only when its resolved target remains in data/.
    current = raw if raw.is_absolute() else Path.cwd() / raw
    for parent in [current, *current.parents]:
        if parent == DATA_ROOT.parent:
            break
        if parent.is_symlink() and DATA_ROOT not in parent.resolve().parents:
            raise ValueError("symlink escapes data/")
    return resolved


def _db() -> sqlite3.Connection:
    DATA_ROOT.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
          doc_id TEXT PRIMARY KEY, source_url TEXT, sro TEXT, year INTEGER,
          doc_no TEXT, local_path TEXT, summary TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'registered'
        );
        CREATE TABLE IF NOT EXISTS notices (
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, lang TEXT, body TEXT, doc_ids TEXT
        );
        CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, timestamp TEXT NOT NULL,
          event_type TEXT NOT NULL, event_json TEXT NOT NULL, previous_hash TEXT NOT NULL, current_hash TEXT NOT NULL
        );
        """
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(audit_log)")}
    if columns and "current_hash" not in columns:
        db.execute("ALTER TABLE audit_log RENAME TO audit_log_legacy")
        db.executescript("""CREATE TABLE audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
          timestamp TEXT NOT NULL, event_type TEXT NOT NULL, event_json TEXT NOT NULL,
          previous_hash TEXT NOT NULL, current_hash TEXT NOT NULL
        );""")
        db.commit()
    return db


def _audit(db: sqlite3.Connection, event_type: str, data: dict) -> None:
    timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
    event_id = uuid.uuid4().hex
    canonical = json.dumps({"event_id": event_id, "timestamp": timestamp, "event_type": event_type, "data": data}, sort_keys=True, separators=(",", ":"))
    previous = db.execute("SELECT current_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    previous_hash = previous[0] if previous else "GENESIS"
    current_hash = hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()
    db.execute("INSERT INTO audit_log(event_id,timestamp,event_type,event_json,previous_hash,current_hash) VALUES (?,?,?,?,?,?)", (event_id, timestamp, event_type, canonical, previous_hash, current_hash))


def _allowlist() -> set[str]:
    values = settings.browser_allowlist.split(",")
    return {v.strip().lower() for v in values if v.strip()}


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("URL must be credential-free HTTP(S)")
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    netloc = f"{host}:{port}"
    allowed = _allowlist()
    if netloc not in allowed and host not in allowed:
        raise ValueError(f"host is not allowlisted: {host}:{port}")
    # The local demo explicitly permits only the configured loopback endpoint.
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("host could not be resolved safely") from exc
    if host in {"localhost", "127.0.0.1"}:
        if not addresses or not addresses.issubset({"127.0.0.1", "::1"}):
            raise ValueError("local allowlist resolved outside loopback")
    else:
        raise ValueError("only the configured local mock portal is enabled")
    return url


def _safe_component(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or fallback


@mcp.tool()
def register_document(source_url: str, sro: str, year: int, doc_no: str, local_path: str) -> str:
    path = _safe_data_path(local_path, pdf=True)
    if not path.is_file() or path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("local path is not a valid PDF")
    doc_id = hashlib.sha256(f"{source_url}|{sro}|{year}|{doc_no}".encode()).hexdigest()[:16]
    db = _db()
    try:
        db.execute("INSERT OR REPLACE INTO documents(doc_id,source_url,sro,year,doc_no,local_path,summary,status) VALUES (?,?,?,?,?,?,?,?)", (doc_id, source_url, sro, year, doc_no, str(path), "", "registered"))
        _audit(db, "register_document", {"doc_id": doc_id, "sro": sro, "year": year, "doc_no": doc_no})
        db.commit()
    finally:
        db.close()
    return doc_id


@mcp.tool()
def record_scan(doc_id: str, summary: dict) -> dict:
    safe = {k: summary[k] for k in ("thumbprints", "aadhaar", "decision", "status", "verification") if k in summary}
    findings = list(summary.get("findings", []))
    for page in summary.get("pages", []):
        for finding in page.get("findings", []):
            findings.append({"page": page.get("page"), **finding})
    safe["findings"] = [{k: f[k] for k in ("type", "page", "confidence", "source") if k in f} for f in findings]
    safe.setdefault("thumbprints", sum(f.get("type") == "FINGERPRINT" for f in findings))
    safe.setdefault("aadhaar", sum(f.get("type") in {"AADHAAR", "VID"} for f in findings))
    db = _db()
    try:
        db.execute("UPDATE documents SET summary=?, status=? WHERE doc_id=?", (json.dumps(safe, sort_keys=True), str(safe.get("decision", "scanned")), doc_id))
        _audit(db, "record_scan", {"doc_id": doc_id, "summary": safe})
        db.commit()
    finally:
        db.close()
    return {"ok": True, "doc_id": doc_id}


@mcp.tool()
def list_exposed(sro: str | None = None, year: int | None = None) -> list[dict]:
    db = _db()
    rows = db.execute("SELECT * FROM documents WHERE summary != '' ORDER BY year,doc_no").fetchall()
    db.close()
    out = []
    for row in rows:
        if sro and row["sro"] != sro or year and row["year"] != year:
            continue
        out.append({"doc_id": row["doc_id"], "sro": row["sro"], "year": row["year"], "doc_no": row["doc_no"], **json.loads(row["summary"])})
    return out


@mcp.tool()
def stats() -> dict:
    rows = list_exposed()
    result = {"reviewed_deeds": len(rows), "exposed_deeds": 0, "by_type": {}, "by_sro": {}, "by_year": {}, "by_status": {}}
    for row in rows:
        exposed = int(row.get("thumbprints", 0)) + int(row.get("aadhaar", 0)) > 0
        result["exposed_deeds"] += int(exposed)
        result["by_type"]["thumbprints"] = result["by_type"].get("thumbprints", 0) + int(row.get("thumbprints", 0))
        result["by_type"]["aadhaar"] = result["by_type"].get("aadhaar", 0) + int(row.get("aadhaar", 0))
        result["by_sro"][row["sro"]] = result["by_sro"].get(row["sro"], 0) + 1
        result["by_year"][str(row["year"])] = result["by_year"].get(str(row["year"]), 0) + 1
        result["by_status"][row.get("decision", "unknown")] = result["by_status"].get(row.get("decision", "unknown"), 0) + 1
    return result


@mcp.tool()
def save_notice_draft(kind: str, lang: str, body: str, doc_ids: list[str]) -> dict:
    if kind not in {"registry_takedown", "citizen_advisory"}:
        raise ValueError("unsupported notice kind")
    db = _db()
    try:
        cur = db.execute("INSERT INTO notices(kind,lang,body,doc_ids) VALUES (?,?,?,?)", (kind, lang, body, json.dumps(doc_ids)))
        _audit(db, "save_notice_draft", {"id": cur.lastrowid, "kind": kind, "doc_count": len(doc_ids)})
        db.commit()
        return {"id": cur.lastrowid, "saved": True}
    finally:
        db.close()


@mcp.tool()
def save_mission_report(mission: str, body: str) -> dict:
    db = _db()
    try:
        cur = db.execute("INSERT INTO reports(mission,body) VALUES (?,?)", (mission, body))
        _audit(db, "save_mission_report", {"id": cur.lastrowid})
        db.commit()
        return {"id": cur.lastrowid, "saved": True}
    finally:
        db.close()


@mcp.tool()
def verify_audit_chain() -> dict:
    db = _db()
    rows = db.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    previous = "GENESIS"
    for row in rows:
        expected = hashlib.sha256((previous + row["event_json"]).encode()).hexdigest()
        if expected != row["current_hash"] or row["previous_hash"] != previous:
            db.close()
            return {"ok": False, "broken_at": row["id"], "event_id": row["event_id"]}
        previous = row["current_hash"]
    db.close()
    return {"ok": True, "broken_at": None}


@mcp.tool()
def fetch_pdf(url: str, sro: str = "all", year: int = 0) -> str:
    current = _validate_url(url)
    parsed = urlparse(current)
    filename = _safe_component(Path(parsed.path).name, "document.pdf")
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    destination = _safe_data_path(DATA_ROOT / "inbox" / _safe_component(sro, "all") / str(year or "unknown") / filename, pdf=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        for _ in range(5):
            response = client.get(current)
            if response.is_redirect:
                current = _validate_url(urljoin(current, response.headers["location"]))
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "application/pdf" not in content_type or not response.content.startswith(b"%PDF-"):
                raise ValueError("response is not a valid PDF")
            if len(response.content) > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds 25 MB")
            destination.write_bytes(response.content)
            return str(destination)
    raise ValueError("too many redirects")


if __name__ == "__main__":
    mcp.run()
