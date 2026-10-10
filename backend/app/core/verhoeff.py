"""Verhoeff checksum, as used by Aadhaar (12 digits) and VID (16 digits)."""

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 8, 3, 6, 2, 7, 1, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 2, 6, 1, 3, 8, 5, 9),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def _checksum(digits: str) -> int:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c


def validate(number: str) -> bool:
    """True if `number` (digits only) carries a valid Verhoeff check digit."""
    return bool(number) and number.isdigit() and _checksum(number) == 0


def compute_check_digit(payload: str) -> str:
    """Check digit to append to `payload` (digits only)."""
    if not payload.isdigit():
        raise ValueError("payload must be digits")
    return str(_INV[_checksum(payload + "0")])
