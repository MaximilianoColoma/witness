"""Adversarial acceptance probes for credential-authority isolation."""

from __future__ import annotations

from contextvars import Context
import asyncio
from datetime import datetime, timedelta, timezone
import os

import pytest

from witness_public.auth import (
    Principal,
    bind_transport_credential,
    current_transport_credential,
    resolve_principal,
)


class Provider:
    issuer = "repair-test-issuer"
    audience = "witness"

    def __init__(self, credential_type: str) -> None:
        now = datetime.now(timezone.utc)
        self.principal = Principal(
            subject_id="repair-actor",
            client_id="repair-client",
            role="admin",
            credential_type=credential_type,
            credential_id="repair-credential",
            issuer=self.issuer,
            audience=self.audience,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            revocation_status="active",
        )

    def resolve(self, raw_credential: str):
        return self.principal if raw_credential in {"opaque-repair-token", "opaque-repair-token-2"} else None


def test_registry_fallback_cannot_authorize_non_synthetic_principal() -> None:
    """A compatibility binding is not an OAuth/API-key authority channel."""
    for credential_type in ("oauth_bearer", "api_key_provider"):
        provider = Provider(credential_type)
        with bind_transport_credential("opaque-repair-token"):
            # A fresh context models the FastMCP session task that did not inherit
            # the caller's request-local credential and can see only fallback state.
            with pytest.raises(ValueError, match="authentication"):
                Context().run(resolve_principal, provider)


def test_registry_fallback_remains_explicitly_synthetic_only() -> None:
    provider = Provider("synthetic_test_provider")
    with bind_transport_credential("opaque-repair-token"):
        principal = Context().run(resolve_principal, provider)
    assert principal.credential_type == "synthetic_test_provider"


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork unavailable")
def test_registry_binding_is_cleared_in_forked_child() -> None:
    read_fd, write_fd = os.pipe()
    with bind_transport_credential("opaque-repair-token"):
        pid = os.fork()
        if pid == 0:  # pragma: no cover - assertion is performed by parent
            try:
                os.close(read_fd)
                inherited = Context().run(current_transport_credential)
                os.write(write_fd, b"NONE" if inherited is None else b"INHERITED")
            finally:
                os._exit(0)
        os.close(write_fd)
        observed = os.read(read_fd, 32)
        _, status = os.waitpid(pid, 0)
    os.close(read_fd)
    assert os.waitstatus_to_exitcode(status) == 0
    assert observed == b"NONE"


@pytest.mark.anyio
async def test_two_concurrent_registry_credentials_fail_closed_without_substitution() -> None:
    first = Provider("synthetic_test_provider")
    second = Provider("synthetic_test_provider")
    first.principal = Principal(**{**first.principal.__dict__, "subject_id": "actor-first"})
    second.principal = Principal(**{**second.principal.__dict__, "subject_id": "actor-second"})
    entered = asyncio.Event()
    release = asyncio.Event()
    resolved: asyncio.Queue[None] = asyncio.Queue()
    exit_contexts = asyncio.Event()
    outcomes: list[str] = []

    async def bound(provider: Provider, token: str) -> None:
        with bind_transport_credential(token):
            entered.set()
            await release.wait()
            try:
                outcomes.append(Context().run(resolve_principal, provider).subject_id)
            except ValueError:
                outcomes.append("DENY")
            await resolved.put(None)
            await exit_contexts.wait()

    one = asyncio.create_task(bound(first, "opaque-repair-token"))
    await entered.wait()
    entered.clear()
    two = asyncio.create_task(bound(second, "opaque-repair-token-2"))
    await entered.wait()
    release.set()
    await resolved.get()
    await resolved.get()
    exit_contexts.set()
    await asyncio.gather(one, two)
    assert outcomes == ["DENY", "DENY"]
