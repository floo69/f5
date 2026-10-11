"""Purpose presets: minimum disclosure per everyday sharing situation (pure data).

Thumb impressions and VIDs are destroyed under every preset (hard rule); faces are never
masked (the recipient needs the photo) but the watermark always crosses them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Mask policy tokens
AADHAAR_FIRST8 = "AADHAAR_FIRST8"  # keep only the last 4 digits (UIDAI masked-Aadhaar format)
ALL_NUMBERS = "ALL_NUMBERS"  # every token containing a digit, incl. the Aadhaar last 4
QR = "QR"  # QR codes and 1-D barcodes (Aadhaar QR carries the full demographic record)
PAN = "PAN"
DOB = "DOB"
ADDRESS = "ADDRESS"
ALWAYS = frozenset({"FINGERPRINT", "VID"})


@dataclass(frozen=True, slots=True)
class Preset:
    key: str
    label: str
    purpose: str  # goes into the watermark: "FOR <recipient> <purpose> ONLY"
    policy: frozenset[str]
    masks: tuple[str, ...]
    keeps: tuple[str, ...]
    default_days: int
    max_days: int
    not_valid_for: tuple[str, ...]

    def public(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "masks": list(self.masks),
            "keeps": list(self.keeps),
            "default_days": self.default_days,
            "max_days": self.max_days,
            "not_valid_for": list(self.not_valid_for),
        }


_THUMB = "Thumb impressions"
_FIRST8 = "Aadhaar first 8 digits"
_QR = "QR code / barcode"

PRESETS: dict[str, Preset] = {
    p.key: p
    for p in (
        Preset(
            "hotel", "Hotel Check-in", "HOTEL CHECK-IN",
            frozenset({AADHAAR_FIRST8, QR, PAN}),
            (_FIRST8, _QR, "PAN", "VID", _THUMB),
            ("Photo", "Name", "Address", "Date of birth"),
            2, 7, ("BANKING", "SIM", "LOANS"),
        ),
        Preset(
            "xerox", "Xerox / Print Shop", "PHOTOCOPY",
            frozenset({ALL_NUMBERS, QR, PAN, DOB, ADDRESS}),
            ("Every number", "Address", "Date of birth", _QR, "PAN", _THUMB),
            ("Photo", "Name"),
            1, 1, ("BANKING", "SIM", "LOANS", "HOTEL", "RENTAL"),
        ),
        Preset(
            "sim", "SIM / Telecom", "SIM KYC",
            frozenset({AADHAAR_FIRST8, PAN}),
            (_FIRST8, "PAN", "VID", _THUMB),
            ("Photo", "Name", "Address", "Date of birth", "QR (offline e-KYC)"),
            3, 7, ("BANKING", "LOANS", "HOTEL"),
        ),
        Preset(
            "rental", "Rental / Landlord", "RENTAL AGREEMENT",
            frozenset({AADHAAR_FIRST8, QR, PAN, DOB}),
            (_FIRST8, _QR, "PAN", "Date of birth", "VID", _THUMB),
            ("Photo", "Name", "Address"),
            30, 90, ("BANKING", "SIM", "LOANS"),
        ),
        Preset(
            "school", "School Admission", "SCHOOL ADMISSION",
            frozenset({AADHAAR_FIRST8, QR, PAN}),
            (_FIRST8, _QR, "PAN", "VID", _THUMB),
            ("Photo", "Name", "Date of birth", "Address"),
            30, 90, ("BANKING", "SIM", "LOANS"),
        ),
        Preset(
            "bank_loan", "Bank Loan", "LOAN KYC",
            frozenset({AADHAAR_FIRST8}),
            (_FIRST8, "VID", _THUMB),
            ("Photo", "Name", "Date of birth", "Address", "PAN", "QR (offline KYC)"),
            15, 30, ("SIM", "HOTEL", "RENTAL", "OTHER LENDERS"),
        ),
    )
}


def watermark_text(p: Preset, recipient: str, issued: datetime, expires: datetime, armor_id: str
                   ) -> str:
    who = recipient.upper()
    purpose = p.purpose
    first = purpose.split()[0]
    if first in who.replace(",", " ").split():  # "TAJ HOTEL, GOA" + "HOTEL CHECK-IN"
        purpose = purpose[len(first):].strip() or purpose
    return (
        f"FOR {who} {purpose} ONLY · {issued:%d %b %Y} – {expires:%d %b %Y}"
        f" · NOT VALID FOR {', '.join(p.not_valid_for)} · {armor_id}"
    ).upper()


def action_for(p: Preset, finding_type: str) -> str:
    """MASK | MASK_PARTIAL | KEEP for one finding type under a preset."""
    pol = p.policy
    if finding_type in ALWAYS:
        return "MASK"
    if finding_type == "AADHAAR":
        return "MASK" if ALL_NUMBERS in pol else "MASK_PARTIAL"
    if finding_type == "MASKED_AADHAAR":
        return "MASK" if ALL_NUMBERS in pol else "KEEP"
    if finding_type in ("QR", "BARCODE"):
        return "MASK" if QR in pol else "KEEP"
    if finding_type == "PAN":
        return "MASK" if PAN in pol or ALL_NUMBERS in pol else "KEEP"
    if finding_type == "DOB":
        return "MASK" if DOB in pol or ALL_NUMBERS in pol else "KEEP"
    if finding_type == "ADDRESS":
        return "MASK" if ADDRESS in pol else "KEEP"
    if finding_type == "NUMBER":
        return "MASK" if ALL_NUMBERS in pol else "KEEP"
    return "KEEP"  # FACE, NAME, BADGE
