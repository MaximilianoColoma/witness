"""Adversarial acceptance probe for unconditional potential-PII coverage."""

from __future__ import annotations

import json

from witness_public.service import _SPECS, _parse


def test_unclassified_operational_strings_cross_privacy_scanner() -> None:
    raw_email = "owner@example.com"
    raw_secret = "api_key=abcd1234secret"
    raw_ip = "198.51.100.42"

    parsed = [
        _parse(
            _SPECS["tool_register_project"],
            {
                "name": raw_email,
                "domains": raw_secret,
                "description": "safe",
                "caller_instance_id": raw_ip,
                "request_id": "privacy-project-1",
            },
        ),
        _parse(
            _SPECS["tool_log_record"],
            {
                "project": raw_email,
                "record_type": raw_secret,
                "title": "safe",
                "content": "safe",
                "caller_instance_id": raw_ip,
                "request_id": "privacy-record-1",
                "references": raw_ip,
            },
        ),
        _parse(
            _SPECS["tool_log_outcome"],
            {
                "project": raw_email,
                "task_summary": "safe",
                "result": "success",
                "caller_instance_id": raw_ip,
                "domain": raw_secret,
                "session_id": raw_email,
                "task_id": raw_ip,
                "request_id": "privacy-outcome-1",
            },
        ),
    ]

    rendered = json.dumps(parsed, sort_keys=True)
    assert raw_email not in rendered
    assert raw_secret not in rendered
    assert raw_ip not in rendered
    assert "[REDACTED:EMAIL]" in rendered
    assert "[REDACTED:SECRET]" in rendered
    assert "[REDACTED:IP]" in rendered
    assert "privacy-project-1" in rendered  # full-match request-id pattern stays operational
    assert '"result": "success"' in rendered  # closed enum stays operational


def test_recursive_secret_keys_and_nested_string_leaves_are_redacted():
    from witness_public.privacy import redact
    raw = {
        "nested": [{"password": "tiny", "note": "owner@example.com"}],
        "authorization": "abc",
    }
    rendered = json.dumps(redact(raw), sort_keys=True)
    assert "tiny" not in rendered and "owner@example.com" not in rendered and "abc" not in rendered
    assert rendered.count("[REDACTED:") == 3
