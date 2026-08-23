# Witness Evidence — evidence and proof status

This file separates product direction from proof. The [Product roadmap](ROADMAP.md) says which developer capabilities Witness is building; this file records what has actually run, what has not, the acceptance conditions, and the limits of each result.

## Status vocabulary

| Status | Meaning |
|---|---|
| `verified` | The named test ran on identified product bytes and produced recorded output. |
| `planned — not yet run` | Acceptance is defined, but no result is claimed. |
| `blocked` | A named prerequisite is missing and the capability is not accepted. |
| `superseded` | A newer proof record replaces the result for current bytes. |

A green repository test proves only its stated boundary. It does not prove deployment, production scale, customer value, or every environment.

## v0.1.0 core on current main — verified local evidence

**Status: `verified`**

### Real local product flow

Tested on `2026-08-23` with Python `3.11.15`, from a documentation candidate based on main commit `46da0c679a3684f16dea5e827fa25854221ba5ee`.

The demo was added after the `v0.1.0` tag. It exercises product source bytes unchanged from `v0.1.0`, but the demo itself is not present in the immutable `v0.1.0` release assets.

Command:

```bash
uv sync --locked
uv run python examples/coordinated_autonomy_demo.py
```

Expected receipt:

```text
WITNESS_DEMO_PASS decisions=1 outcomes=1 outcome_status=verified distinct_validator=true context_restored=true
```

What it proves:

- the actual public MCP server starts locally;
- signed synthetic builder and validator identities are distinct;
- a project, decision, and outcome persist in SQLite;
- the distinct synthetic validator used by the demo can move the outcome from `recorded` to `verified`;
- bounded project context can be restored from persistence.

What it does not prove:

- the evidence reference itself is automatically fetched or independently validated;
- builder/validator separation is enforced by the product rather than chosen by this demo;
- the outcome's `based_on` evidence reference is exposed by the public read projection;
- a third-party model integration works without custom wiring;
- hosted operation, multi-tenant isolation, scale, savings, or customer impact.

### Fresh installation and repository verification

The released repository includes acceptance coverage for:

- staged manifest and machine-readable failure states;
- inherited Python-environment scrubbing;
- locked installation with `uv`;
- local configuration and storage;
- real MCP first-run doctor;
- idempotent rerun;
- product, privacy, identity, audit, contract, build, SBOM, license, and scan checks.

Canonical commands:

```bash
./install.sh --manifest --json
./install.sh --target "$HOME/.local/share/witness" --non-interactive --json
uv run python -m pytest -q -p no:cacheprovider tests repair-tests
uv build
```

The immutable release record is [Witness v0.1.0](https://github.com/MaximilianoColoma/witness/releases/tag/v0.1.0). The tag points to `2eeb481276d77131ee9452b5ef9c5d6420dffb26`; later documentation changes do not replace its tag or assets.

## Cross-model project continuity — planned proof

**Status: `planned — not yet run`**

### Capability under test

A different model or agent team retrieves bounded Witness state and continues a project correctly with **no access to the original chat**.

### Acceptance conditions

1. A fresh public installation completes from scratch.
2. A planner records the current decision and acceptance rule.
3. A builder records an outcome and evidence reference.
4. A distinct validator records acceptance or dispute.
5. A different model receives only bounded Witness access and the project identifier.
6. It identifies the current decision, outcome, evidence reference, acceptance state, and unresolved limits correctly.
7. It proposes a next action that does not contradict the accepted state.
8. Reconstruction time, tool calls, operator intervention, incorrect answers, and missing fields are recorded.

### Minimum participants

- one originating planner/builder path;
- one separately identified validator;
- one recovery agent using a different model family where practical;
- one human or independent evaluator scoring reconstruction accuracy.

### Measurements

| Measure | Required record |
|---|---|
| Reconstruction accuracy | Exact fields recovered versus expected fields |
| reconstruction time | Start to accepted answer |
| Tool usage | Number and type of Witness calls |
| Operator load | Clarifications or manual corrections required |
| Evidence fidelity | Correct evidence references and stated limitations |
| Unsafe inference | Claims not present in bounded state |

No benchmark result exists yet. Blank cells are not silently interpreted as success.

## Failure cases to record

The planned continuity proof must preserve failures, not only the best run:

- missing project or entry;
- stale or superseded decision;
- contradictory outcomes;
- evidence reference present but not independently verifiable;
- unauthorized identity or tenant mismatch;
- bounded result omits a needed field;
- recovery agent invents transcript context;
- model selects an obsolete outcome;
- operator has to reveal the original chat;
- reconstruction exceeds the agreed time or intervention bound.

A failure may improve the product contract; it cannot be edited out of the proof record.

## Portable verification — planned proof

**Status: `planned — not yet run`**

Acceptance requires a released evidence bundle, a public verifier, a deliberate record modification, and an external party detecting the mismatch without trusting the live Witness server.

## Verified learning return — north-star proof

**Status: `planned — not yet run`**

Acceptance requires a later bounded task to improve because of a provenance-bound, separately accepted earlier outcome. The proof must also show that unverified text, revoked evidence, and superseded decisions do not silently become policy.

Witness `v0.1.0` does not implement this learning loop.

## Adding evidence

A proof contribution should include:

1. tested commit or release digest;
2. environment and model/client versions;
3. prewritten acceptance conditions;
4. exact commands or reproducible harness;
5. raw result and failure cases;
6. statement limits;
7. a validator distinct from the builder.

Open an issue before adding a new benchmark category so comparable runs use the same contract.
