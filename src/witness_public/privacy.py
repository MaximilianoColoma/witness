"""Fail-closed recursive privacy transformations.

Coverage rule (public-contract.json `privacy.coverage_rule`): every persisted or
indexed string, string-list member and string-valued JSON leaf is potential PII
unless the caller classified it as a validated operational identifier or a closed
enum. `redact` therefore walks the whole value recursively and rewrites every
supported PII or credential-secret class to a stable ``[REDACTED:<CLASS>]``
marker before the value can reach SQLite, FTS, audit or logs.
"""

from __future__ import annotations

import re
from typing import Any

# Keys of a key/value credential pair, and the auth scheme words that can precede
# the credential itself ("Authorization: Bearer x", "Bearer x").
_SECRET_KEY = (
    r"(?:api[_-]?keys?|apikeys?|secret[_-]?keys?|secrets?|passwords?|passwd|pwd|"
    r"tokens?|access[_-]?keys?|private[_-]?keys?|credentials?|authorization|auth[_-]?tokens?|"
    r"client[_-]?secrets?|session[_-]?keys?|bearer|basic)"
)
_SCHEME = r"(?:bearer|basic|token)"
_SENSITIVE_KEY = re.compile(
    r"(?i)(?:password|passwd|secret|token|credential|api[_-]?key|authorization|oauth|private[_-]?key|session[_-]?id)"
)


def _luhn(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _credit_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[REDACTED:CREDIT_CARD]" if 13 <= len(digits) <= 19 and _luhn(digits) else match.group(0)


# Ordered: structural/secret classes first so a secret is never re-classified as a
# weaker class (e.g. an email inside a "password: ..." pair stays a SECRET).
_RULES: tuple[tuple[re.Pattern[str], Any], ...] = (
    (re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED:PRIVATE_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}"), "[REDACTED:JWT]"),
    (re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@"), "[REDACTED:URL_CREDENTIALS]"),
    # key=value / key: value, optionally with an auth scheme word in front of the value.
    (re.compile(rf"(?i)\b{_SECRET_KEY}\b\s*[:=]\s*[\"']?(?:{_SCHEME}\s+)?[^\s\"',;]{{4,}}[\"']?"), "[REDACTED:SECRET]"),
    # bare "Bearer <credential>" / "Basic <credential>" headers.
    (re.compile(rf"(?i)\b{_SCHEME}\s+[\"']?[A-Za-z0-9._~+/=-]{{8,}}[\"']?"), "[REDACTED:SECRET]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:SECRET]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "[REDACTED:SECRET]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"), "[REDACTED:SECRET]"),
    (re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj|ant)?[-_]?[A-Za-z0-9]{8,}[A-Za-z0-9_-]*\b"), "[REDACTED:SECRET]"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "[REDACTED:SECRET]"),
    (re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"), "[REDACTED:EMAIL]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[REDACTED:IBAN]"),
    (re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"), "[REDACTED:SSN]"),
    (re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"), _credit_card),
    (re.compile(r"\+\d[\d ().-]{6,}\d\b"), "[REDACTED:PHONE]"),
    (re.compile(r"(?<![\w-])\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?![\d-])"), "[REDACTED:PHONE]"),
    (re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"), "[REDACTED:IP]"),
)


def _redact_text(value: str) -> str:
    value.encode("utf-8", "strict")
    for pattern, replacement in _RULES:
        value = pattern.sub(replacement, value)
    return value


def redact(value: Any) -> Any:
    """Recursively redact every string leaf before it crosses a storage boundary."""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {
            key: "[REDACTED:SECRET]"
            if isinstance(key, str) and _SENSITIVE_KEY.search(key)
            else redact(item)
            for key, item in value.items()
        }
    return value
