from __future__ import annotations
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
import hashlib
import json
import time
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from witness_public.auth import Principal
from witness_public.identity import MemoryReplayStore, VerificationContext, sign_envelope
from witness_public.server import create_server


def _pub(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


class SyntheticCredentialProvider:
    issuer = "test-issuer"
    audience = "witness"

    def __init__(self):
        self.records = {}
        self.lookup_failure = False
        self._principal_keys = {}
        self._logical_subjects = {}
        self._owner_key = Ed25519PrivateKey.generate()
        self._profile_hash = hashlib.sha256(b"synthetic-profile-v1").hexdigest()
        self._generation = "11111111-1111-4111-8111-111111111111"
        self.identity_context = VerificationContext(
            tenant_id="witness-test-tenant",
            profile_hashes={"synthetic-profile": self._profile_hash},
            active_runtime_generations=frozenset({self._generation}),
            replay_store=MemoryReplayStore(),
            now=lambda: int(time.time()),
        )

    def issue(self, subject_id="agent-a", role="admin", expires_delta=3600,
              issued_offset=0, revocation_status="active", issuer=None,
              audience=None, drop_field=None):
        now = datetime.now(timezone.utc)
        token = f"synthetic-{len(self.records)+1}"
        principal_key = Ed25519PrivateKey.generate()
        principal_pubkey = _pub(principal_key)
        value = Principal(
            subject_id=principal_pubkey,
            client_id="test-client",
            role=role,
            credential_type="synthetic_test_provider",
            credential_id=f"cred-{len(self.records)+1}",
            issuer=issuer or self.issuer,
            audience=audience or self.audience,
            issued_at=now + timedelta(seconds=issued_offset),
            expires_at=now + timedelta(seconds=expires_delta),
            revocation_status=revocation_status,
        )
        if drop_field:
            value = asdict(value)
            value.pop(drop_field, None)
        self.records[token] = value
        self._principal_keys[token] = principal_key
        self._logical_subjects[token] = subject_id
        return token

    def resolve(self, raw_credential):
        if self.lookup_failure:
            raise RuntimeError("provider unavailable")
        return self.records.get(raw_credential)

    def revoke(self, token):
        p = self.records[token]
        self.records[token] = Principal(**{**p.__dict__, "revocation_status": "revoked"})

    def principal_pubkey(self, token: str) -> str:
        return _pub(self._principal_keys[token])

    def prepare(self, token: str, tool: str, args: dict) -> dict:
        payload = dict(args)
        logical = self._logical_subjects[token]
        if payload.get("caller_instance_id") == logical:
            payload["caller_instance_id"] = self.principal_pubkey(token)
        now = int(time.time())
        principal_key = self._principal_keys[token]
        principal = self.principal_pubkey(token)
        owner = _pub(self._owner_key)
        conditions = json.dumps(
            {
                "capabilities": [tool],
                "expires_at": now + 120,
                "not_before": now - 1,
                "principal_pubkey": principal,
                "profile_id": "synthetic-profile",
                "profile_version_sha256": self._profile_hash,
                "tenant_id": "witness-test-tenant",
                "runtime_generation": self._generation,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        attestation = {
            "conditions": conditions,
            "signature": self._owner_key.sign(
                b"witness-mission:agent-auth:v1:owner-attestation:" + conditions.encode()
            ).hex(),
        }
        try:
            payload_bytes = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        except UnicodeEncodeError:
            # Build a structurally valid envelope so the service itself proves
            # malformed Unicode is rejected before storage.
            payload_bytes = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
            ).encode()
        envelope = {
            "version": "1.0",
            "principal_pubkey": principal,
            "owner_pubkey": owner,
            "owner_attestation": attestation,
            "profile_id": "synthetic-profile",
            "profile_version_sha256": self._profile_hash,
            "tenant_id": "witness-test-tenant",
            "runtime_generation": self._generation,
            "tool_name": tool,
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "nonce": str(uuid4()),
            "issued_at": now - 1,
            "expires_at": now + 60,
        }
        return {**payload, "identity_envelope": sign_envelope(envelope, principal_key)}


class FaultInjector:
    def __init__(self, *stages):
        self.stages = set(stages)

    def __call__(self, stage):
        if stage in self.stages:
            raise RuntimeError(f"synthetic fault:{stage}")


@pytest.fixture
def provider():
    return SyntheticCredentialProvider()


@pytest.fixture
def server(tmp_path, provider):
    return create_server(
        db_path=tmp_path / "witness.db",
        credential_provider=provider,
        identity_context=provider.identity_context,
    )
