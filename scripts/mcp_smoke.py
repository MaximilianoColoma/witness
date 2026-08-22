from __future__ import annotations
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from fastmcp import Client
from witness_public.server import create_server

class Provider:
    issuer = "fresh-install-smoke"
    audience = "witness"
    def resolve(self, raw_credential):
        raise RuntimeError("smoke never authenticates")

async def main():
    with TemporaryDirectory() as temp:
        server = create_server(db_path=Path(temp) / "witness.db", credential_provider=Provider())
        async with Client(server) as client:
            tools = await client.list_tools()
        names = sorted(tool.name for tool in tools)
        assert len(names) == 10, names
        print(f"MCP_FIRST_RUN_PASS product=witness tools={len(names)}")

asyncio.run(main())
