"""Authentication boundary for the Witness public core.

The raw transport credential travels in a :class:`~contextvars.ContextVar`, so a
credential bound around one request is visible only to the code running inside
that request's context: concurrent requests are isolated by construction and no
process-global slot is ever read or written by a request.

The in-memory FastMCP adapter is the one transport that cannot carry the context
across the call: its server session task snapshots its context when the session
is opened, which is before a per-call credential is bound. For that adapter only,
a *thread-local registry of currently active bindings* is consulted. The registry
never overwrites or clears another actor's binding (entries are keyed by binding
identity and removed by that identity), and it resolves a credential only when
exactly one distinct credential is active in this thread. Two concurrently bound
actors are indeterminate, and indeterminate fails closed with
AUTHENTICATION_REQUIRED rather than attributing one actor's request to another
(public-contract.json identity_authority: "Missing, malformed, conflicting or
provider-indeterminate claims deny before dispatch").
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
import os
from threading import Lock, get_ident
from typing import Any, Iterator
import unicodedata

_transport_credential: ContextVar[str | None] = ContextVar(
    "witness_transport_credential", default=None
)
# thread_id -> {binding_id: raw_credential} for the in-memory adapter only.
_active_bindings: dict[int, dict[int, str]] = {}
_binding_ids = count()
_bindings_lock = Lock()


def _clear_bindings_after_fork() -> None:
    """Drop parent request state and replace possibly inherited locked mutexes."""
    global _bindings_lock
    _active_bindings.clear()
    _transport_credential.set(None)
    _bindings_lock = Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_clear_bindings_after_fork)


@dataclass(frozen=True)
class Principal:
    subject_id: str
    client_id: str
    role: str
    credential_type: str
    credential_id: str
    issuer: str
    audience: str
    issued_at: datetime
    expires_at: datetime
    revocation_status: str


@contextmanager
def bind_transport_credential(raw_credential: str | None) -> Iterator[None]:
    """Bind an opaque credential only for the current MCP call context."""
    token = _transport_credential.set(raw_credential)
    binding_id = next(_binding_ids)
    thread_id = get_ident()
    if isinstance(raw_credential, str) and raw_credential:
        with _bindings_lock:
            _active_bindings.setdefault(thread_id, {})[binding_id] = raw_credential
    try:
        yield
    finally:
        _transport_credential.reset(token)
        with _bindings_lock:
            bindings = _active_bindings.get(thread_id)
            if bindings is not None:
                bindings.pop(binding_id, None)
                if not bindings:
                    _active_bindings.pop(thread_id, None)


def _transport_credential_with_source() -> tuple[str | None, bool]:
    """Return ``(credential, is_request_local)`` and fail closed on ambiguity."""
    contextual = _transport_credential.get()
    if isinstance(contextual, str) and contextual:
        return contextual, True
    with _bindings_lock:
        distinct = set(_active_bindings.get(get_ident(), {}).values())
    return (distinct.pop(), False) if len(distinct) == 1 else (None, False)


def current_transport_credential() -> str | None:
    """Return this request's credential, or None when it is absent or ambiguous."""
    return _transport_credential_with_source()[0]


def _canonical_identifier(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("claim")
    value.encode("utf-8", "strict")
    canonical = unicodedata.normalize("NFC", value)
    if canonical != value or not 1 <= len(value) <= 128:
        raise ValueError("claim")
    return value


def resolve_principal(provider: Any) -> Principal:
    """Resolve and validate a principal afresh; any uncertainty fails closed."""
    raw, request_local = _transport_credential_with_source()
    if not isinstance(raw, str) or not raw:
        raise ValueError("authentication")
    try:
        resolved = provider.resolve(raw)
        if isinstance(resolved, Principal):
            principal = resolved
        elif isinstance(resolved, dict):
            required = set(Principal.__dataclass_fields__)
            if set(resolved) != required:
                raise ValueError("claim")
            principal = Principal(**resolved)
        else:
            raise ValueError("claim")
        # The registry exists solely because FastMCP's in-memory acceptance
        # adapter opens its server task before a per-call ContextVar is bound.
        # It is not an authenticated production transport and therefore cannot
        # confer OAuth or API-key authority.
        if not request_local and principal.credential_type != "synthetic_test_provider":
            raise ValueError("binding")
        for field in (
            "subject_id", "client_id", "role", "credential_type", "credential_id",
            "issuer", "audience", "revocation_status",
        ):
            _canonical_identifier(getattr(principal, field))
        if principal.role not in {"reader", "writer", "admin"}:
            raise ValueError("role")
        if principal.credential_type not in {
            "oauth_bearer", "api_key_provider", "synthetic_test_provider"
        }:
            raise ValueError("credential_type")
        if principal.issuer != provider.issuer or principal.audience != provider.audience:
            raise ValueError("binding")
        if principal.revocation_status != "active":
            raise ValueError("revocation")
        if not isinstance(principal.issued_at, datetime) or not isinstance(principal.expires_at, datetime):
            raise ValueError("time")
        now = datetime.now(timezone.utc)
        issued = principal.issued_at.astimezone(timezone.utc)
        expires = principal.expires_at.astimezone(timezone.utc)
        if issued.timestamp() > now.timestamp() + 30 or expires <= issued or expires <= now:
            raise ValueError("time")
        return principal
    except Exception as exc:
        raise ValueError("authentication") from exc
