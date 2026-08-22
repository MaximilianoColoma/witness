#!/usr/bin/env python3
"""Real local Witness flow using the public MCP server and synthetic signed identity."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from conftest import SyntheticCredentialProvider  # noqa: E402
from witness_public.auth import bind_transport_credential  # noqa: E402
from witness_public.server import create_server  # noqa: E402


def body(result):
    return json.loads(result.content[0].text)


async def main() -> None:
    provider = SyntheticCredentialProvider()
    builder = provider.issue("builder-agent", "admin")
    validator = provider.issue("validator-agent", "admin")
    with TemporaryDirectory(prefix="witness-real-demo-") as temporary:
        server = create_server(
            db_path=Path(temporary) / "witness.db",
            credential_provider=provider,
            identity_context=provider.identity_context,
        )

        async def call(client, token, tool, arguments):
            prepared = provider.prepare(token, tool, arguments)
            with bind_transport_credential(token):
                return body(await client.call_tool(tool, prepared, raise_on_error=False))

        async with Client(server) as client:
            await call(client, builder, "tool_register_project", {
                "name": "autonomous-release", "domains": "engineering",
                "description": "A real local multi-agent proof flow.",
                "caller_instance_id": "builder-agent", "request_id": "demo-project",
            })
            decision = await call(client, builder, "tool_log_decision", {
                "project": "autonomous-release", "title": "Require independent validation",
                "decision": "The builder may build, but a separate validator must accept the evidence.",
                "rationale": "Execution and acceptance are different authorities.",
                "caller_instance_id": "builder-agent", "request_id": "demo-decision",
            })
            outcome = await call(client, builder, "tool_log_outcome", {
                "project": "autonomous-release", "task_summary": "Build and validate release candidate",
                "result": "success", "workflow_chain": "planner -> builder -> distinct validator",
                "based_on": "receipt:sha256:demo-evidence",
                "caller_instance_id": "builder-agent", "request_id": "demo-outcome",
            })
            verified = await call(client, validator, "tool_update_status", {
                "entry_id": outcome["id"], "new_status": "verified",
                "reason": "Distinct validator accepted the synthetic evidence reference.",
                "caller_instance_id": "validator-agent", "request_id": "demo-verify",
            })
            context = await call(client, validator, "tool_get_context_for", {
                "project": "autonomous-release", "max_items": 20,
            })

        assert decision["status"] == outcome["status"] == verified["status"] == context["status"] == "ok"
        assert len(context["decisions"]) == 1 and len(context["outcomes"]) == 1
        assert context["outcomes"][0]["status"] == "verified"
        with sqlite3.connect(Path(temporary) / "witness.db") as database:
            validator_subject = provider.principal_pubkey(validator)
            audit = database.execute(
                "SELECT principal_subject_id FROM operations_log WHERE tool_name='tool_update_status' AND result_code='OK'"
            ).fetchone()
        assert audit and audit[0] == validator_subject
        assert provider.principal_pubkey(builder) != validator_subject
        print("[1/3] Decision witnessed: builder cannot validate its own release")
        print("[2/3] Outcome verified by a distinct validator identity")
        print("[3/3] Project context restored from the database")
        print("WITNESS_DEMO_PASS decisions=1 outcomes=1 outcome_status=verified distinct_validator=true context_restored=true")


if __name__ == "__main__":
    asyncio.run(main())
