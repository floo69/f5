"""Synthetic Kerala-style sale deeds with ground truth (SYNTHETIC DATA ONLY).

Public API:
    generate_deed(seed, split, mode, n_pages=None) -> (pdf_bytes, gt_dict, page_images)
    make_aadhaar(rng), make_vid(rng), make_bad_checksum_12(rng)

Coordinates follow docs/DATA_CONTRACT.md: points, top-left origin, y down. Internally every
drawing helper takes top-down y and converts to reportlab's bottom-left origin in one place.
Full Aadhaar/VID values are never stored in the ground truth (only masked values).
"""

from __future__ import annotations

import hashlib
import io
import math
import random
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from faker import Faker
from PIL import Image
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from backend.app.core.verhoeff import compute_check_digit
from synth import fingerprint_gen
from synth.styles import sample_fp_style, sample_scan_style

DPI = 200
PT_TO_PX = DPI / 72.0
LEGAL = (612.0, 1008.0)
MARGIN = 40.0
SIZE = 9.5

FONT_DIR = Path(__file__).parent / "fonts"
F_REG, F_BOLD, F_ML = "NotoSansR", "NotoSansB", "NotoSansML"

SRO_NAMES = [
    "SRO Thrissur", "SRO Ernakulam", "SRO Kottayam", "SRO Palakkad", "SRO Kozhikode",
    "SRO Kollam", "SRO Alappuzha", "SRO Kannur", "SRO Thiruvananthapuram", "SRO Manjeri",
    "SRO Kasaragod", "SRO Idukki", "SRO Pathanamthitta", "SRO Kalpetta", "SRO Perinthalmanna",
]  # fmt: skip

MALAYALAM_SENTENCES = [
    "ഈ ആധാരം പ്രകാരം വസ്തുവിന്റെ ഉടമസ്ഥാവകാശം വാങ്ങുന്നയാൾക്ക് കൈമാറിയിരിക്കുന്നു.",
    "മേൽപ്പറഞ്ഞ വസ്തുവിന്റെ വില പൂർണ്ണമായി കൈപ്പറ്റിയിരിക്കുന്നു.",
    "ഈ ആധാരം സബ് രജിസ്ട്രാർ ഓഫീസിൽ രജിസ്റ്റർ ചെയ്തിട്ടുള്ളതാണ്.",
    "വസ്തുവിന് യാതൊരു ബാധ്യതയും ഇല്ലെന്ന് ഞാൻ ഉറപ്പ് നൽകുന്നു.",
    "വസ്തുവിന്റെ അതിരുകൾ താഴെ പറയുന്ന പ്രകാരമാണ്.",
    "കരം തീർത്ത രസീത് ഈ ആധാരത്തോടൊപ്പം ഹാജരാക്കിയിട്ടുണ്ട്.",
]
ML_AADHAAR = "ആധാർ നമ്പർ:"

AADHAAR_LABELS = ["Aadhaar No.:", "Aadhaar No:", "UID:", "Aadhaar Card No.", ML_AADHAAR, None, None]
BAD_LABELS = ["Ref. No.", "Receipt No.", "Token No.", "Challan No.", "Aadhaar No.:", "UID:", None]
PHONE_LABELS = ["Mobile:", "Ph:", "Contact:", None]
FORMATS = ("spaced", "plain", "hyphen")

CLAUSES = [
    "The Vendor declares that the property is free from all encumbrances, attachments and "
    "litigation, and that the Vendor has full right to sell the same.",
    "The Purchaser shall be entitled to get the property mutated in the revenue records and to "
    "remit basic tax in his or her own name from the date of this deed.",
    "Possession of the property has been handed over to the Purchaser on the date of execution "
    "of this deed, and the Purchaser shall hold the same absolutely.",
    "If any defect in title is found, the Vendor shall indemnify the Purchaser against all "
    "losses arising therefrom.",
    "The Vendor has received the entire sale consideration and no amount remains due from the "
    "Purchaser under this deed.",
    "All taxes, cess and dues up to the date of this deed have been paid by the Vendor and the "
    "receipts have been produced before the registering authority.",
]

_FONTS_READY = False
_FAKE: Faker | None = None


def _register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    pdfmetrics.registerFont(TTFont(F_REG, str(FONT_DIR / "NotoSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(F_BOLD, str(FONT_DIR / "NotoSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(F_ML, str(FONT_DIR / "NotoSansMalayalam-Regular.ttf")))
    _FONTS_READY = True


def _faker(seed: int) -> Faker:
    global _FAKE
    if _FAKE is None:
        _FAKE = Faker("en_IN")
    _FAKE.seed_instance(seed)
    return _FAKE


# --------------------------------------------------------------------------- number helpers
def make_aadhaar(rng: random.Random) -> str:
    """12-digit Verhoeff-valid number, first digit 2-9."""
    payload = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    return payload + compute_check_digit(payload)


def make_vid(rng: random.Random) -> str:
    """16-digit Verhoeff-valid virtual ID."""
    payload = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(14))
    return payload + compute_check_digit(payload)


def make_bad_checksum_12(rng: random.Random) -> str:
    """12-digit number, first digit 2-9, with a deliberately WRONG Verhoeff check digit."""
    payload = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    good = compute_check_digit(payload)
    bad = rng.choice([d for d in "0123456789" if d != good])
    return payload + bad


def _fmt(digits: str, style: str) -> str:
    sep = {"spaced": " ", "hyphen": "-", "plain": ""}[style]
    return sep.join(digits[i : i + 4] for i in range(0, len(digits), 4))


def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


# --------------------------------------------------------------------------- builder
class _Deed:
    """Draws one deed with reportlab and collects ground truth (pt, top-left origin)."""

    def __init__(self, seed: int, split: str, n_pages: int):
        _register_fonts()
        self.seed, self.split, self.n_pages = seed, split, n_pages
        self.r = random.Random(seed)
        self.nrng = np.random.default_rng(seed)
        self.fake = _faker(seed)
        self.W, self.H = A4 if self.r.random() < 0.7 else LEGAL
        self.sro = self.r.choice(SRO_NAMES)
        self.year = self.r.randint(2005, 2024)
        self.doc_no = f"{self.r.randint(1, 9999)}/{self.year}"
        self.buf = io.BytesIO()
        self.c = rl_canvas.Canvas(self.buf, pagesize=(self.W, self.H), invariant=1)
        self.c.setTitle("Synthetic sale deed")
        self.annotations: list[dict] = []
        self.hard_negatives: list[dict] = []
        self.page = 0
        self.first_aadhaar_done = False

    # ---- low level drawing (top-down y)
    def text(self, x, y, s, font=F_REG, size=SIZE, color=(0.08, 0.08, 0.1)):
        c = self.c
        c.setFillColorRGB(*color)
        c.setFont(font, size)
        c.drawString(x, self.H - y, s)
        return x + pdfmetrics.stringWidth(s, font, size)

    def ctext(self, y, s, font=F_BOLD, size=16):
        w = pdfmetrics.stringWidth(s, font, size)
        self.text((self.W - w) / 2, y, s, font, size)

    def _add_ann(self, typ, subtype, x0, x1, base_y, size, masked):
        self.annotations.append(
            {
                "page": self.page,
                "type": typ,
                "subtype": subtype,
                "bbox_pt": [x0, base_y - 0.76 * size, x1, base_y + 0.12 * size],
                "value_masked": masked,
            }
        )

    def _add_hn(self, typ, x0, y0, x1, y1):
        self.hard_negatives.append(
            {"page": self.page, "type": typ, "bbox_pt": [x0, y0, x1, y1]}
        )

    # ---- number items: list of segments (text, font, ann|None)
    def item(self, kind: str, force_label: bool = False) -> list:
        r = self.r
        segs: list = []
        if kind == "aadhaar":
            d, st = make_aadhaar(r), r.choice(FORMATS)
            label = r.choice(AADHAAR_LABELS[:5]) if force_label else r.choice(AADHAAR_LABELS)
            txt, ann = _fmt(d, st), ("AADHAAR", st, f"XXXX XXXX {d[-4:]}")
        elif kind == "masked":
            d, st = make_aadhaar(r), r.choice(("spaced", "hyphen"))
            label = r.choice(AADHAAR_LABELS)
            sep = " " if st == "spaced" else "-"
            txt = f"XXXX{sep}XXXX{sep}{d[-4:]}"
            ann = ("MASKED_AADHAAR", st, f"XXXX XXXX {d[-4:]}")
        elif kind == "vid":
            d, st = make_vid(r), r.choice(("spaced", "hyphen"))
            label = r.choice(["VID:", "Virtual ID (VID):", "VID No."])
            txt, ann = _fmt(d, st), ("VID", st, f"XXXX XXXX XXXX {d[-4:]}")
        elif kind == "bad":
            d, st = make_bad_checksum_12(r), r.choice(FORMATS)
            label = r.choice(BAD_LABELS)
            txt, ann = _fmt(d, st), ("DECOY_NUMBER", "bad_checksum", None)
        elif kind == "phone":
            d = str(r.randint(6, 9)) + "".join(str(r.randint(0, 9)) for _ in range(9))
            txt = r.choice(
                [
                    f"+91 {d[:5]} {d[5:]}",
                    f"{d[:5]} {d[5:]}",
                    f"0{d}",
                    f"+91-{d[:5]}-{d[5:]}",
                    f"+91{d}",
                ]
            )
            label = r.choice(PHONE_LABELS)
            ann = ("DECOY_NUMBER", "phone", None)
        elif kind == "survey":
            txt = f"Sy. No. {r.randint(1, 999)}/{r.randint(1, 20)}{r.choice('ABCD')}"
            label, ann = None, ("DECOY_NUMBER", "survey", None)
        else:  # date
            dd, mm, yy = r.randint(1, 28), r.randint(1, 12), r.randint(1995, 2024)
            sep = r.choice("/-.")
            txt = f"{dd:02d}{sep}{mm:02d}{sep}{yy}"
            label = r.choice(["Date:", "Dated", "Date of purchase:", None])
            ann = ("DECOY_NUMBER", "date", None)
        if label:
            segs.append((label, F_ML if ord(label[0]) > 0x0D00 else F_REG, None))
        segs.append((txt, F_REG, ann))
        return segs

    @staticmethod
    def _item_width(segs, size) -> float:
        w = 0.0
        for i, (t, f, _a) in enumerate(segs):
            w += pdfmetrics.stringWidth(t, f, size) + (4.0 if i else 0.0)
        return w

    def _draw_item(self, x, y, segs, size):
        for i, (t, f, ann) in enumerate(segs):
            if i:
                x += 4.0
            x1 = self.text(x, y, t, f, size)
            if ann:
                self._add_ann(ann[0], ann[1], x, x1, y, size, ann[2])
            x = x1
        return x

    # ---- block planners: each returns (height, draw(y_top))
    def plan_par(self, text, font=F_REG, size=SIZE, indent=0.0, space=5.0, lead=1.45):
        lines = simpleSplit(text, font, size, self.W - 2 * MARGIN - indent)
        step = size * lead

        def draw(y):
            for i, ln in enumerate(lines):
                self.text(MARGIN + indent, y + size + i * step, ln, font, size)

        return len(lines) * step + space, draw

    def plan_items(self, items, size=SIZE, indent=0.0, space=5.0):
        maxw = self.W - 2 * MARGIN - indent
        lines: list[list] = []
        cur: list = []
        curw = 0.0
        for it in items:
            w = self._item_width(it, size)
            if cur and curw + 16 + w > maxw:
                lines.append(cur)
                cur, curw = [], 0.0
            curw += (16 if cur else 0) + w
            cur.append(it)
        if cur:
            lines.append(cur)
        step = size * 1.5

        def draw(y):
            for i, ln in enumerate(lines):
                x = MARGIN + indent
                for it in ln:
                    x = self._draw_item(x, y + size + i * step, it, size) + 16

        return len(lines) * step + space, draw

    @staticmethod
    def seq(plans):
        total = sum(h for h, _ in plans)

        def draw(y):
            for h, d in plans:
                d(y)
                y += h

        return total, draw

    def plan_heading(self, s):
        return self.plan_par(s, F_BOLD, 10.5, space=4.0)

    def plan_party(self, role, first=False):
        f, r = self.fake, self.r
        rel = r.choice(["S/o", "D/o", "W/o"])
        addr = f.street_address().replace("\n", ", ")
        txt = (
            f"{f.name()}, aged {r.randint(24, 78)} years, {rel} {f.name()}, residing at {addr}, "
            f"{f.city()}, Kerala ({role})."
        )
        kinds = []
        if first and not self.first_aadhaar_done:
            kinds.append("aadhaar")
            self.first_aadhaar_done = True
        pool = ["aadhaar", "masked", "vid", "bad", "phone", "date"]
        weights = [34, 8, 10, 12, 18, 10]
        kinds += r.choices(pool, weights, k=r.randint(1, 3))
        items = [self.item(k) for k in kinds]
        return self.seq([self.plan_par(txt), self.plan_items(items, indent=14.0, space=7.0)])

    @staticmethod
    def _ordinal(n: int) -> str:
        suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suf}"

    def plan_intro(self):
        f, r = self.fake, self.r
        months = ["January", "March", "May", "June", "August", "October", "December"]
        txt = (
            f"THIS DEED OF SALE is executed at {self.sro} on this "
            f"{self._ordinal(r.randint(1, 28))} day of "
            f"{r.choice(months)} {self.year}, in respect of the property described in the "
            f"Schedule hereunder, for a total sale consideration of Rs. "
            f"{_indian(r.randint(8, 250) * 10000)}/- paid by the Purchaser to the Vendor, "
            f"before the Sub Registrar, {f.city()}."
        )
        return self.plan_par(txt)

    def plan_clause(self):
        return self.plan_par(self.r.choice(CLAUSES))

    def plan_malayalam(self):
        k = self.r.randint(1, 3)
        txt = " ".join(self.r.sample(MALAYALAM_SENTENCES, k))
        return self.plan_par(txt, F_ML, SIZE, lead=1.8, space=6.0)

    def plan_malayalam_id(self):
        it = self.item("aadhaar")
        if it[0][0] != ML_AADHAAR:
            it = [(ML_AADHAAR, F_ML, None), it[-1]]
        return self.plan_items([it], space=6.0)

    def plan_schedule(self):
        f, r = self.fake, self.r
        head = self.plan_heading("SCHEDULE OF PROPERTY")
        txt = (
            f"District: {f.city()}; Taluk: {f.city()}; Village: {f.city()}; Extent: "
            f"{r.randint(1, 60)}.{r.randint(0, 99):02d} Ares "
            f"({r.randint(2, 150)}.{r.randint(0, 99):02d}"
            f" Cents). Boundaries: East - public road; West - property of {f.name()}; "
            f"North - property of {f.name()}; South - canal."
        )
        items = [self.item("survey") for _ in range(r.randint(1, 2))]
        if r.random() < 0.5:
            items.append(self.item("date"))
        return self.seq([head, self.plan_par(txt), self.plan_items(items, space=7.0)])

    def plan_ids(self):
        r = self.r
        pool = ["aadhaar", "masked", "vid", "bad", "phone", "survey", "date"]
        weights = [30, 8, 10, 22, 10, 10, 10]
        items = [self.item(k) for k in r.choices(pool, weights, k=r.randint(2, 4))]
        return self.seq([self.plan_heading("IDENTIFICATION PARTICULARS"), self.plan_items(items)])

    def plan_witness(self):
        f = self.fake
        n = self.r.randint(1, 2)
        txt = f"Witness {n}: {f.name()}, {f.city()}, Kerala."
        kinds = self.r.choice([["aadhaar"], ["aadhaar", "phone"], ["bad"], ["masked"], ["vid"]])
        items = [self.item(k) for k in kinds]
        return self.seq([self.plan_par(txt, space=2.0), self.plan_items(items, indent=14.0)])

    def plan_security(self):
        x0, x1 = MARGIN, self.W - MARGIN
        phase = self.r.uniform(0, 6.28)
        amp = self.r.uniform(2.0, 3.2)
        wl = self.r.uniform(18, 30)
        col = self.r.choice([(0.85, 0.3, 0.3), (0.45, 0.45, 0.6), (0.3, 0.6, 0.5)])

        def draw(y):
            c = self.c
            c.saveState()
            c.setStrokeColorRGB(*col)
            c.setLineWidth(0.6)
            xs = np.arange(x0, x1 + 1, 2.0)
            for k in range(4):
                path = c.beginPath()
                ys = y + 6 + k * 2.4 + amp * np.sin(xs / wl * 6.283 + phase + k * 0.7)
                path.moveTo(float(xs[0]), self.H - float(ys[0]))
                for xv, yv in zip(xs[1:], ys[1:], strict=True):
                    path.lineTo(float(xv), self.H - float(yv))
                c.drawPath(path, stroke=1, fill=0)
            c.restoreState()
            self._add_hn("SECURITY_LINES", x0, y + 6 - amp - 0.5, x1, y + 6 + 7.2 + amp + 0.5)

        return 22.0, draw

    # ---- hard negatives drawn at absolute positions
    def draw_signature(self, x, y, w=130.0, h=38.0):
        r, c = self.r, self.c
        n = r.randint(5, 8)
        xs = np.linspace(x + 4, x + w - 4, n)
        pts = [(float(px), y + h * r.uniform(0.2, 0.8)) for px in xs]
        segs = []
        for a, b in zip(pts[:-1], pts[1:], strict=True):
            dx = b[0] - a[0]
            segs.append(
                (
                    a,
                    (a[0] + dx * r.uniform(0.2, 0.9), a[1] + h * r.uniform(-0.8, 0.8)),
                    (b[0] - dx * r.uniform(-0.4, 0.9), b[1] + h * r.uniform(-0.8, 0.8)),
                    b,
                )
            )
        last = pts[-1]
        segs.append(
            (
                last,
                (last[0] - w * 0.3, last[1] + h * 0.3),
                (x + w * 0.2, y + h * 0.9),
                (x + w * 0.8, y + h * 0.85),
            )
        )
        lw = r.uniform(0.9, 1.6)
        col = r.choice([(0.08, 0.12, 0.5), (0.05, 0.05, 0.1), (0.15, 0.2, 0.6)])
        c.saveState()
        c.setStrokeColorRGB(*col)
        c.setLineWidth(lw)
        c.setLineCap(1)
        path = c.beginPath()
        path.moveTo(segs[0][0][0], self.H - segs[0][0][1])
        sx: list[float] = []
        sy: list[float] = []
        for p0, p1, p2, p3 in segs:
            path.curveTo(p1[0], self.H - p1[1], p2[0], self.H - p2[1], p3[0], self.H - p3[1])
            for t in np.linspace(0, 1, 12):
                u = 1 - t
                bw = (u**3, 3 * u * u * t, 3 * u * t * t, t**3)
                sx.append(sum(b * p[0] for b, p in zip(bw, (p0, p1, p2, p3), strict=True)))
                sy.append(sum(b * p[1] for b, p in zip(bw, (p0, p1, p2, p3), strict=True)))
        c.drawPath(path, stroke=1, fill=0)
        c.restoreState()
        pad = lw / 2
        self._add_hn("SIGNATURE", min(sx) - pad, min(sy) - pad, max(sx) + pad, max(sy) + pad)

    def draw_seal(self, cx, cy, rad):
        c, r = self.c, self.r
        col = r.choice([(0.42, 0.15, 0.58), (0.12, 0.2, 0.65), (0.35, 0.12, 0.5)])
        label = (self.sro.upper() + " * REGISTERED * ")
        label = (label * 3)[: r.randint(26, 34)]
        c.saveState()
        c.setStrokeColorRGB(*col)
        c.setFillColorRGB(*col)
        c.setStrokeAlpha(0.6)
        c.setFillAlpha(0.6)
        c.setLineWidth(1.4)
        c.circle(cx, self.H - cy, rad, stroke=1, fill=0)
        c.setLineWidth(0.7)
        c.circle(cx, self.H - cy, rad - 3.5, stroke=1, fill=0)
        c.circle(cx, self.H - cy, rad * 0.55, stroke=1, fill=0)
        n = len(label)
        c.setFont(F_BOLD, 6.2)
        for i, ch in enumerate(label):
            ang = 90 - i * 360.0 / n
            c.saveState()
            c.translate(cx, self.H - cy)
            c.rotate(ang - 90)
            c.drawCentredString(0, rad - 10.5, ch)
            c.restoreState()
        c.setFont(F_BOLD, 7)
        c.drawCentredString(cx, self.H - cy + 1, "REGD")
        c.drawCentredString(cx, self.H - cy - 8, str(self.year))
        c.restoreState()
        self._add_hn("SEAL", cx - rad, cy - rad, cx + rad, cy + rad)

    def draw_qr(self, x, y, size=66.0):
        w = QrCodeWidget(f"SYNTHETIC-SAMPLE/{self.doc_no}/{self.r.randint(0, 10**6)}")
        x0, y0, x1, y1 = w.getBounds()
        d = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
        d.add(w)
        renderPDF.draw(d, self.c, x, self.H - y - size)
        self._add_hn("QR", x, y, x + size, y + size)

    def draw_photo(self, x, y, w=58.0, h=72.0):
        c, r = self.c, self.r
        bg = r.choice([(0.72, 0.72, 0.74), (0.85, 0.8, 0.7), (0.65, 0.7, 0.75)])
        fg = tuple(v * 0.62 for v in bg)
        c.saveState()
        p = c.beginPath()
        p.rect(x, self.H - y - h, w, h)
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColorRGB(*bg)
        c.rect(x, self.H - y - h, w, h, stroke=0, fill=1)
        c.setFillColorRGB(*fg)
        c.ellipse(x + w * 0.3, self.H - (y + h * 0.58), x + w * 0.7, self.H - (y + h * 0.2),
                  stroke=0, fill=1)  # fmt: skip
        c.ellipse(x - w * 0.1, self.H - (y + h * 1.35), x + w * 1.1, self.H - (y + h * 0.65),
                  stroke=0, fill=1)  # fmt: skip
        c.restoreState()
        c.setStrokeColorRGB(0.4, 0.4, 0.4)
        c.setLineWidth(0.5)
        c.rect(x, self.H - y - h, w, h, stroke=1, fill=0)
        self._add_hn("PHOTO", x, y, x + w, y + h)

    def draw_guilloche(self):
        c, r, W, H = self.c, self.r, self.W, self.H
        tint = r.choice([(0.78, 0.9, 0.8), (0.93, 0.8, 0.84), (0.8, 0.85, 0.95), (0.95, 0.9, 0.75)])
        c.saveState()
        c.setStrokeColorRGB(*tint)
        c.setLineWidth(0.4)
        xs = np.arange(0, W + 3, 3.0)
        nl = 46
        a1, a2 = r.uniform(4, 9), r.uniform(2, 5)
        f1, f2 = r.uniform(0.02, 0.04), r.uniform(0.07, 0.11)
        for i in range(nl):
            ph = i * 0.18
            ys = (i + 0.5) * H / nl + a1 * np.sin(xs * f1 + ph) + a2 * np.sin(xs * f2 - ph * 2)
            path = c.beginPath()
            path.moveTo(0, H - float(ys[0]))
            for xv, yv in zip(xs[1:], ys[1:], strict=True):
                path.lineTo(float(xv), H - float(yv))
            c.drawPath(path, stroke=1, fill=0)
        # central rosette (hypotrochoid family)
        t = np.linspace(0, 2 * np.pi * 10, 1400)
        for k in range(4):
            R, rr, dd = 100.0 - k * 12, 37.0 + k * 3, 55.0 - k * 4
            px = (R - rr) * np.cos(t) + dd * np.cos((R - rr) / rr * t)
            py = (R - rr) * np.sin(t) - dd * np.sin((R - rr) / rr * t)
            path = c.beginPath()
            path.moveTo(W / 2 + float(px[0]), H / 2 + float(py[0]))
            for xv, yv in zip(px[1:], py[1:], strict=True):
                path.lineTo(W / 2 + float(xv), H / 2 + float(yv))
            c.drawPath(path, stroke=1, fill=0)
        c.setStrokeColorRGB(*[v * 0.85 for v in tint])
        c.setLineWidth(1.2)
        c.rect(14, 14, W - 28, H - 28, stroke=1, fill=0)
        c.restoreState()
        self._add_hn("GUILLOCHE", 0.0, 0.0, W, H)

    def draw_watermark(self):
        c, W, H = self.c, self.W, self.H
        s = "SYNTHETIC SAMPLE – NOT A REAL DOCUMENT"
        target = 0.72 * math.hypot(W, H)
        size = target / pdfmetrics.stringWidth(s, F_BOLD, 1.0)
        c.saveState()
        c.setFillColorRGB(*self._wm_color)
        c.setFillAlpha(0.17)
        c.translate(W / 2, H / 2)
        c.rotate(math.degrees(math.atan2(H, W)) * 0.85)
        c.setFont(F_BOLD, size)
        c.drawCentredString(0, -size * 0.35, s)
        c.restoreState()

    # ---- page assembly
    def build(self) -> None:
        self._wm_color = self.r.choice([(0.8, 0.1, 0.1), (0.45, 0.45, 0.5)])
        for pg in range(self.n_pages):
            self.page = pg
            self._build_page(pg)
            self.draw_watermark()
            self.c.showPage()
        self.c.save()

    def _build_page(self, pg: int) -> None:
        r, c, W, H = self.r, self.c, self.W, self.H
        if r.random() < (0.55 if pg == 0 else 0.12):
            self.draw_guilloche()

        # ---- bottom zones, stacked from the bottom up
        n_fp = r.choices([0, 1, 2, 3, 4], [18, 30, 25, 17, 10])[0]
        n_boxes = min(4, n_fp + (1 if r.random() < 0.25 else 0))
        box_w, box_h = 116.0, 108.0
        thumb_top = H - 38 - 20 - box_h
        zone_top = thumb_top if n_boxes else H - 40
        n_sig = r.choices([0, 1, 2, 3], [25, 30, 30, 15])[0]
        sig_top = zone_top - 14 - 52
        if n_sig:
            zone_top = sig_top
        hn_items = [k for k, p in (("seal", 0.4), ("qr", 0.3), ("photo", 0.25)) if r.random() < p]
        hn_top = zone_top - 8 - 80
        if hn_items:
            zone_top = hn_top
        y_limit = zone_top - 6

        # ---- header
        y = MARGIN
        if pg == 0:
            self.ctext(y + 14, "SALE DEED (SYNTHETIC SAMPLE)", F_BOLD, 16)
            y += 30
            self.ctext(y + 8, f"Sub Registry Office: {self.sro}", F_REG, 10)
            y += 16
            self.ctext(y + 8, f"Document No. {self.doc_no}     Book I", F_REG, 10)
            y += 22
        else:
            self.text(MARGIN, y + 8, f"SALE DEED (SYNTHETIC SAMPLE) - Doc. No. {self.doc_no} - "
                      "continued", F_REG, 8, (0.35, 0.35, 0.35))  # fmt: skip
            y += 24

        # ---- body
        forced: list = []
        if pg == 0:
            forced = [
                self.plan_intro(),
                self.plan_heading("VENDOR / EXECUTANT"),
                self.plan_party("Vendor", first=True),
                self.plan_heading("PURCHASER / CLAIMANT"),
                self.plan_party("Purchaser"),
            ]
            if r.random() < 0.5:
                forced.insert(0, self.plan_security())
        sec_used = pg == 0 and any(h == 22.0 for h, _ in forced)
        for h, d in forced:
            if y + h <= y_limit:
                d(y)
                y += h
        misses = 0
        kinds = ["clause", "ml", "mlid", "schedule", "ids", "witness", "party", "security"]
        weights = [24, 16, 6, 14, 16, 10, 8, 4]
        while misses < 8:
            k = r.choices(kinds, weights)[0]
            if k == "security":
                if sec_used:
                    continue
                plan = self.plan_security()
            elif k == "party":
                plan = self.seq(
                    [self.plan_heading(r.choice(["CONFIRMING PARTY", "GUARANTOR"])),
                     self.plan_party("Party")]
                )  # fmt: skip
            else:
                plan = {
                    "clause": self.plan_clause, "ml": self.plan_malayalam,
                    "mlid": self.plan_malayalam_id, "schedule": self.plan_schedule,
                    "ids": self.plan_ids, "witness": self.plan_witness,
                }[k]()  # fmt: skip
            h, d = plan
            if y + h <= y_limit:
                d(y)
                y += h
                sec_used = sec_used or k == "security"
            else:
                misses += 1

        # ---- hard-negative row
        if hn_items:
            slots = r.sample(range(4), len(hn_items))
            for k, s in zip(hn_items, slots, strict=True):
                cx = MARGIN + 60 + s * ((W - 2 * MARGIN - 120) / 3)
                if k == "seal":
                    self.draw_seal(cx, hn_top + 40, 34.0)
                elif k == "qr":
                    self.draw_qr(cx - 33, hn_top + 7)
                else:
                    self.draw_photo(cx - 29, hn_top + 4)
                    self.text(cx - 20, hn_top + 80, "Photograph", F_REG, 6.5, (0.4, 0.4, 0.4))

        # ---- signatures
        for i in range(n_sig):
            x = MARGIN + i * 175
            self.draw_signature(x, sig_top + 2)
            c.setStrokeColorRGB(0.3, 0.3, 0.3)
            c.setLineWidth(0.5)
            c.line(x, H - (sig_top + 46), x + 140, H - (sig_top + 46))
            cap = r.choice(["Signature of Executant", "Signature of Witness", "Signature of Claimant"])  # noqa: E501
            self.text(x, sig_top + 53, cap, F_REG, 6.5)

        # ---- thumb boxes
        if n_boxes:
            gap = 10.0
            total = n_boxes * box_w + (n_boxes - 1) * gap
            x_start = MARGIN if r.random() < 0.6 else W - MARGIN - total
            captions = [
                "Left thumb impression of executant", "LTI", "Left thumb impression of claimant",
                "Left thumb impression of witness", "LTI of vendor", "Right thumb impression",
            ]  # fmt: skip
            for i in range(n_boxes):
                bx = x_start + i * (box_w + gap)
                c.setStrokeColorRGB(0.2, 0.2, 0.2)
                c.setLineWidth(0.7)
                c.rect(bx, H - (thumb_top + box_h), box_w, box_h, stroke=1, fill=0)
                for j, ln in enumerate(simpleSplit(r.choice(captions), F_REG, 6.5, box_w - 4)):
                    self.text(bx + 2, thumb_top + box_h + 8 + j * 8, ln, F_REG, 6.5)
                if i < n_fp:
                    self._draw_print(bx, thumb_top, box_w, box_h)

        # ---- footer
        self.text(MARGIN, H - 22, f"{self.sro} | Doc. No. {self.doc_no} | Page {pg + 1} of "
                  f"{self.n_pages}", F_REG, 7, (0.4, 0.4, 0.4))  # fmt: skip

    def _draw_print(self, bx, by, bw, bh):
        seed_i = int(self.nrng.integers(0, 2**31 - 1))
        style = sample_fp_style(self.nrng, self.split)
        arr = fingerprint_gen.generate(seed_i, style)
        h_px, w_px = arr.shape[:2]
        w, h = w_px * 72.0 / DPI, h_px * 72.0 / DPI
        s = min(1.0, (bw - 6) / w, (bh - 6) / h)
        w, h = w * s, h * s
        x = bx + (bw - w) / 2 + self.r.uniform(-1, 1) * max(0.0, (bw - 6 - w) / 2)
        y = by + (bh - h) / 2 + self.r.uniform(-1, 1) * max(0.0, (bh - 6 - h) / 2)
        img = Image.fromarray(np.ascontiguousarray(arr), "RGBA")
        self.c.drawImage(ImageReader(img), x, self.H - (y + h), w, h, mask="auto")
        self.annotations.append(
            {
                "page": self.page,
                "type": "FINGERPRINT",
                "subtype": None,
                "bbox_pt": [x, y, x + w, y + h],
                "value_masked": None,
            }
        )


# --------------------------------------------------------------------------- rendering / scan
def _render_pages(pdf: bytes) -> list[np.ndarray]:
    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=DPI, alpha=False)
            out.append(
                np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()
            )
    return out


def _degrade(img: np.ndarray, st: dict, rng: np.random.Generator):
    """Skew/blur/noise/yellow/JPEG. Returns (jpeg_bytes, decoded_rgb, affine_2x3)."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), st["skew_deg"], 1.0)
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    if st["blur_sigma"] > 0.05:
        out = cv2.GaussianBlur(out, (0, 0), st["blur_sigma"])
    y = st["yellowing"]
    tint = np.array([1.0, 1.0 - 0.10 * y, 1.0 - 0.38 * y], np.float32)
    f = out.astype(np.float32) * tint
    f += rng.standard_normal((h, w, 1), dtype=np.float32) * st["noise_std"]
    out = np.clip(f, 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(
        ".jpg", cv2.cvtColor(out, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, st["jpeg_quality"]]
    )
    assert ok
    jpeg = enc.tobytes()
    dec = cv2.cvtColor(cv2.imdecode(enc, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    return jpeg, dec, m


def _transform_box(box_pt, m, W, H):
    """Rotate the 4 corners with the px-space affine, take AABB, clip to page (pt)."""
    x0, y0, x1, y1 = (v * PT_TO_PX for v in box_pt)
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], np.float64) @ m.T
    nx0, ny0 = pts.min(axis=0) / PT_TO_PX
    nx1, ny1 = pts.max(axis=0) / PT_TO_PX
    return [
        min(max(nx0, 0.0), W), min(max(ny0, 0.0), H),
        min(max(nx1, 0.0), W), min(max(ny1, 0.0), H),
    ]  # fmt: skip


def _finish(entry: dict) -> dict:
    pt = [round(float(v), 2) for v in entry["bbox_pt"]]
    entry["bbox_pt"] = pt
    entry["bbox_px"] = [int(round(v * PT_TO_PX)) for v in pt]
    return entry


def _fix_pdf_id(pdf: bytes) -> bytes:
    """pymupdf writes a random trailer /ID; replace it (same length) by a content hash."""
    tag = b"/ID[<"
    i = pdf.rfind(tag)
    if i < 0:
        return pdf
    j = pdf.index(b"]", i)
    digest = hashlib.md5(pdf[:i]).hexdigest().upper().encode()
    return pdf[:i] + b"/ID[<" + digest + b"><" + digest + b">" + pdf[j:]


def generate_deed(
    seed: int, split: str, mode: str, n_pages: int | None = None, doc_id: str | None = None
) -> tuple[bytes, dict, list[np.ndarray]]:
    """Build one synthetic deed. Returns (pdf_bytes, ground_truth, 200-dpi RGB page images)."""
    if mode not in ("born_digital", "scanned"):
        raise ValueError(mode)
    if n_pages is None:
        n_pages = random.Random(seed ^ 0x5EED).choices([1, 2, 3, 4], [30, 30, 25, 15])[0]
    deed = _Deed(seed, split, n_pages)
    deed.build()
    W, H = deed.W, deed.H
    pdf = deed.buf.getvalue()
    anns, hns = deed.annotations, deed.hard_negatives
    images = _render_pages(pdf)

    if mode == "scanned":
        srng = np.random.default_rng([seed, 17])
        pages_out = pymupdf.open()
        new_images = []
        keep_a, keep_h = [], []
        for pg, img in enumerate(images):
            st = sample_scan_style(srng, split)
            jpeg, dec, m = _degrade(img, st, srng)
            new_images.append(dec)
            page = pages_out.new_page(width=W, height=H)
            page.insert_image(page.rect, stream=jpeg)
            for src, dst in ((anns, keep_a), (hns, keep_h)):
                for e in (e for e in src if e["page"] == pg):
                    e["bbox_pt"] = _transform_box(e["bbox_pt"], m, W, H)
                    b = e["bbox_pt"]
                    if b[2] - b[0] > 0.5 and b[3] - b[1] > 0.5:
                        dst.append(e)
        anns = sorted(keep_a, key=lambda e: e["page"])
        hns = sorted(keep_h, key=lambda e: e["page"])
        images = new_images
        pages_out.set_metadata(
            {k: "" for k in ("title", "author", "subject", "keywords", "creator", "producer",
                             "creationDate", "modDate")}  # fmt: skip
        )
        pdf = _fix_pdf_id(pages_out.tobytes(garbage=4, deflate=True))
        pages_out.close()

    gt = {
        "doc_id": doc_id or f"{split}_{seed}",
        "split": split,
        "seed": seed,
        "mode": mode,
        "dpi_px": DPI,
        "pages": [{"index": i, "size_pt": [round(W, 2), round(H, 2)]} for i in range(n_pages)],
        "annotations": [_finish(e) for e in anns],
        "hard_negatives": [_finish(e) for e in hns],
    }
    return pdf, gt, images
