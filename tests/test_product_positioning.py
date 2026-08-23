"""Preimplementation acceptance for Witness category, capability roadmap and proof separation."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_readme_establishes_category_audience_and_problem():
    readme = text("README.md")
    assert readme.startswith("# Witness Evidence\n")
    assert "Open Evidence Layer for Agentic Systems" in readme
    assert "agent-platform and AI-infrastructure engineers" in readme
    assert "Your agents can act. Witness preserves what was decided, which evidence was attached, and what the next agent may inherit." in readme
    assert "Delegate execution without delegating truth." in readme
    assert "Every token should leave the system more valuable than before." in readme


def test_readme_separates_truth_horizons_and_suite_boundaries():
    readme = text("README.md")
    for heading in ("## Runs today", "## Building next", "## North star"):
        assert heading in readme
    assert "not automatic evidence verification" in readme
    assert "not automatic cross-model learning" in readme
    assert "Mission and Spindle are separate systems" in readme
    assert "technical identifiers remain unchanged" in readme
    assert "Witness Evidence is the public-facing qualifier" in readme


def test_readme_positions_witness_between_protocols_traces_and_runtimes():
    readme = text("README.md")
    assert "MCP connects agents to tools." in readme
    assert "A2A connects agents to agents." in readme
    assert "Traces show what ran." in readme
    assert "Durable runtimes keep workflows alive." in readme
    assert "Witness preserves what was decided, which evidence was attached, which status transitions followed, and what the next agent may inherit." in readme
    assert "No first-party adapters for Claude, Codex, OpenAI Agents SDK, LangGraph, or Temporal ship in v0.1.0." in readme


def test_current_capability_precedes_future_claims_and_keeps_hard_boundaries():
    readme = text("README.md")
    runs_at = readme.index("## Runs today")
    building_at = readme.index("## Building next")
    north_at = readme.index("## North star")
    assert runs_at < building_at < north_at
    current = readme[runs_at:building_at]
    assert "does **not enforce builder/validator separation**" in current
    assert "public read projection" in current
    assert "not automatic evidence verification" in current
    for unshipped in ("Claude", "Codex", "OpenAI Agents SDK", "LangGraph", "Temporal", "Spindle", "SaaS", "cross-model learning"):
        assert unshipped not in current


def test_roadmap_is_capability_led_and_links_to_evidence():
    roadmap = text("ROADMAP.md")
    assert "## Runs today — v0.1.0 shipped" in roadmap
    assert "## Building next — cross-model project continuity" in roadmap
    assert "## After that — portable verification and integration recipes" in roadmap
    assert "## North star — verified learning return" in roadmap
    assert "[Evidence and proof status](EVIDENCE.md)" in roadmap
    assert "one external agent team restores and verifies context" not in roadmap.lower()


def test_evidence_owns_proof_status_acceptance_and_results():
    evidence = text("EVIDENCE.md")
    for heading in (
        "## Status vocabulary",
        "## v0.1.0 core on current main — verified local evidence",
        "## Cross-model project continuity — planned proof",
        "## Failure cases to record",
    ):
        assert heading in evidence
    assert "Status: `verified`" in evidence
    assert "Status: `planned — not yet run`" in evidence
    assert "no access to the original chat" in evidence
    assert "reconstruction time" in evidence
    assert "[Product roadmap](ROADMAP.md)" in evidence
    assert "The demo was added after the `v0.1.0` tag." in evidence
    assert "not present in the immutable `v0.1.0` release assets" in evidence
    assert "builder/validator separation is enforced by the product rather than chosen by this demo" in evidence


def test_brand_qualification_discloses_unrelated_project_without_rename():
    trademarks = text("TRADEMARKS.md")
    readme = text("README.md")
    assert "Witness Evidence" in trademarks
    assert "https://github.com/in-toto/witness" in trademarks
    assert "not affiliated" in trademarks.lower()
    assert "No legal conclusion" in trademarks
    assert "package `witness-public`" in trademarks
    assert "repository `MaximilianoColoma/witness`" in trademarks
    assert "Version `0.1.0`" in readme
    assert "Evidence & Learning Infrastructure for Multi-Agent Systems” is north-star language only" in trademarks


def test_local_markdown_links_resolve():
    files = [ROOT / name for name in ("README.md", "ROADMAP.md", "EVIDENCE.md", "TRADEMARKS.md")]
    link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    missing = []
    for source in files:
        for target in link.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = target.split("#", 1)[0]
            if local and not (source.parent / local).exists():
                missing.append(f"{source.name}: {target}")
    assert not missing, missing
