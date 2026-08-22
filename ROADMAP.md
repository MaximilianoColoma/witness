# Witness product roadmap

Witness is the evidence layer for accountable agent work. The roadmap advances by **observable proof gates**, not dates or feature volume.

## v0.1.0 — shipped

- Apache-2.0 public core and reproducible release artifacts
- 10 MCP tools for projects, decisions, insights, outcomes, records, lifecycle and bounded search
- signed identity envelopes, request binding, default-deny roles and idempotent mutations
- privacy redaction before persistence
- transactional append-only operations audit
- real local roundtrip demo and public fresh-install verification

## Next proof — one external agent team restores and verifies context

**Claim to prove:** a planner, builder and validator can use Witness during a real bounded project and a different model can later recover why the work was accepted.

Exit evidence:

1. public install completes from scratch;
2. the team records at least one decision, outcome and receipt;
3. a separate agent retrieves the bounded context without transcript access;
4. the agent correctly identifies the current decision and evidence;
5. owner reconstruction time and failure cases are recorded.

## Next product layer — suite integration

Build only after the external context-recovery proof:

- documented integration recipe for Mission and common agent clients;
- explicit receipt linking rather than hidden cross-service side effects;
- deployment profile, health/SLO contract, backup and restore proof;
- operator quickstart that a fresh user completes in under 15 minutes.

## Later proof gates

### Tamper-evident verification

Hash-chain/Merkle evidence and a public verifier. Exit: an external party detects a modified released record without trusting the Witness server.

### Multi-tenant service

Tenant isolation, authentication lifecycle and operational recovery. Exit: two test tenants complete isolation and deletion tests with zero cross-access.

### Sustainable SaaS

Metering, seats, billing and support only after repeat usage proves that Witness removes meaningful review or reconstruction work.

### Learning layer

Spindle-style learning remains separate. Exit: verified outcomes improve a later decision without allowing unverified text to silently become policy.

## Not promised

- no release date for later stages;
- no semantic/vector search in the current core;
- no bundled agent scheduler or spawning runtime;
- no automatic Mission bridge in v0.1.0;
- no hosted service, scale, savings or customer-outcome claim without external evidence.

Every stage requires prewritten acceptance, a distinct validator and readback from the actual target environment.
