"""Preimplementation adversarial acceptance probe for WIT-RFC8785-NUM-001."""

from witness_public.service import _canonical_number


CASES = [
    (-0.0, "0"),
    (1.0, "1"),
    (1e-7, "1e-7"),
    (1e-6, "0.000001"),
    (1e20, "100000000000000000000"),
    (1e21, "1e+21"),
    (2e-3, "0.002"),
    (333333333.33333329, "333333333.3333333"),
]


def test_ecmascript_numeric_thresholds() -> None:
    observed = [(value, _canonical_number(value)) for value, _ in CASES]
    expected = [(value, canonical) for value, canonical in CASES]
    assert observed == expected