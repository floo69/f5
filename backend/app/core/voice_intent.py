"""Deterministic voice-command parser ("Hey Surakshit, armor my Aadhaar for Goa Taj Hotel for
2 days"). Regex + keyword tables, no LLM, no network: well under a millisecond.

Only the transcript text arrives here (speech is recognised in the browser); it is parsed in
memory and never logged or stored.
"""

from __future__ import annotations

import re
import time

from .presets import PRESETS

_WAKE = re.compile(r"^\s*(?:hey|hi|ok|okay)?\s*(?:surakshit|suraksheet|surakshith)\b[\s,.!]*", re.I)
_NUM = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "thirty": 30}
_DUR = re.compile(r"\b(?:for|valid(?: for)?|till|upto|up to)?\s*(\d{1,3}|"
                  + "|".join(_NUM) + r")\s*(day|days|night|nights|week|weeks|month|months)\b",
                  re.I)
_TODAY = re.compile(r"\b(?:for\s+)?(today|tonight|one day only)\b", re.I)
# (preset, keywords) — first match in this order wins
_PRESET_KW = [
    ("xerox", r"xerox|photocopy|photo copy|print ?shop|printout|copy shop|cyber ?cafe"),
    ("sim", r"\bsim\b|telecom|mobile connection|new connection|jio|airtel|vodafone|\bvi\b|bsnl"),
    ("bank_loan", r"\bloan\b|bank|nbfc|finance|lender"),
    ("rental", r"rent|rental|landlord|tenant|lease|\bpg\b|paying guest|flat|broker"),
    ("school", r"school|admission|college|university|coaching"),
    ("hotel", r"hotel|check[- ]?in|resort|lodge|homestay|guest ?house|oyo|stay|hostel"),
]
_DOC = [("pan", r"\bpan\b"), ("aadhaar", r"aadhaa?r|adhaa?r|aadhar|uid")]
_FOR = re.compile(r"\b(?:for|at|to|with)\s+(?:the\s+)?(.+)", re.I)
_LEAD = re.compile(r"^(?:armou?r|protect|mask|share|secure|send)\b.*?\b(?:my|the|this)?\s*"
                   r"(?:aadhaa?r|aadhar|pan|id|card|document)?\s*(?:card)?\s*", re.I)
_STRIP_TAIL = re.compile(r"\b(?:only|please|pls|now|check[- ]?in|copy)\b", re.I)


def _days(text: str) -> tuple[int | None, str]:
    m = _DUR.search(text)
    if m:
        n = m.group(1).lower()
        n = int(n) if n.isdigit() else _NUM[n]
        unit = m.group(2).lower()
        mult = 7 if unit.startswith("week") else 30 if unit.startswith("month") else 1
        return n * mult, text[: m.start()] + text[m.end() :]
    m = _TODAY.search(text)
    if m:
        return 1, text[: m.start()] + text[m.end() :]
    return None, text


def parse(text: str) -> dict:
    t0 = time.perf_counter()
    raw = " ".join(text.split())[:300]
    s = _WAKE.sub("", raw)
    low = s.lower()
    doc = next((d for d, rx in _DOC if re.search(rx, low)), "any")
    preset = next((p for p, rx in _PRESET_KW if re.search(rx, low)), None)
    days, rest = _days(s)

    recipient = None
    m = _FOR.search(rest)
    if m:
        cand = m.group(1)
        cand = re.split(r"\b(?:for|valid|till|upto|please)\b", cand, maxsplit=1, flags=re.I)[0]
        at = re.split(r"\bat\b", cand, flags=re.I)
        if len(at) > 1 and len(at[-1].strip()) >= 3:  # "for school admission at DPS Noida"
            cand = at[-1]
        cand = _STRIP_TAIL.sub("", cand)
        cand = re.sub(r"\b(?:my|the)\s+(?:aadhaa?r|pan|id)\b", "", cand, flags=re.I)
        cand = cand.strip(" ,.;:-")
        # a bare purpose word ("for hotel check-in", "for xerox") is not a recipient
        bare = re.fullmatch(r"(?:a\s+)?(?:" + "|".join(rx for _, rx in _PRESET_KW) + r")s?", cand,
                            re.I)
        if len(cand) >= 3 and not bare:
            recipient = " ".join(w if w.isupper() else w[:1].upper() + w[1:]
                                 for w in cand.split())[:60]

    p = PRESETS.get(preset or "")
    if days is None and p is not None:
        days = p.default_days
    missing = [k for k, v in (("purpose", preset), ("recipient", recipient)) if not v]
    if p is not None and days is not None and days > p.max_days:
        missing.append(f"days (max {p.max_days} for {p.label})")
        days = p.max_days
    doc_word = {"pan": "PAN card", "aadhaar": "Aadhaar", "any": "ID"}[doc]
    if not missing:
        blocked = ", ".join(x if x == "SIM" else x.lower() for x in p.not_valid_for)
        conf = (f"Armoring your {doc_word} for {recipient}: {p.label}, valid {days} "
                f"day{'s' if days != 1 else ''}. It will be refused for {blocked}.")
    elif "purpose" in missing:
        conf = "What is this copy for? Say hotel, xerox, SIM, rental, school or bank loan."
    else:
        conf = f"Who receives this {p.label.lower()} copy? Say the name, like Taj Hotel Goa."
    return {
        "ok": not missing, "preset": preset, "recipient": recipient, "valid_days": days,
        "document": doc, "missing": missing, "confirmation": conf,
        "parse_ms": round((time.perf_counter() - t0) * 1000, 3),
    }
