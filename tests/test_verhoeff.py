import random

import pytest

from backend.app.core.verhoeff import compute_check_digit, validate

# Reference vectors from the Verhoeff algorithm article: 236 -> 3, 12345 -> 1.
KNOWN_GOOD = ["2363", "123451"]
KNOWN_BAD = ["2364", "2362", "123456", "123415", "", "12a4"]


@pytest.mark.parametrize("n", KNOWN_GOOD)
def test_known_good(n):
    assert validate(n)


@pytest.mark.parametrize("n", KNOWN_BAD)
def test_known_bad(n):
    assert not validate(n)


def test_compute_check_digit_vectors():
    assert compute_check_digit("236") == "3"
    assert compute_check_digit("12345") == "1"


def _random_number(rng: random.Random, length: int) -> str:
    payload = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(length - 2))
    return payload + compute_check_digit(payload)


@pytest.mark.parametrize("length", [12, 16])
def test_generated_validate_and_single_digit_mutations_fail(length):
    rng = random.Random(1234 + length)
    for _ in range(300):
        n = _random_number(rng, length)
        assert validate(n)
        for pos in range(length):
            for d in "0123456789":
                if d != n[pos]:
                    assert not validate(n[:pos] + d + n[pos + 1 :])


def test_synth_aadhaar_numbers_validate():
    from synth.deed_gen import make_aadhaar, make_bad_checksum_12, make_vid

    rng = random.Random(99)
    for _ in range(200):
        a = make_aadhaar(rng)
        assert len(a) == 12 and a[0] in "23456789" and validate(a)
        v = make_vid(rng)
        assert len(v) == 16 and validate(v)
        d = make_bad_checksum_12(rng)
        assert len(d) == 12 and d[0] in "23456789" and not validate(d)
