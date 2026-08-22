"""GHR-001 preimplementation RED: Witness dispatch must enforce the shared envelope."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastmcp import Client

from witness_public.auth import Principal, bind_transport_credential
from witness_public.identity import SQLiteReplayStore, VerificationContext, sign_envelope
from witness_public.server import create_server


def pub(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


class Provider:
    issuer = "test-issuer"
    audience = "witness"

    def __init__(self, subject: str):
        now = datetime.now(timezone.utc)
        self.token = "synthetic-envelope-token"
        self.principal = Principal(
            subject_id=subject,
            client_id="test-client",
            role="admin",
            credential_type="synthetic_test_provider",
            credential_id="cred-envelope",
            issuer=self.issuer,
            audience=self.audience,
            issued_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(hours=1),
            revocation_status="active",
        )

    def resolve(self, raw):
        return self.principal if raw == self.token else None


def make_envelope(principal_key, owner_key, payload, tool, now, nonce):
    principal = pub(principal_key)
    owner = pub(owner_key)
    profile_hash = hashlib.sha256(b"profile-v1").hexdigest()
    generation = "11111111-1111-4111-8111-111111111111"
    conditions = json.dumps(
        {
            "capabilities": [tool],
            "expires_at": now + 120,
            "not_before": now - 1,
            "principal_pubkey": principal,
            "profile_id": "hermes-handwerker",
            "profile_version_sha256": profile_hash,
            "tenant_id": "tenant-server",
            "runtime_generation": generation,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    attestation = {
        "conditions": conditions,
        "signature": owner_key.sign(
            b"witness-mission:agent-auth:v1:owner-attestation:" + conditions.encode()
        ).hex(),
    }
    unsigned = {
        "version": "1.0",
        "principal_pubkey": principal,
        "owner_pubkey": owner,
        "owner_attestation": attestation,
        "profile_id": "hermes-handwerker",
        "profile_version_sha256": profile_hash,
        "tenant_id": "tenant-server",
        "runtime_generation": generation,
        "tool_name": tool,
        "payload_sha256": "0" * 64,
        "nonce": nonce,
        "issued_at": now - 1,
        "expires_at": now + 60,
    }
    context = VerificationContext(
        tenant_id="tenant-server",
        profile_hashes={"hermes-handwerker": profile_hash},
        active_runtime_generations=frozenset({generation}),
        replay_store=SQLiteReplayStore(str(payload["_replay_db"])),
        now=lambda: now,
    )
    clean_payload = {k: v for k, v in payload.items() if k != "_replay_db"}
    unsigned["payload_sha256"] = hashlib.sha256(
        json.dumps(clean_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    return sign_envelope(unsigned, principal_key), context


def body(result):
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_envelope_is_required_verified_and_audited_before_witness_mutation(tmp_path):
    now = 2_000_000_000
    principal_key, owner_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    provider = Provider(pub(principal_key))
    db_path = tmp_path / "witness.db"
    payload = {
        "name": "demo",
        "domains": "engineering",
        "caller_instance_id": pub(principal_key),
        "request_id": "identity-project",
        "_replay_db": tmp_path / "replay.db",
    }
    envelope, context = make_envelope(
        principal_key, owner_key, payload, "tool_register_project", now,
        "22222222-2222-4222-8222-222222222222",
    )
    clean = {k: v for k, v in payload.items() if k != "_replay_db"}
    server = create_server(
        db_path=db_path,
        credential_provider=provider,
        identity_context=context,
    )
    async with Client(server) as client:
        with bind_transport_credential(provider.token):
            missing = body(await client.call_tool("tool_register_project", clean, raise_on_error=False))
        with bind_transport_credential(provider.token):
            accepted = body(await client.call_tool(
                "tool_register_project", {**clean, "identity_envelope": envelope}, raise_on_error=False
            ))
        with bind_transport_credential(provider.token):
            replay = body(await client.call_tool(
                "tool_register_project", {**clean, "identity_envelope": envelope}, raise_on_error=False
            ))

    assert missing["code"] == "AUTHENTICATION_REQUIRED"
    assert accepted["status"] == "ok"
    assert replay["code"] == "REPLAY_DETECTED"
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM project_registry").fetchone()[0] == 1
        row = db.execute(
            "SELECT principal_pubkey,owner_pubkey,profile_id,profile_version_sha256,tenant_id,runtime_generation,envelope_nonce,payload_sha256 "
            "FROM operations_log WHERE result_code='OK'"
        ).fetchone()
    assert row == (
        pub(principal_key), pub(owner_key), "hermes-handwerker",
        hashlib.sha256(b"profile-v1").hexdigest(), "tenant-server",
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222", envelope["payload_sha256"],
    )


@pytest.mark.anyio
async def test_payload_mismatch_cannot_reach_business_lookup_or_consume_nonce(tmp_path):
    now = 2_000_000_000
    principal_key, owner_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    provider = Provider(pub(principal_key))
    payload = {
        "name": "hidden",
        "domains": "engineering",
        "caller_instance_id": pub(principal_key),
        "request_id": "identity-mismatch",
        "_replay_db": tmp_path / "replay.db",
    }
    envelope, context = make_envelope(
        principal_key, owner_key, payload, "tool_register_project", now,
        "33333333-3333-4333-8333-333333333333",
    )
    clean = {k: v for k, v in payload.items() if k != "_replay_db"}
    server = create_server(db_path=tmp_path / "witness.db", credential_provider=provider, identity_context=context)
    async with Client(server) as client:
        with bind_transport_credential(provider.token):
            mismatch = body(await client.call_tool(
                "tool_register_project", {**clean, "name": "changed", "identity_envelope": envelope}, raise_on_error=False
            ))
        with bind_transport_credential(provider.token):
            accepted = body(await client.call_tool(
                "tool_register_project", {**clean, "identity_envelope": envelope}, raise_on_error=False
            ))
    assert mismatch["code"] == "REQUEST_BINDING_MISMATCH"
    assert accepted["status"] == "ok"
