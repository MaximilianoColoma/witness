# Witness Evidence product roadmap

Witness Evidence is the **open evidence layer for agentic systems**. This roadmap describes developer capabilities and integrations. Tests, measurements, failure cases, and verification results live in [Evidence and proof status](EVIDENCE.md).

The roadmap advances by capability gates, not dates or feature volume. `Runs today`, `building next`, and `north star` are deliberately different claims.

## Runs today — v0.1.0 shipped

Version `0.1.0` provides:

- a reproducible Apache-2.0 public core;
- 10 MCP tools for projects, decisions, insights, outcomes, records, lifecycle, bounded context, and local FTS5 search;
- signed identity envelopes, request binding, default-deny roles, and idempotent mutations;
- privacy redaction before persistence;
- transactional append-only operations audit;
- a real local roundtrip using distinct synthetic builder/validator identities and public fresh-install verification.

Proof status: [`verified`](EVIDENCE.md#v010-core-on-current-main--verified-local-evidence).

## Building next — cross-model project continuity

### Developer capability

Goal: enable Claude, Codex, GPT, local models, and specialist agents to use the same bounded project state and continue work without access to the original conversation.

### Planned interfaces

1. a portable context contract for current decision, outcome, evidence references, acceptance state, and allowed inheritance;
2. a reference MCP-client recipe that does not depend on one model vendor;
3. first-party examples for at least Claude and Codex after the vendor-neutral contract is stable;
4. explicit error and recovery behavior when context is incomplete, stale, unauthorized, or contradictory.

### Exit gate

A separate agent team with no transcript access reconstructs the accepted project state correctly. Reconstruction time, incorrect answers, missing evidence, authorization failures, and operator intervention are recorded.

Proof status: [`planned — not yet run`](EVIDENCE.md#cross-model-project-continuity--planned-proof).

**Next proof record:** the acceptance run and its failures belong in `EVIDENCE.md`; the capability remains the roadmap headline.

## After that — portable verification and integration recipes

### Portable verification

An external validator can inspect a released evidence bundle without trusting the builder’s narration or the live Witness server.

Planned capability:

- stable evidence-bundle schema;
- explicit digest and receipt linking;
- public verifier;
- tamper-detection proof against a modified released record.

### Agent-runtime recipes

Documented, exercised integration paths for:

- OpenAI Agents SDK;
- LangGraph;
- Temporal;
- PydanticAI and custom MCP clients.

Each recipe must show one complete decision → outcome → separate acceptance → context-recovery flow. A logo or configuration snippet alone is not an integration proof.

### Mission suite integration

Mission remains a separate coordination product. Integration requires versioned receipt linking and explicit failure semantics, not hidden shared state or an automatic bridge.

## Operational capability — deployable and recoverable service

Only after the local and cross-model contracts are stable:

- deployment profile and health/SLO contract;
- backup, restore, and corruption-recovery proof;
- operator quickstart completed by a fresh user in under 15 minutes;
- tenant isolation and authentication lifecycle before hosted multi-user operation.

A GitHub release is not a deployment or runtime proof.

## North star — verified learning return

Verified outcomes should improve later decisions without allowing unverified text to silently become policy.

This requires a separately governed learning layer with:

- eligibility rules for what may become a learning candidate;
- provenance back to decisions, evidence, outcomes, and validators;
- review, supersession, revocation, and rollback;
- measured improvement on a later bounded task;
- guardrails against self-confirming or poisoned feedback loops.

Spindle-style learning remains separate from Witness. Witness supplies evidence-bearing project state; it does not automatically train models, rewrite policy, or operate an autonomous learning loop in `v0.1.0`.

## Community and adoption

After one successful external continuity proof:

- publish reference flows and bounded benchmarks;
- open RFCs for the portable context and evidence-bundle contracts;
- label integration contribution issues;
- accept adapters only with executable examples and claim-bounded proof records.

## Not promised

- no dates for unbuilt capabilities;
- no semantic/vector search in the current core;
- no bundled scheduler or agent-spawning runtime;
- no first-party model/runtime adapters in `v0.1.0`;
- no automatic Mission bridge or Spindle learning loop;
- no hosted service, scale, savings, or customer-outcome claim without external evidence.

Every capability gate requires prewritten acceptance, a distinct validator, and readback from the actual target environment. Detailed status and results belong in [`EVIDENCE.md`](EVIDENCE.md), not in the roadmap narrative.
