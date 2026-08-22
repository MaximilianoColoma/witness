from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import pytest
from fastmcp import Client

from witness_public.auth import bind_transport_credential
from witness_public.server import create_server
from conftest import FaultInjector


def payload(result):
    assert result.content
    return json.loads(result.content[0].text)


def assert_wire_response(name, body):
    wire = json.loads((Path(__file__).resolve().parents[1] / "spec" / "wire-contract.json").read_text())
    schema = wire["tools"][name]["response"]
    assert set(body) <= set(schema["properties"]), (name, set(body) - set(schema["properties"]))
    variant = schema["variants"]["success" if body.get("status") == "ok" else "error"]
    assert set(variant["required"]) <= set(body), (name, set(variant["required"]) - set(body))
    assert body["status"] == variant["status_const"]


async def call(client,provider,token,name,args,raise_on_error=False):
    prepared = provider.prepare(token, name, args)
    with bind_transport_credential(token):
        body = payload(await client.call_tool(name,prepared,raise_on_error=raise_on_error))
    assert_wire_response(name, body)
    return body


@pytest.mark.anyio
async def test_public_core_roundtrip_includes_record_over_mcp(server,provider):
    token=provider.issue()
    async with Client(server) as client:
        project=await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","description":"Synthetic project","caller_instance_id":"agent-a","request_id":"r-project"})
        decision=await call(client,provider,token,"tool_log_decision",{"project":"demo","title":"Use deterministic tests","decision":"Only synthetic examples enter fixtures.","caller_instance_id":"agent-a","domain":"engineering","request_id":"r-decision"})
        insight=await call(client,provider,token,"tool_log_insight",{"title":"Determinism helps review","insight":"Stable fixtures make failures reproducible.","caller_instance_id":"agent-a","project":"demo","request_id":"r-insight"})
        outcome=await call(client,provider,token,"tool_log_outcome",{"project":"demo","task_summary":"Run synthetic validation","result":"success","caller_instance_id":"agent-a","request_id":"r-outcome"})
        record=await call(client,provider,token,"tool_log_record",{"project":"demo","record_type":"receipt","title":"Synthetic receipt","content":"No production content.","caller_instance_id":"agent-a","request_id":"r-record"})
        context=await call(client,provider,token,"tool_get_context_for",{"project":"demo","max_items":20})
    assert project["status"]=="ok"
    ids={decision["id"],insight["id"],outcome["id"],record["id"]}
    observed={item["id"] for kind in ("decisions","insights","outcomes","records") for item in context[kind]}
    assert ids <= observed


@pytest.mark.anyio
async def test_malformed_fts_query_returns_closed_invalid_input_envelope(server, provider):
    token = provider.issue()
    async with Client(server) as client:
        result = await call(
            client, provider, token, "tool_query_log_fts5",
            {"query": '"unterminated', "caller_instance_id": "agent-a"}, False,
        )
    assert result["status"] == "error"
    assert result["code"] == "INVALID_INPUT"
    assert set(result) == {"status", "correlation_id", "code", "message"}


@pytest.mark.anyio
@pytest.mark.parametrize("credential_case",["missing","missing_claim","expired","revoked","indeterminate","future_issued","boundary_future","wrong_issuer","wrong_audience","unknown_role","provider_failure"])
async def test_credentials_fail_closed_before_dispatch(server,provider,credential_case):
    token=None
    if credential_case!="missing":
        kwargs={}
        if credential_case=="expired": kwargs["expires_delta"]=-1
        if credential_case=="revoked": kwargs["revocation_status"]="revoked"
        if credential_case=="indeterminate": kwargs["revocation_status"]="unknown"
        if credential_case=="future_issued": kwargs["issued_offset"]=3600
        if credential_case=="boundary_future": kwargs["issued_offset"]=31
        if credential_case=="wrong_issuer": kwargs["issuer"]="wrong-issuer"
        if credential_case=="wrong_audience": kwargs["audience"]="wrong-audience"
        if credential_case=="missing_claim": kwargs["drop_field"]="audience"
        if credential_case=="unknown_role": kwargs["role"]="invented"
        token=provider.issue(**kwargs)
    if credential_case=="provider_failure": provider.lookup_failure=True
    async with Client(server) as client:
        if token is None:
            result=payload(await client.call_tool("tool_query_log",{"limit":1},raise_on_error=False))
        else:
            result=await call(client,provider,token,"tool_query_log",{"limit":1},False)
    assert result["code"]=="AUTHENTICATION_REQUIRED"


@pytest.mark.anyio
async def test_mismatch_and_role_denials_precede_lookup_or_mutation(server,provider):
    writer=provider.issue(role="writer")
    reader=provider.issue(subject_id="reader-a",role="reader")
    async with Client(server) as client:
        mismatch=await call(client,provider,writer,"tool_log_decision",{"project":"SECRET-ID","title":"No","decision":"No","caller_instance_id":"owner","request_id":"mismatch"},False)
        reader_write=await call(client,provider,reader,"tool_log_decision",{"project":"unknown","title":"No","decision":"No","caller_instance_id":"reader-a","request_id":"deny-1"},False)
        writer_admin=await call(client,provider,writer,"tool_update_status",{"entry_id":"unknown","new_status":"archived","caller_instance_id":"agent-a","request_id":"deny-2"},False)
    assert mismatch["code"]=="IDENTITY_MISMATCH" and "SECRET-ID" not in json.dumps(mismatch)
    assert reader_write["code"]=="PERMISSION_DENIED"
    assert writer_admin["code"]=="PERMISSION_DENIED"


@pytest.mark.anyio
async def test_status_fsm_valid_and_invalid_transition_has_no_mutation(server,provider):
    token=provider.issue()
    async with Client(server) as client:
        await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","caller_instance_id":"agent-a","request_id":"fsm-p"})
        decision=await call(client,provider,token,"tool_log_decision",{"project":"demo","title":"FSM","decision":"Test transitions","caller_instance_id":"agent-a","request_id":"fsm-d"})
        locked=await call(client,provider,token,"tool_update_status",{"entry_id":decision["id"],"new_status":"locked","caller_instance_id":"agent-a","request_id":"fsm-lock"})
        invalid=await call(client,provider,token,"tool_update_status",{"entry_id":decision["id"],"new_status":"proposed","caller_instance_id":"agent-a","request_id":"fsm-back"},False)
        got=await call(client,provider,token,"tool_get_entry",{"entry_id":decision["id"]})
    assert locked["status"]=="ok" and invalid["code"]=="CONFLICT"
    assert got["entry"]["status"]=="locked"


@pytest.mark.anyio
async def test_pii_redacted_before_storage_and_error_does_not_echo(server,provider,tmp_path):
    token=provider.issue(); db_path=tmp_path/"privacy.db"; server=create_server(db_path=db_path,credential_provider=provider,identity_context=provider.identity_context)
    async with Client(server) as client:
        await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","description":"person@example.com","caller_instance_id":"agent-a","request_id":"pii-p"})
        created=await call(client,provider,token,"tool_log_record",{"project":"demo","record_type":"receipt","title":"person@example.com","content":"Owner person@example.com","caller_instance_id":"agent-a","request_id":"pii-r"})
        got=await call(client,provider,token,"tool_get_entry",{"entry_id":created["id"]})
        invalid=await call(client,provider,token,"tool_log_record",{"project":"demo","record_type":"receipt","title":"x","content":"\ud800","caller_instance_id":"agent-a","request_id":"pii-bad"},False)
    assert "person@example.com" not in json.dumps(got)
    assert "\ud800" not in json.dumps(invalid) and invalid["code"]=="INVALID_INPUT"
    with sqlite3.connect(db_path) as db:
        dump=" ".join(str(x) for row in db.execute("SELECT title,content FROM records") for x in row)
    assert "person@example.com" not in dump and "[REDACTED:EMAIL]" in dump


@pytest.mark.anyio
async def test_audit_failure_rolls_back_mutation(provider,tmp_path):
    db_path=tmp_path/"atomic.db"; server=create_server(db_path=db_path,credential_provider=provider,identity_context=provider.identity_context,fault_injector=FaultInjector("before_audit_insert")); token=provider.issue()
    async with Client(server) as client:
        result=await call(client,provider,token,"tool_register_project",{"name":"rollback","domains":"engineering","caller_instance_id":"agent-a","request_id":"atomic-1"},False)
    assert result["code"]=="INTERNAL_ERROR" and "correlation_id" in result
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM project_registry WHERE name='rollback'").fetchone()[0]==0


@pytest.mark.anyio
async def test_idempotent_retry_does_not_duplicate(server,provider):
    token=provider.issue(); args={"name":"demo","domains":"engineering","caller_instance_id":"agent-a","request_id":"same-1"}
    async with Client(server) as client:
        first=await call(client,provider,token,"tool_register_project",args)
        second=await call(client,provider,token,"tool_register_project",args)
        conflict=await call(client,provider,token,"tool_register_project",{**args,"description":"different"},False)
    assert first==second and conflict["code"]=="CONFLICT"


@pytest.mark.anyio
async def test_all_declared_free_text_is_redacted_at_rest(provider,tmp_path):
    db_path=tmp_path/"all-pii.db"; server=create_server(db_path=db_path,credential_provider=provider,identity_context=provider.identity_context); token=provider.issue(); pii="person@example.com"
    async with Client(server) as client:
        await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","description":pii,"caller_instance_id":"agent-a","request_id":"all-p"})
        await call(client,provider,token,"tool_log_decision",{"project":"demo","title":pii,"decision":pii,"alternatives":pii,"rationale":pii,"tags":pii,"caller_instance_id":"agent-a","request_id":"all-d"})
        await call(client,provider,token,"tool_log_insight",{"project":"demo","title":pii,"insight":pii,"actionable_in":pii,"tags":pii,"caller_instance_id":"agent-a","request_id":"all-i"})
        await call(client,provider,token,"tool_log_outcome",{"project":"demo","task_summary":pii,"result":"fail","root_cause":pii,"prevented_by":pii,"tags":pii,"caller_instance_id":"agent-a","request_id":"all-o"})
        await call(client,provider,token,"tool_log_record",{"project":"demo","record_type":"receipt","title":pii,"content":pii,"tags":pii,"caller_instance_id":"agent-a","request_id":"all-r"})
    with sqlite3.connect(db_path) as db:
        values=[]
        for sql in ("SELECT description FROM project_registry","SELECT title,decision,alternatives,rationale,tags FROM decisions","SELECT title,insight,actionable_in,tags FROM insights","SELECT task_summary,root_cause,prevented_by,tags FROM outcomes","SELECT title,content,tags FROM records"):
            values.extend(str(v) for row in db.execute(sql) for v in row)
        audit_dump=" ".join(str(v) for row in db.execute("SELECT * FROM operations_log") for v in row)
    assert pii not in " ".join(values) and pii not in audit_dump
    assert any("[REDACTED:EMAIL]" in v for v in values)


@pytest.mark.anyio
async def test_audit_schema_is_complete_and_append_only(server,provider,tmp_path):
    token=provider.issue(); db_path=tmp_path/"audit-shape.db"; server=create_server(db_path=db_path,credential_provider=provider,identity_context=provider.identity_context)
    async with Client(server) as client:
        await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","caller_instance_id":"agent-a","request_id":"audit-shape"})
    required={"event_id","occurred_at","principal_subject_id","asserted_subject_id","client_id","role","tool_name","object_type","object_id_or_redacted","result_code","correlation_id","request_id"}
    with sqlite3.connect(db_path) as db:
        columns={row[1] for row in db.execute("PRAGMA table_info(operations_log)")}
        assert required <= columns
        with pytest.raises(sqlite3.DatabaseError): db.execute("DELETE FROM operations_log")
        with pytest.raises(sqlite3.DatabaseError): db.execute("UPDATE operations_log SET result_code='X'")


@pytest.mark.anyio
async def test_wire_rejects_extra_fields_and_bounds(server,provider):
    token=provider.issue(role="reader")
    async with Client(server) as client:
        extra=await call(client,provider,token,"tool_query_log",{"limit":1,"unexpected":"x"},False)
        bound=await call(client,provider,token,"tool_query_log",{"limit":101},False)
    assert extra["code"]=="INVALID_INPUT" and bound["code"]=="INVALID_INPUT"
    assert "unexpected" not in extra.get("message","") and "101" not in bound.get("message","")


@pytest.mark.anyio
@pytest.mark.parametrize("tool,args,path",[
 ("tool_log_insight",{"project":"demo","title":"I","insight":"I"},["validated","archived"]),
 ("tool_log_outcome",{"project":"demo","task_summary":"O","result":"success"},["verified","archived"]),
 ("tool_log_record",{"project":"demo","record_type":"receipt","title":"R","content":"R"},["archived"]),
])
async def test_complete_nondecision_fsms(server,provider,tool,args,path):
    token=provider.issue()
    async with Client(server) as client:
        await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","caller_instance_id":"agent-a","request_id":f"p-{tool}"})
        created=await call(client,provider,token,tool,{**args,"caller_instance_id":"agent-a","request_id":f"c-{tool}"})
        for i,state in enumerate(path):
            changed=await call(client,provider,token,"tool_update_status",{"entry_id":created["id"],"new_status":state,"reason":"synthetic","caller_instance_id":"agent-a","request_id":f"s-{tool}-{i}"})
            assert changed["new_status"]==state
        denied=await call(client,provider,token,"tool_update_status",{"entry_id":created["id"],"new_status":path[0],"caller_instance_id":"agent-a","request_id":f"deny-{tool}"},False)
    assert denied["code"]=="CONFLICT"


@pytest.mark.anyio
async def test_list_encoding_request_id_and_substantive_roundtrip(server,provider):
    token=provider.issue()
    async with Client(server) as client:
        empty=await call(client,provider,token,"tool_register_project",{"name":"x","domains":"a,b","caller_instance_id":"agent-a","request_id":""},False)
        project=await call(client,provider,token,"tool_register_project",{"name":"lists","domains":"engineering, research","caller_instance_id":"agent-a","request_id":"list-project"})
        record=await call(client,provider,token,"tool_log_record",{"project":"lists","record_type":"receipt","title":"Title","content":"Body","references":"[\"REF-1\",\"REF-2\"]","tags":"alpha,beta","caller_instance_id":"agent-a","request_id":"list-record"})
        got=await call(client,provider,token,"tool_get_entry",{"entry_id":record["id"]})
    assert empty["code"]=="INVALID_INPUT" and project["project"]["domains"]==["engineering","research"]
    assert got["entry"]["record_type"]=="receipt" and got["entry"]["title"]=="Title" and got["entry"]["content"]=="Body"
    assert got["entry"]["references"]==["REF-1","REF-2"] and got["entry"]["tags"]==["alpha","beta"]


@pytest.mark.anyio
async def test_startup_tamper_blocks_writes(provider,tmp_path):
    db_path=tmp_path/"tamper.db"; token=provider.issue(); first=create_server(db_path=db_path,credential_provider=provider,identity_context=provider.identity_context)
    async with Client(first) as client:
        await call(client,provider,token,"tool_register_project",{"name":"demo","domains":"engineering","caller_instance_id":"agent-a","request_id":"before-tamper"})
    with sqlite3.connect(db_path) as db: db.execute("DROP TRIGGER operations_log_no_delete")
    restarted=create_server(db_path=db_path,credential_provider=provider,identity_context=provider.identity_context)
    async with Client(restarted) as client:
        denied=await call(client,provider,token,"tool_register_project",{"name":"after","domains":"engineering","caller_instance_id":"agent-a","request_id":"after-tamper"},False)
    assert denied["code"]=="INTERNAL_ERROR"


@pytest.mark.anyio
async def test_frozen_public_tool_names(server):
    expected={"tool_register_project","tool_log_decision","tool_log_insight","tool_log_outcome","tool_log_record","tool_update_status","tool_get_entry","tool_get_context_for","tool_query_log","tool_query_log_fts5"}
    async with Client(server) as client: tools=await client.list_tools()
    assert {tool.name for tool in tools}==expected
