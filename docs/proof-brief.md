# Product proof brief — Witness Evidence positioning

**Audience:** experienced agent-platform and AI-infrastructure engineers already operating multiple agents, models, or durable workflows; secondarily staff/principal engineers and agent-security, reliability, and governance engineers.

**Category:** Open Evidence Layer for Agentic Systems.

**Current claim:** the Witness v0.1.0 core preserves identity-bound decisions, outcomes, status-transition identity/reason, audit history, and bounded project context through ten local MCP tools. The outcome write path persists `based_on`, but the current public read projection does not expose that field.

**Observable proof:** run the public MCP server locally, write one project decision and one outcome with a signed synthetic builder identity, use a distinct synthetic validator identity to move the outcome to `verified`, then retrieve bounded project context. This demonstrates chosen separation in the demo, not an enforced builder/validator invariant.

**Source truth:** real Witness v0.1.0 public-core source behavior and contracts. The demo was added after the v0.1.0 tag and is not part of the immutable release assets; it exercises unchanged v0.1.0 product source. No cloud service, customer metric, first-party model/runtime adapter, automatic evidence verification, automatic Mission bridge, or Spindle learning behavior is claimed.

**Destination:** GitHub README as the category landing page; ROADMAP.md as capability direction; EVIDENCE.md as proof status and acceptance record; source-checkout terminal demo as primary current proof.

**Evidence class: real.** The terminal demonstration executes the actual server, identity envelope, MCP calls, SQLite persistence, status transition, and bounded context read with synthetic credentials.

**Truth horizons:**

- `Runs today`: exact v0.1.0 behavior.
- `Building next`: cross-model project continuity with a prewritten external proof.
- `North star`: portable verification and verified learning return, explicitly not current functionality.

**Desired action:** an experienced agent-platform engineer understands the category in one screen, runs the real demo, inspects the evidence limits, and can see the next integration capability without mistaking it for shipped functionality.

**Naming boundary:** “Witness Evidence” qualifies public prose. Repository, package, module, MCP tools, contracts, and v0.1.0 artifacts keep their technical identifiers. The unrelated in-toto/witness project is disclosed without implying affiliation or making a legal conclusion.

**Constraints:** no invented integrations, users, savings, scale, semantic search, deployment, multi-tenant operation, external artifact verification, automatic learning, or customer outcomes. Emotional lines describe direction, not measured economics.
