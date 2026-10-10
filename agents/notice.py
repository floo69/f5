from __future__ import annotations

import re

from mcp_servers.casestore_server import save_notice_draft


def _safe(text: str) -> str:
    text = re.sub(r"(?<!\d)[2-9]\d{11}(?!\d)", "XXXX XXXX XXXX", text)
    return re.sub(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b", "XXXX XXXX XXXX", text)


def draft_notices(rows: list[dict]) -> dict:
    """Create drafts only; never sends notices and never includes complete Aadhaar numbers."""
    doc_ids = [str(row.get("portal_id", row.get("doc_id", ""))) for row in rows]
    affected = ", ".join(doc_ids) or "the affected synthetic records"
    total_fp = sum(int(row.get("thumbprints", 0)) for row in rows)
    total_aadhaar = sum(int(row.get("aadhaar", 0)) for row in rows)
    takedown = _safe(f"Subject: Synthetic registry masking request\nAffected documents: {affected}\nFindings: {total_fp} thumb impressions and {total_aadhaar} Aadhaar findings. Please mask sensitive regions and republish redacted versions with certificates. This is a draft for human review only.")
    english = _safe(f"Citizen advisory (synthetic demo): a public record contained a sensitive identity exposure. Do not share biometric details. Use UIDAI's official channels to lock biometrics where available and report suspected fraud to 1930 or cybercrime.gov.in. Affected synthetic records: {affected}.")
    malayalam = _safe("പൗര ഉപദേശം (സിന്തറ്റിക് ഡെമോ): ഒരു പൊതു രേഖയിൽ സ്വകാര്യ വിവരങ്ങൾ കണ്ടെത്തി. ഔദ്യോഗിക UIDAI മാർഗ്ഗങ്ങളിലൂടെ ബയോമെട്രിക് ലോക്ക് ഓപ്ഷനുകൾ പരിശോധിക്കുക. തട്ടിപ്പ് സംശയമുണ്ടെങ്കിൽ 1930 അല്ലെങ്കിൽ cybercrime.gov.in-ൽ റിപ്പോർട്ട് ചെയ്യുക.")
    saved = [save_notice_draft("registry_takedown", "en", takedown, doc_ids), save_notice_draft("citizen_advisory", "en+ml", english + "\n\n" + malayalam, doc_ids)]
    return {"drafts": [{"kind": "registry_takedown", "lang": "en", "body": takedown}, {"kind": "citizen_advisory", "lang": "en+ml", "body": english + "\n\n" + malayalam}], "saved": saved}
