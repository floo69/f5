"""Aadhaar / VID detection on page text: strict group shapes + Verhoeff, never a sliding window.

Full numbers are never logged, stored or returned; findings carry only a masked value.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import verhoeff
from .ocr import normalize_token
from .types import BBox, Finding, PageText, Word

_AADHAAR_KW = ("aadhaar", "aadhar", "uid", "ആധാർ")
_VID_KW = ("vid", "virtual id")
_CONTEXT_CHARS = 40
_MASK_CHARS = set("Xx×*")


@dataclass
class _Atom:
    kind: str  # "D" digits, "M" mask (XXXX), "T" other text
    val: str  # digits for "D"
    word: Word
    start: int  # char offset of the word in its line string


def _atoms(words: list[Word]) -> tuple[list[_Atom], str]:
    """Split a line's words (reading order) into atoms; hyphens separate atoms."""
    atoms: list[_Atom] = []
    pos = 0
    line = ""
    for w in words:
        start = pos
        line += w.text + " "
        pos = len(line)
        raw = w.text
        plus = raw.startswith("+")  # phone numbers: "+91..." never starts a number
        for part in raw.split("-") if "-" in raw[1:] else [raw]:
            t = normalize_token(part)
            if not t:
                continue
            if plus:
                kind, val = "T", t
                plus = False
            elif t.isdigit():
                kind, val = "D", t
            elif 3 <= len(t) <= 4 and sum(c in _MASK_CHARS for c in t) >= 3:
                kind, val = "M", t
            else:
                kind, val = "T", t
            atoms.append(_Atom(kind, val, w, start))
    return atoms, line


def _is_d4(a: _Atom) -> bool:
    return a.kind == "D" and len(a.val) == 4


def _union(atoms: list[_Atom]) -> BBox:
    bs = [a.word.bbox_pt for a in atoms]
    x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
    return (x0, y0, max(b[2] for b in bs), max(b[3] for b in bs))


def _near(text: str, kws: tuple[str, ...]) -> bool:
    tail = text[-_CONTEXT_CHARS:].lower()
    return any(k in tail for k in kws)


def _runs(atoms: list[_Atom], kind: str):
    """Yield (i, j) index ranges of maximal consecutive atoms of `kind`."""
    i = 0
    while i < len(atoms):
        if atoms[i].kind != kind:
            i += 1
            continue
        j = i
        while j < len(atoms) and atoms[j].kind == kind:
            j += 1
        yield i, j
        i = j


def find_numbers(pt: PageText, page: int) -> list[Finding]:
    """Aadhaar (12 digits), VID (16) and already-masked Aadhaar numbers on one page."""
    source = "textlayer" if pt.text_layer else "ocr"
    by_line: dict[int, list[Word]] = {}
    for w in pt.words:
        by_line.setdefault(w.line_id, []).append(w)
    lines = []
    for ws in by_line.values():
        ws.sort(key=lambda w: w.bbox_pt[0])
        lines.append((sum((w.bbox_pt[1] + w.bbox_pt[3]) / 2 for w in ws) / len(ws), ws))
    lines.sort(key=lambda t: t[0])

    out: list[Finding] = []
    prev_text = ""
    for _, ws in lines:
        atoms, line = _atoms(ws)
        for i, j in _runs(atoms, "D"):
            run = atoms[i:j]
            lens = [len(a.val) for a in run]
            digits = "".join(a.val for a in run)
            total = sum(lens)
            # canonical shapes, or OCR-fragmented groups (e.g. 8+4, 4+4+2+2) that still total
            # 12/16 digits; Verhoeff guards the looser ones. Runs with a 5-7 or 9+ digit atom
            # (phones, long digit runs) never qualify.
            loose = len(run) <= 6 and all(n in (1, 2, 3, 4, 6, 8) for n in lens)
            if total == 12 and (lens in ([12], [4, 4, 4]) or loose):
                ok = digits[0] in "23456789" and verhoeff.validate(digits)
                kind, kws = "AADHAAR", _AADHAAR_KW
            elif total == 16 and (lens in ([16], [4, 4, 4, 4]) or loose):
                kind, ok, kws = "VID", verhoeff.validate(digits), _VID_KW
            else:
                continue
            if not ok:
                continue
            before = line[: run[0].start]
            near = _near(before, kws) or (not before.strip() and _near(prev_text, kws))
            masked = ("XXXX XXXX XXXX " if kind == "VID" else "XXXX XXXX ") + digits[-4:]
            out.append(
                Finding(
                    type=kind,
                    page=page,
                    bbox_pt=_union(run),
                    confidence=min(1.0, 0.9 + (0.1 if near else 0.0)),
                    source=source,
                    value_masked=masked,
                    redact=True,
                )
            )
        # already-masked: 2-3 mask groups then 4 digits
        for k in range(len(atoms) - 2):
            if atoms[k].kind != "M" or (k > 0 and atoms[k - 1].kind == "M"):
                continue
            m = k
            while m < len(atoms) and atoms[m].kind == "M":
                m += 1
            if m - k in (2, 3) and m < len(atoms) and _is_d4(atoms[m]):
                grp = atoms[k : m + 1]
                out.append(
                    Finding(
                        type="MASKED_AADHAAR",
                        page=page,
                        bbox_pt=_union(grp),
                        confidence=0.9,
                        source=source,
                        value_masked=("XXXX " * (m - k)) + atoms[m].val,
                        redact=False,
                    )
                )
        prev_text = line
    return out
