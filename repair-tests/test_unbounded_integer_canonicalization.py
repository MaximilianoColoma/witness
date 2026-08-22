"""Preimplementation adversarial acceptance for WIT-CANONICAL-UNBOUNDED-INT-001."""

from witness_public.service import _canonical, _canonical_number


def test_adjacent_unbounded_integers_keep_distinct_exact_identities() -> None:
    lower = 2**53
    upper = lower + 1

    assert _canonical_number(lower) == "9007199254740992"
    assert _canonical_number(upper) == "9007199254740993"
    assert _canonical({"tokens_total": lower}) != _canonical({"tokens_total": upper})


def test_overflow_scale_integer_canonicalizes_without_float_conversion() -> None:
    value = 10**400

    assert _canonical_number(value) == "1" + ("0" * 400)


def test_integral_float_keeps_ecmascript_double_identity() -> None:
    assert _canonical_number(float(2**53 + 1)) == "9007199254740992"
