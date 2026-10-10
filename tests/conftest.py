"""Shared fixtures. Tests never read data/datasets/ (gitignored); they generate small deeds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from synth.deed_gen import generate_deed


@dataclass
class Deed:
    path: Path
    pdf: bytes
    gt: dict

    def gt_of(self, *types: str) -> list[dict]:
        return [a for a in self.gt["annotations"] if a["type"] in types]


def _make(tmp_dir: Path, seed: int, mode: str, n_pages: int, split: str = "val") -> Deed:
    pdf, gt, _ = generate_deed(seed, split, mode, n_pages=n_pages)
    path = tmp_dir / f"{split}_{mode}_{seed}.pdf"
    path.write_bytes(pdf)
    return Deed(path, pdf, gt)


def _first_with_prints(tmp_dir: Path, mode: str, n_pages: int) -> Deed:
    for seed in range(11, 60):
        d = _make(tmp_dir, seed, mode, n_pages)
        if d.gt_of("FINGERPRINT") and d.gt_of("AADHAAR"):
            return d
    raise RuntimeError("no suitable synthetic deed found")


@pytest.fixture(scope="session")
def born_digital_deed(tmp_path_factory) -> Deed:
    """2-page born-digital deed with at least one thumbprint and one Aadhaar number."""
    return _first_with_prints(tmp_path_factory.mktemp("bd"), "born_digital", 2)


@pytest.fixture(scope="session")
def scanned_deed(tmp_path_factory) -> Deed:
    """1-page scanned (image-only) deed with at least one thumbprint and one Aadhaar number."""
    return _first_with_prints(tmp_path_factory.mktemp("sc"), "scanned", 1)
