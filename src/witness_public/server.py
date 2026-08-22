"""FastMCP exposure for exactly the ten frozen public tools.

Each tool advertises its normative request schema verbatim from the frozen wire
contract, including ``additionalProperties: false``; the service layer enforces
the same shape and returns the stable error envelope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import Tool
from pydantic import PrivateAttr

from .db import WitnessDatabase
from .service import WitnessService

# Verbatim copies of spec/wire-contract.json -> tools[*].request.
_REQUEST_SCHEMAS: dict[str, dict[str, Any]] = json.loads("""
{
  "tool_register_project": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "name": {
        "type": "string",
        "maxLength": 128
      },
      "domains": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "description": {
        "type": "string",
        "maxLength": 4000
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      },
      "request_id": {
        "type": "string",
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9._:-]+$",
        "normalization": "none; exact ASCII bytes are the idempotency identity"
      }
    },
    "required": [
      "name",
      "domains",
      "caller_instance_id",
      "request_id"
    ]
  },
  "tool_log_decision": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "title": {
        "type": "string",
        "maxLength": 500
      },
      "decision": {
        "type": "string",
        "maxLength": 4000
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      },
      "domain": {
        "type": "string",
        "maxLength": 128
      },
      "scope": {
        "type": "string",
        "default": "macro",
        "maxLength": 64
      },
      "alternatives": {
        "type": "string",
        "maxLength": 4000
      },
      "rationale": {
        "type": "string",
        "maxLength": 4000
      },
      "severity": {
        "type": "string",
        "default": "standard",
        "maxLength": 32
      },
      "pinned": {
        "type": "boolean",
        "default": false
      },
      "based_on": {
        "type": "string",
        "maxLength": 4000,
        "encoding": "csv_or_json_array_v1"
      },
      "decision_ids": {
        "type": "string",
        "maxLength": 4000,
        "encoding": "csv_or_json_array_v1"
      },
      "tags": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "task_id": {
        "type": "string",
        "maxLength": 128
      },
      "impact_level": {
        "type": "string",
        "default": "routine",
        "maxLength": 32
      },
      "request_id": {
        "type": "string",
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9._:-]+$",
        "normalization": "none; exact ASCII bytes are the idempotency identity"
      }
    },
    "required": [
      "project",
      "title",
      "decision",
      "caller_instance_id",
      "request_id"
    ]
  },
  "tool_log_insight": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "title": {
        "type": "string",
        "maxLength": 500
      },
      "insight": {
        "type": "string",
        "maxLength": 4000
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      },
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "applies_to": {
        "type": "string",
        "default": "project",
        "maxLength": 32
      },
      "applies_projects": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "applies_domains": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "actionable_in": {
        "type": "string",
        "maxLength": 2000
      },
      "based_on": {
        "type": "string",
        "maxLength": 4000,
        "encoding": "csv_or_json_array_v1"
      },
      "tags": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "mcp_scope": {
        "type": "string",
        "maxLength": 1000
      },
      "applies_to_mcps": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "impact_level": {
        "type": "string",
        "default": "routine",
        "maxLength": 32
      },
      "request_id": {
        "type": "string",
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9._:-]+$",
        "normalization": "none; exact ASCII bytes are the idempotency identity"
      }
    },
    "required": [
      "title",
      "insight",
      "caller_instance_id",
      "project",
      "request_id"
    ]
  },
  "tool_log_outcome": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "task_summary": {
        "type": "string",
        "maxLength": 4000
      },
      "result": {
        "type": "string",
        "enum": [
          "success",
          "partial",
          "fail"
        ]
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      },
      "domain": {
        "type": "string",
        "maxLength": 128
      },
      "skills_used": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "tools_used": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "workflow_chain": {
        "type": "string",
        "maxLength": 4000
      },
      "duration_planned": {
        "type": "integer",
        "minimum": 0,
        "maximum": 31536000
      },
      "duration_actual": {
        "type": "integer",
        "minimum": 0,
        "maximum": 31536000
      },
      "root_cause": {
        "type": "string",
        "maxLength": 4000
      },
      "root_cause_category": {
        "type": "string",
        "maxLength": 128
      },
      "prevented_by": {
        "type": "string",
        "maxLength": 4000
      },
      "decision_ids": {
        "type": "string",
        "maxLength": 4000,
        "encoding": "csv_or_json_array_v1"
      },
      "based_on": {
        "type": "string",
        "maxLength": 4000,
        "encoding": "csv_or_json_array_v1"
      },
      "quality_score": {
        "type": "number",
        "minimum": -1,
        "maximum": 10
      },
      "execution_quality": {
        "type": "number",
        "minimum": -1,
        "maximum": 10
      },
      "decision_quality": {
        "type": "number",
        "minimum": -1,
        "maximum": 10
      },
      "compliant_with_decisions": {
        "type": "string",
        "maxLength": 2000
      },
      "tokens_input": {
        "type": "integer",
        "minimum": 0
      },
      "tokens_output": {
        "type": "integer",
        "minimum": 0
      },
      "tokens_total": {
        "type": "integer",
        "minimum": 0
      },
      "tags": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "session_id": {
        "type": "string",
        "maxLength": 128
      },
      "task_id": {
        "type": "string",
        "maxLength": 128
      },
      "impact_level": {
        "type": "string",
        "default": "routine",
        "maxLength": 32
      },
      "request_id": {
        "type": "string",
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9._:-]+$",
        "normalization": "none; exact ASCII bytes are the idempotency identity"
      }
    },
    "required": [
      "project",
      "task_summary",
      "result",
      "caller_instance_id",
      "request_id"
    ]
  },
  "tool_log_record": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "record_type": {
        "type": "string",
        "maxLength": 128
      },
      "title": {
        "type": "string",
        "maxLength": 500
      },
      "content": {
        "type": "string",
        "maxLength": 4000
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      },
      "status": {
        "type": "string",
        "default": "active",
        "enum": [
          "active"
        ]
      },
      "based_on": {
        "type": "string",
        "maxLength": 4000,
        "encoding": "csv_or_json_array_v1"
      },
      "tags": {
        "type": "string",
        "maxLength": 2000,
        "encoding": "csv_or_json_array_v1"
      },
      "request_id": {
        "type": "string",
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9._:-]+$",
        "normalization": "none; exact ASCII bytes are the idempotency identity"
      },
      "references": {
        "type": "string",
        "default": "",
        "maxLength": 8000,
        "encoding": "csv_or_json_array_v1"
      }
    },
    "required": [
      "project",
      "record_type",
      "title",
      "content",
      "caller_instance_id",
      "request_id"
    ]
  },
  "tool_update_status": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "entry_id": {
        "type": "string",
        "maxLength": 128
      },
      "new_status": {
        "type": "string",
        "maxLength": 128
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      },
      "reason": {
        "type": "string",
        "maxLength": 4000
      },
      "request_id": {
        "type": "string",
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[A-Za-z0-9._:-]+$",
        "normalization": "none; exact ASCII bytes are the idempotency identity"
      }
    },
    "required": [
      "entry_id",
      "new_status",
      "caller_instance_id",
      "request_id"
    ]
  },
  "tool_get_entry": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "entry_id": {
        "type": "string",
        "maxLength": 128
      }
    },
    "required": [
      "entry_id"
    ]
  },
  "tool_get_context_for": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "domain": {
        "type": "string",
        "maxLength": 128
      },
      "scope": {
        "type": "string",
        "maxLength": 128
      },
      "max_items": {
        "type": "integer",
        "default": 20,
        "minimum": 1,
        "maximum": 100
      }
    },
    "required": [
      "project"
    ]
  },
  "tool_query_log": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "type": {
        "type": "string",
        "maxLength": 128
      },
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "domain": {
        "type": "string",
        "maxLength": 128
      },
      "status": {
        "type": "string",
        "maxLength": 128
      },
      "confidence": {
        "type": "string",
        "maxLength": 128
      },
      "result": {
        "type": "string",
        "maxLength": 128
      },
      "search": {
        "type": "string",
        "maxLength": 500
      },
      "period": {
        "type": "string",
        "maxLength": 128
      },
      "tags": {
        "type": "string",
        "maxLength": 1000,
        "encoding": "csv_or_json_array_v1"
      },
      "limit": {
        "type": "integer",
        "default": 20,
        "minimum": 1,
        "maximum": 100
      },
      "offset": {
        "type": "integer",
        "default": 0,
        "minimum": 0,
        "maximum": 100000
      }
    },
    "required": []
  },
  "tool_query_log_fts5": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "query": {
        "type": "string",
        "maxLength": 500
      },
      "project": {
        "type": "string",
        "maxLength": 128
      },
      "max_items": {
        "type": "integer",
        "default": 3,
        "minimum": 1,
        "maximum": 50
      },
      "include_types": {
        "type": "string",
        "maxLength": 500,
        "encoding": "csv_or_json_array_v1"
      },
      "global_cap": {
        "type": "integer",
        "default": 0,
        "minimum": 0,
        "maximum": 200
      },
      "caller_instance_id": {
        "type": "string",
        "maxLength": 128
      }
    },
    "required": [
      "query",
      "caller_instance_id"
    ]
  }
}
""")

# FastMCP must admit the envelope into the service's fail-closed validator so
# malformed/missing identity receives the stable public error envelope instead
# of an adapter-specific schema exception. The service still requires it for
# every dispatch; Phase 4 verifies advertised-schema parity separately.
_IDENTITY_ENVELOPE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "version": {"type": "string"},
        "principal_pubkey": {"type": "string"},
        "owner_pubkey": {"type": "string"},
        "owner_attestation": {"type": "object"},
        "profile_id": {"type": "string"},
        "profile_version_sha256": {"type": "string"},
        "tenant_id": {"type": "string"},
        "runtime_generation": {"type": "string"},
        "tool_name": {"type": "string"},
        "payload_sha256": {"type": "string"},
        "nonce": {"type": "string"},
        "issued_at": {"type": "integer"},
        "expires_at": {"type": "integer"},
        "signature": {"type": "string"},
    },
}
# The wire contract is projected into a package-local, fully dereferenced schema
# artifact.  The parity acceptance test prevents this projection from drifting.
_REQUEST_SCHEMAS = json.loads(
    Path(__file__).with_name("request-schemas.json").read_text(encoding="utf-8")
)
_TOOL_NAMES = tuple(_REQUEST_SCHEMAS)


class _DispatchTool(Tool):
    _service: WitnessService = PrivateAttr()

    def __init__(self, name: str, service: WitnessService):
        super().__init__(
            name=name,
            description="Witness public-core operation.",
            parameters=_REQUEST_SCHEMAS[name],
        )
        self._service = service

    async def run(self, arguments: dict[str, Any]):
        return self.convert_result(self._service.dispatch(self.name, arguments))


def create_server(*, db_path: str | Path, credential_provider: Any,
                  identity_context=None, fault_injector=None) -> FastMCP:
    database = WitnessDatabase(db_path, fault_injector=fault_injector)
    service = WitnessService(database, credential_provider, identity_context)
    server = FastMCP("Witness", mask_error_details=True)
    for name in _TOOL_NAMES:
        server.add_tool(_DispatchTool(name, service))
    return server
