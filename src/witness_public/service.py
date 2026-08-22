"""Contract-focused service layer for the Witness public core.

Field parsing, bound checking, privacy classification and persistence are driven
by one declarative table (`_SPECS`) that mirrors the frozen wire contract, so a
declared field cannot be silently accepted-and-dropped by a hand-written handler.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
import sqlite3
from typing import Any, Callable
from uuid import uuid4

from .auth import Principal, resolve_principal
from .db import AUDIT_COLUMNS, WitnessDatabase
from .identity import IdentityError, VerificationContext, VerifiedIdentity, verify_envelope
from .privacy import redact

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]+$")
_PERIOD = re.compile(r"all|today|(\d{1,6})([hdw])")
_KINDS = ("decision", "insight", "outcome", "record")
_ROLES = {
    "reader": {"tool_get_entry", "tool_get_context_for", "tool_query_log", "tool_query_log_fts5"},
    "writer": {"tool_get_entry", "tool_get_context_for", "tool_query_log", "tool_query_log_fts5", "tool_log_decision", "tool_log_insight", "tool_log_outcome", "tool_log_record"},
    "admin": {"tool_get_entry", "tool_get_context_for", "tool_query_log", "tool_query_log_fts5", "tool_log_decision", "tool_log_insight", "tool_log_outcome", "tool_log_record", "tool_register_project", "tool_update_status"},
}


class PublicError(Exception):
    def __init__(self, code: str, message: str, event_type: str | None = None):
        self.code, self.message, self.event_type = code, message, event_type


class _F:
    """One declared wire field: kind, declared bounds, default and privacy class.

    `maximum` is maxLength for text/list fields and the numeric maximum for
    int/number fields. `pii` marks a field the privacy contract treats as
    potential PII; operational identifiers and closed enums are left verbatim so
    they stay usable as filter keys.
    """

    __slots__ = ("kind", "required", "default", "maximum", "minimum", "max_items", "min_length", "pattern", "enum", "pii")

    def __init__(self, kind: str, *, maximum: Any = None, minimum: Any = None, required: bool = False,
                 default: Any = None, max_items: int = 100, min_length: int = 0,
                 pattern: re.Pattern[str] | None = None, enum: frozenset[str] | None = None, pii: bool = False):
        self.kind, self.maximum, self.minimum, self.required = kind, maximum, minimum, required
        self.default, self.max_items, self.min_length = default, max_items, min_length
        self.pattern, self.enum, self.pii = pattern, enum, pii


_REQ = _F("text", maximum=128, min_length=1, pattern=_REQUEST_ID, required=True)
_CALLER = _F("text", maximum=128, required=True)

_SPECS: dict[str, dict[str, _F]] = {
    "tool_register_project": {
        "name": _F("text", maximum=128, required=True),
        "domains": _F("list", maximum=2000, max_items=50, required=True),
        "description": _F("text", maximum=4000, default="", pii=True),
        "caller_instance_id": _CALLER,
        "request_id": _REQ,
    },
    "tool_log_decision": {
        "project": _F("text", maximum=128, required=True),
        "title": _F("text", maximum=500, required=True, pii=True),
        "decision": _F("text", maximum=4000, required=True, pii=True),
        "caller_instance_id": _CALLER,
        "domain": _F("text", maximum=128, default=""),
        "scope": _F("text", maximum=64, default="macro"),
        "alternatives": _F("list", maximum=4000, default=(), pii=True),
        "rationale": _F("text", maximum=4000, default="", pii=True),
        "severity": _F("text", maximum=32, default="standard"),
        "pinned": _F("bool", default=False),
        "based_on": _F("list", maximum=4000, default=(), pii=True),
        "decision_ids": _F("list", maximum=4000, default=(), pii=True),
        "tags": _F("list", maximum=2000, default=(), pii=True),
        "task_id": _F("text", maximum=128, default=""),
        "impact_level": _F("text", maximum=32, default="routine"),
        "request_id": _REQ,
    },
    "tool_log_insight": {
        "title": _F("text", maximum=500, required=True, pii=True),
        "insight": _F("text", maximum=4000, required=True, pii=True),
        "caller_instance_id": _CALLER,
        "project": _F("text", maximum=128, required=True),
        "applies_to": _F("text", maximum=32, default="project"),
        "applies_projects": _F("list", maximum=2000, default=()),
        "applies_domains": _F("list", maximum=2000, default=()),
        "actionable_in": _F("list", maximum=2000, default=(), pii=True),
        "based_on": _F("list", maximum=4000, default=(), pii=True),
        "tags": _F("list", maximum=2000, default=(), pii=True),
        "mcp_scope": _F("text", maximum=1000, default="", pii=True),
        "applies_to_mcps": _F("list", maximum=2000, default=()),
        "impact_level": _F("text", maximum=32, default="routine"),
        "request_id": _REQ,
    },
    "tool_log_outcome": {
        "project": _F("text", maximum=128, required=True),
        "task_summary": _F("text", maximum=4000, required=True, pii=True),
        "result": _F("text", maximum=128, required=True, enum=frozenset({"success", "partial", "fail"})),
        "caller_instance_id": _CALLER,
        "domain": _F("text", maximum=128, default=""),
        "skills_used": _F("list", maximum=2000, default=(), pii=True),
        "tools_used": _F("list", maximum=2000, default=(), pii=True),
        "workflow_chain": _F("text", maximum=4000, default="", pii=True),
        "duration_planned": _F("int", minimum=0, maximum=31536000),
        "duration_actual": _F("int", minimum=0, maximum=31536000),
        "root_cause": _F("text", maximum=4000, default="", pii=True),
        "root_cause_category": _F("text", maximum=128, default="", pii=True),
        "prevented_by": _F("list", maximum=4000, default=(), pii=True),
        "decision_ids": _F("list", maximum=4000, default=(), pii=True),
        "based_on": _F("list", maximum=4000, default=(), pii=True),
        "quality_score": _F("number", minimum=-1, maximum=10),
        "execution_quality": _F("number", minimum=-1, maximum=10),
        "decision_quality": _F("number", minimum=-1, maximum=10),
        "compliant_with_decisions": _F("text", maximum=2000, default="", pii=True),
        "tokens_input": _F("int", minimum=0),
        "tokens_output": _F("int", minimum=0),
        "tokens_total": _F("int", minimum=0),
        "tags": _F("list", maximum=2000, default=(), pii=True),
        "session_id": _F("text", maximum=128, default=""),
        "task_id": _F("text", maximum=128, default=""),
        "impact_level": _F("text", maximum=32, default="routine"),
        "request_id": _REQ,
    },
    "tool_log_record": {
        "project": _F("text", maximum=128, required=True),
        "record_type": _F("text", maximum=128, required=True),
        "title": _F("text", maximum=500, required=True, pii=True),
        "content": _F("text", maximum=4000, required=True, pii=True),
        "caller_instance_id": _CALLER,
        "status": _F("text", maximum=128, default="active", enum=frozenset({"active"})),
        "based_on": _F("list", maximum=4000, default=(), pii=True),
        "tags": _F("list", maximum=2000, default=(), pii=True),
        "request_id": _REQ,
        "references": _F("list", maximum=8000, default=(), pii=True),
    },
    "tool_update_status": {
        "entry_id": _F("text", maximum=128, required=True),
        "new_status": _F("text", maximum=128, required=True),
        "caller_instance_id": _CALLER,
        "reason": _F("text", maximum=4000, default="", pii=True),
        "request_id": _REQ,
    },
    "tool_get_entry": {"entry_id": _F("text", maximum=128, required=True)},
    "tool_get_context_for": {
        "project": _F("text", maximum=128, required=True),
        "domain": _F("text", maximum=128),
        "scope": _F("text", maximum=128),
        "max_items": _F("int", minimum=1, maximum=100, default=20),
    },
    "tool_query_log": {
        "type": _F("text", maximum=128),
        "project": _F("text", maximum=128),
        "domain": _F("text", maximum=128),
        "status": _F("text", maximum=128),
        "confidence": _F("text", maximum=128),
        "result": _F("text", maximum=128),
        "search": _F("text", maximum=500),
        "period": _F("text", maximum=128),
        "tags": _F("list", maximum=1000),
        "limit": _F("int", minimum=1, maximum=100, default=20),
        "offset": _F("int", minimum=0, maximum=100000, default=0),
    },
    "tool_query_log_fts5": {
        "query": _F("text", maximum=500, required=True),
        "project": _F("text", maximum=128),
        "max_items": _F("int", minimum=1, maximum=50, default=3),
        "include_types": _F("list", maximum=500, max_items=4),
        "global_cap": _F("int", minimum=0, maximum=200, default=0),
        "caller_instance_id": _CALLER,
    },
}
_MUTATIONS = {"tool_register_project", "tool_log_decision", "tool_log_insight", "tool_log_outcome", "tool_log_record", "tool_update_status"}
# tool -> (audit event, audited object type, object identifier)
_READS = {
    "tool_get_entry": ("read", "entry", "entry_id"),
    "tool_get_context_for": ("read", "project", "project"),
    "tool_query_log": ("read", "query", None),
    "tool_query_log_fts5": ("search", "search", None),
}

_TABLES = {"decision": "decisions", "insight": "insights", "outcome": "outcomes", "record": "records"}
# Columns a type actually declares; a filter on a column a type lacks cannot match.
_TYPE_COLUMNS = {"decision": {"domain", "scope"}, "insight": {"confidence"}, "outcome": {"domain", "result"}, "record": set()}
_SEARCH_COLUMNS = {
    "decision": ("title", "decision", "rationale", "alternatives", "tags"),
    "insight": ("title", "insight", "actionable_in", "tags"),
    "outcome": ("task_summary", "root_cause", "prevented_by", "tags"),
    "record": ("title", "content", "tags"),
}
# Response projections are exactly the frozen definitions (additionalProperties:false).
_PROJECTION = {
    "decision": ("id", "project", "created_at", "actor_subject_id", "status", "title", "decision", "domain", "alternatives", "rationale", "based_on", "tags"),
    "insight": ("id", "project", "created_at", "actor_subject_id", "status", "title", "insight", "confidence", "actionable_in", "tags"),
    "outcome": ("id", "project", "created_at", "actor_subject_id", "status", "task_summary", "result", "root_cause", "prevented_by", "tags"),
    "record": ("id", "project", "created_at", "actor_subject_id", "status", "record_type", "title", "content", "references", "tags"),
}
_LIST_PROJECTIONS = {"alternatives", "based_on", "tags", "actionable_in", "prevented_by", "references"}
_PERSISTED = {
    "decision": ("project", "title", "decision", "domain", "scope", "alternatives", "rationale", "severity", "pinned", "based_on", "decision_ids", "tags", "task_id", "impact_level"),
    "insight": ("project", "title", "insight", "applies_to", "applies_projects", "applies_domains", "actionable_in", "based_on", "tags", "mcp_scope", "applies_to_mcps", "impact_level"),
    "outcome": ("project", "task_summary", "result", "domain", "skills_used", "tools_used", "workflow_chain", "duration_planned", "duration_actual", "root_cause", "root_cause_category", "prevented_by", "decision_ids", "based_on", "quality_score", "execution_quality", "decision_quality", "compliant_with_decisions", "tokens_input", "tokens_output", "tokens_total", "tags", "session_id", "task_id", "impact_level"),
    "record": ("project", "record_type", "title", "content", "based_on", "tags"),
}
_INITIAL_STATUS = {"decision": "proposed", "insight": "hypothesis", "outcome": "recorded"}
_TRANSITIONS = {
    "decision": {("proposed", "locked"), ("proposed", "archived"), ("locked", "superseded"), ("locked", "archived")},
    "insight": {("hypothesis", "validated"), ("hypothesis", "invalidated"), ("validated", "archived"), ("invalidated", "archived")},
    "outcome": {("recorded", "verified"), ("recorded", "disputed"), ("verified", "archived"), ("disputed", "archived")},
    "record": {("active", "archived")},
}


def _invalid(field: str) -> PublicError:
    """Field name and validation code only; never the rejected value."""
    return PublicError("INVALID_INPUT", f"Field '{field}' failed validation.")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _canonical_string(value: str) -> str:
    escapes = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    out = ['"']
    for char in value:
        out.append(escapes.get(char) or (f"\\u{ord(char):04x}" if char < " " else char))
    return "".join(out) + '"'


def _canonical_number(value: int | float) -> str:
    """Serialize integers exactly and finite floats with ECMAScript thresholds.

    Python integers are unbounded and several public token fields intentionally
    accept that domain, so converting them through IEEE-754 would collapse or
    overflow valid identities. Floats retain the RFC 8785/ECMAScript layout.
    """
    if isinstance(value, int):
        return str(value)

    number = float(value)
    if not math.isfinite(number):
        raise PublicError("INVALID_INPUT", "A numeric field is not finite.")
    if number == 0:
        return "0"

    negative = number < 0
    text = repr(abs(number)).lower()
    if "e" in text:
        coefficient, exponent_text = text.split("e", 1)
        exponent = int(exponent_text)
        digits = coefficient.replace(".", "")
        decimal_point = 1 + exponent
    else:
        integer, dot, fraction = text.partition(".")
        if fraction == "0":
            fraction = ""
        digits = integer + fraction
        decimal_point = len(integer)

    magnitude = abs(number)
    if 1e-6 <= magnitude < 1e21:
        if decimal_point <= 0:
            canonical = "0." + ("0" * -decimal_point) + digits
        elif decimal_point >= len(digits):
            canonical = digits + ("0" * (decimal_point - len(digits)))
        else:
            canonical = digits[:decimal_point] + "." + digits[decimal_point:]
    else:
        exponent = decimal_point - 1
        coefficient = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
        canonical = coefficient + "e" + ("+" if exponent >= 0 else "-") + str(abs(exponent))
    return ("-" if negative else "") + canonical


def _canonical(value: Any) -> str:
    """RFC 8785-equivalent JSON canonicalisation of a JSON value.

    Unbounded Python integers retain exact identity; floats use ES6 double
    canonicalisation, so 1 and 1.0 remain one identity. Non-finite floats fail.
    """
    if value is None:
        return "null"
    if value is True or value is False:
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, str):
        return _canonical_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise PublicError("INVALID_INPUT", "The request shape is invalid.")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_canonical_string(key)}:{_canonical(value[key])}" for key in keys) + "}"
    raise PublicError("INVALID_INPUT", "The request shape is invalid.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_start(value: str) -> str:
    match = _PERIOD.fullmatch(value)
    if match is None:
        raise _invalid("period")
    if value == "all":
        return ""
    now = datetime.now(timezone.utc)
    if value == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    amount, unit = int(match.group(1)), match.group(2)
    return (now - {"h": timedelta(hours=amount), "d": timedelta(days=amount), "w": timedelta(weeks=amount)}[unit]).isoformat()


def _decode_list(field: str, value: str, maximum: int) -> list[str]:
    """csv_or_json_array_v1: JSON array of strings, or comma separated tokens."""
    if value == "":
        return []
    if value.lstrip().startswith("["):
        try:
            parsed = json.loads(value)
        except ValueError as exc:
            raise _invalid(field) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise _invalid(field)
        items = [item.strip() for item in parsed]
    else:
        items = [item.strip() for item in value.split(",")]
    if len(items) > maximum or any(not item for item in items) or len(set(items)) != len(items):
        raise _invalid(field)
    return items


def _validate(field: str, spec: _F, value: Any) -> Any:
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise _invalid(field)
        return value
    if spec.kind in ("int", "number"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _invalid(field)
        if isinstance(value, float):
            if not math.isfinite(value):
                raise _invalid(field)
            if spec.kind == "int":
                if not value.is_integer():
                    raise _invalid(field)
                value = int(value)
        if (spec.minimum is not None and value < spec.minimum) or (spec.maximum is not None and value > spec.maximum):
            raise _invalid(field)
        return value
    if not isinstance(value, str):
        raise _invalid(field)
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise _invalid(field) from exc
    if len(value) > spec.maximum or len(value) < spec.min_length:
        raise _invalid(field)
    if spec.pattern is not None and not spec.pattern.fullmatch(value):
        raise _invalid(field)
    if spec.enum is not None and value not in spec.enum:
        raise _invalid(field)
    if spec.kind == "list":
        return _decode_list(field, value, spec.max_items)
    return value


def _parse(spec: dict[str, _F], args: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, declared in spec.items():
        if field not in args:
            if declared.required:
                raise PublicError("INVALID_INPUT", f"Required field '{field}' is missing.")
            values[field] = list(declared.default) if isinstance(declared.default, tuple) else declared.default
            continue
        parsed = _validate(field, declared, args[field])
        # The privacy contract treats every accepted string leaf as potential PII.
        # Only a closed enum or a full-match operational-identifier pattern proves
        # that a field can safely bypass content scanning; the legacy `pii` marker
        # remains descriptive, not the gate that decides whether scanning occurs.
        classified_operational = declared.enum is not None or declared.pattern is not None
        values[field] = parsed if classified_operational else redact(parsed)
    return values


_SQLITE_INTEGER_MIN = -(2**63)
_SQLITE_INTEGER_MAX = 2**63 - 1
_LOSSLESS_INTEGER_FIELDS = {"tokens_input", "tokens_output", "tokens_total"}


def _encode(field: str, value: Any) -> Any:
    if isinstance(value, list):
        return _json(value)
    if isinstance(value, bool):
        return int(value)
    if (
        field in _LOSSLESS_INTEGER_FIELDS
        and isinstance(value, int)
        and not _SQLITE_INTEGER_MIN <= value <= _SQLITE_INTEGER_MAX
    ):
        # SQLite INTEGER is signed 64-bit. The frozen wire contract deliberately
        # leaves token counts unbounded, so preserve larger schema-valid values as
        # tagged decimal text rather than coercing them to an imprecise REAL.
        return f"integer:{value}"
    return value


def _insert(db: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = ",".join(row)
    db.execute(
        f"INSERT INTO {table}({columns}) VALUES ({','.join('?' for _ in row)})",
        [_encode(field, value) for field, value in row.items()],
    )


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _filters(kind: str, values: dict[str, Any], names: tuple[str, ...]) -> tuple[list[str], list[Any]] | None:
    """Build the WHERE fragment, or None when this type cannot satisfy a filter."""
    clauses: list[str] = []
    params: list[Any] = []
    for name in names:
        value = values.get(name)
        if value is None or value == "" or value == []:
            continue
        if name in ("project", "status"):
            clauses.append(f"{name}=?")
            params.append(value)
        elif name in ("domain", "scope", "result"):
            if name not in _TYPE_COLUMNS[kind]:
                return None
            clauses.append(f"{name}=?")
            params.append(value)
        elif name == "confidence":
            if "confidence" not in _TYPE_COLUMNS[kind]:
                return None
            try:
                number = float(value)
            except ValueError:
                return None
            clauses.append("confidence=?")
            params.append(number)
        elif name == "period":
            clauses.append("created_at>=?")
            params.append(_period_start(value))
        elif name == "tags":
            for tag in value:
                clauses.append("EXISTS(SELECT 1 FROM json_each(tags) WHERE json_each.value=?)")
                params.append(tag)
        elif name == "search":
            columns = _SEARCH_COLUMNS[kind]
            clauses.append("(" + " OR ".join(f"{column} LIKE ? ESCAPE '\\'" for column in columns) + ")")
            params.extend([_like(value)] * len(columns))
    return clauses, params


class WitnessService:
    def __init__(self, db: WitnessDatabase, credential_provider: Any,
                 identity_context: VerificationContext | Callable[[], VerificationContext] | None = None):
        self.db = db
        self.credential_provider = credential_provider
        self.identity_context = identity_context

    def dispatch(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        correlation_id = str(uuid4())
        safe_tool = tool if tool in _SPECS else "[REDACTED]"
        principal: Principal | None = None
        verified: VerifiedIdentity | None = None
        payload = {key: value for key, value in args.items() if key != "identity_envelope"}
        try:
            if tool not in _SPECS or set(payload) - set(_SPECS[tool]):
                raise PublicError("INVALID_INPUT", "The request shape is invalid.")
            context = self.identity_context() if callable(self.identity_context) else self.identity_context
            if context is None or args.get("identity_envelope") is None:
                raise IdentityError("AUTHENTICATION_REQUIRED")
            verified = verify_envelope(args.get("identity_envelope"), tool, payload, context)
        except IdentityError as exc:
            self._audit(None, "authentication_failure", safe_tool, "none", "[REDACTED]", exc.code, correlation_id)
            return self._error(exc.code, correlation_id, "The signed identity envelope was rejected.")
        except PublicError as exc:
            return self._error(exc.code, correlation_id, exc.message)
        try:
            principal = resolve_principal(self.credential_provider)
        except ValueError:
            self._audit(None, "authentication_failure", safe_tool, "none", "[REDACTED]", "AUTHENTICATION_REQUIRED", correlation_id)
            return self._error("AUTHENTICATION_REQUIRED", correlation_id, "Authentication is required.")
        try:
            spec = _SPECS[tool]
            if principal.subject_id != verified.principal_pubkey:
                self._audit(principal, "identity_mismatch", safe_tool, "none", "[REDACTED]", "IDENTITY_MISMATCH", correlation_id, asserted="[REDACTED]", identity=verified)
                return self._error("IDENTITY_MISMATCH", correlation_id, "The authenticated transport principal does not match the request signer.")
            if "caller_instance_id" in spec:
                asserted = payload.get("caller_instance_id")
                if not isinstance(asserted, str) or asserted != principal.subject_id:
                    raise PublicError("IDENTITY_MISMATCH", "The caller assertion does not match.", "identity_mismatch")
            if tool not in _ROLES[principal.role]:
                raise PublicError("PERMISSION_DENIED", "The principal cannot use this tool.", "authorization_denial")
            if tool in _MUTATIONS and self.db.tampered:
                raise PublicError("INTERNAL_ERROR", "The operation could not be completed.")
            values = _parse(spec, payload)
            values["_identity"] = verified
            response = getattr(self, tool.removeprefix("tool_"))(principal, values, payload, correlation_id)
            if tool in _READS:
                event, object_type, identifier = _READS[tool]
                self._audit(principal, event, tool, object_type, values[identifier] if identifier else "[REDACTED]", "OK", correlation_id, identity=verified)
            return response
        except PublicError as exc:
            if exc.event_type:
                self._audit(principal, exc.event_type, safe_tool, "none", "[REDACTED]", exc.code, correlation_id, asserted="[REDACTED]", identity=verified)
            return self._error(exc.code, correlation_id, exc.message)
        except Exception:
            return self._error("INTERNAL_ERROR", correlation_id, "The operation could not be completed.")

    @staticmethod
    def _error(code: str, correlation_id: str, message: str) -> dict[str, Any]:
        return {"status": "error", "correlation_id": correlation_id, "code": code, "message": message}

    def _audit(self, principal: Principal | None, event_type: str, tool: str, object_type: str,
               object_id: str, result_code: str, correlation_id: str, request_id: str = "",
               *, asserted: str | None = None, db: sqlite3.Connection | None = None,
               identity: VerifiedIdentity | None = None, payload_sha256: str = "") -> None:
        """Append one operations_log event; never stores content, query text or claims."""
        if self.db.tampered:  # read-only tamper mode: the audit table cannot be trusted
            return
        row = (
            str(uuid4()), _now(),
            principal.subject_id if principal else "[REDACTED]",
            asserted if asserted is not None else (principal.subject_id if principal else "[REDACTED]"),
            principal.client_id if principal else "[REDACTED]",
            principal.role if principal else "[REDACTED]",
            tool, object_type, object_id, result_code, correlation_id, request_id, event_type,
            identity.principal_pubkey if identity else "[REDACTED]",
            identity.owner_pubkey if identity else "[REDACTED]",
            identity.profile_id if identity else "[REDACTED]",
            identity.profile_version_sha256 if identity else "[REDACTED]",
            identity.tenant_id if identity else "[REDACTED]",
            identity.runtime_generation if identity else "[REDACTED]",
            identity.nonce if identity else "[REDACTED]",
            (payload_sha256 or identity.payload_sha256) if identity else "[REDACTED]",
        )
        sql = f"INSERT INTO operations_log({','.join(AUDIT_COLUMNS)}) VALUES ({','.join('?' for _ in AUDIT_COLUMNS)})"
        if db is not None:
            db.execute(sql, row)
            return
        try:
            with self.db.session() as connection:
                connection.execute(sql, row)
                connection.commit()
        except sqlite3.Error:  # a failed security-event append must not leak detail
            pass

    def _mutate(self, principal: Principal, tool: str, args: dict[str, Any], correlation_id: str,
                identity: VerifiedIdentity,
                action: Callable[[sqlite3.Connection], tuple[dict[str, Any], str, str, str]]) -> dict[str, Any]:
        payload_hash = hashlib.sha256(_canonical(args).encode("utf-8")).hexdigest()
        request_id = args["request_id"]
        db = self.db.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT payload_hash,response_json FROM idempotency WHERE subject_id=? AND tool_name=? AND request_id=?",
                (principal.subject_id, tool, request_id),
            ).fetchone()
            if prior:
                if prior["payload_hash"] != payload_hash:
                    raise PublicError("CONFLICT", "The idempotency key was reused with different input.")
                db.rollback()
                return json.loads(prior["response_json"])
            response, object_id, object_type, event_type = action(db)
            self.db.inject("before_audit_insert")
            self._audit(principal, event_type, tool, object_type, object_id, "OK", correlation_id, request_id,
                        asserted=args.get("caller_instance_id", ""), db=db, identity=identity,
                        payload_sha256=hashlib.sha256(_canonical(args).encode("utf-8")).hexdigest())
            db.execute(
                "INSERT INTO idempotency VALUES (?,?,?,?,?)",
                (principal.subject_id, tool, request_id, payload_hash, _json(response)),
            )
            db.commit()
            return response
        except PublicError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise PublicError("INTERNAL_ERROR", "The operation could not be completed.") from exc
        finally:
            db.close()

    # ----- mutations -------------------------------------------------------
    def register_project(self, principal: Principal, values: dict[str, Any], args: dict[str, Any], cid: str) -> dict[str, Any]:
        name, domains, description = values["name"], values["domains"], values["description"]

        def action(db: sqlite3.Connection):
            db.execute(
                "INSERT INTO project_registry(name,domains,description) VALUES (?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET domains=excluded.domains,description=excluded.description",
                (name, _json(domains), description),
            )
            project = {"name": name, "domains": domains, "description": description}
            return {"status": "ok", "correlation_id": cid, "project": project}, name, "project", "administrative_change"

        return self._mutate(principal, "tool_register_project", args, cid, values["_identity"], action)

    def _append(self, principal: Principal, kind: str, values: dict[str, Any], args: dict[str, Any], cid: str,
                extra: dict[str, Any], indexed: tuple[str, ...]) -> dict[str, Any]:
        entry_id, created = f"{kind}-{uuid4()}", _now()

        def action(db: sqlite3.Connection):
            if db.execute("SELECT 1 FROM project_registry WHERE name=?", (values["project"],)).fetchone() is None:
                raise PublicError("NOT_FOUND", "The requested object was not found.")
            row = {"id": entry_id, "status": values.get("status") or _INITIAL_STATUS[kind]}
            row.update({name: values[name] for name in _PERSISTED[kind]})
            row.update(extra)
            row.update({"created_at": created, "actor_subject_id": principal.subject_id})
            _insert(db, _TABLES[kind], row)
            text = " ".join(_json(values[name]) if isinstance(values[name], list) else str(values[name]) for name in indexed)
            db.execute("INSERT INTO entry_fts(entry_id,entry_type,project,text) VALUES (?,?,?,?)", (entry_id, kind, values["project"], text))
            return {"status": "ok", "correlation_id": cid, "id": entry_id, "type": kind}, entry_id, kind, "create"

        return self._mutate(principal, f"tool_log_{kind}", args, cid, values["_identity"], action)

    def log_decision(self, principal, values, args, cid):
        return self._append(principal, "decision", values, args, cid, {}, ("title", "decision", "rationale", "alternatives", "tags"))

    def log_insight(self, principal, values, args, cid):
        return self._append(principal, "insight", values, args, cid, {"confidence": -1.0}, ("title", "insight", "actionable_in", "tags"))

    def log_outcome(self, principal, values, args, cid):
        return self._append(principal, "outcome", values, args, cid, {}, ("task_summary", "root_cause", "prevented_by", "tags"))

    def log_record(self, principal, values, args, cid):
        return self._append(principal, "record", values, args, cid, {"references_json": values["references"]}, ("title", "content", "references", "tags"))

    def update_status(self, principal: Principal, values: dict[str, Any], args: dict[str, Any], cid: str) -> dict[str, Any]:
        entry_id, new_status, reason = values["entry_id"], values["new_status"], values["reason"]

        def action(db: sqlite3.Connection):
            found = self._find_row(db, entry_id)
            if found is None:
                raise PublicError("NOT_FOUND", "The requested object was not found.")
            kind, table, row = found
            if (row["status"], new_status) not in _TRANSITIONS[kind]:
                raise PublicError("CONFLICT", "The lifecycle transition is not allowed.")
            db.execute(f"UPDATE {table} SET status=? WHERE id=? AND status=?", (new_status, entry_id, row["status"]))
            db.execute(
                "INSERT INTO status_changes(entry_id,old_status,new_status,reason,occurred_at,actor_subject_id) VALUES (?,?,?,?,?,?)",
                (entry_id, row["status"], new_status, reason, _now(), principal.subject_id),
            )
            # Additive draft response field: the lifecycle client needs the state
            # it just established, and the strict wire response requires it.
            response = {"status": "ok", "correlation_id": cid, "id": entry_id, "type": kind, "new_status": new_status}
            return response, entry_id, kind, "status_transition"

        return self._mutate(principal, "tool_update_status", args, cid, values["_identity"], action)

    # ----- reads -----------------------------------------------------------
    @staticmethod
    def _find_row(db: sqlite3.Connection, entry_id: str):
        for kind, table in _TABLES.items():
            row = db.execute(f"SELECT * FROM {table} WHERE id=?", (entry_id,)).fetchone()
            if row is not None:
                return kind, table, row
        return None

    @staticmethod
    def _entry(kind: str, row: sqlite3.Row) -> dict[str, Any]:
        entry: dict[str, Any] = {"type": kind}
        for name in _PROJECTION[kind]:
            value = row["references_json" if name == "references" else name]
            entry[name] = json.loads(value) if name in _LIST_PROJECTIONS else value
        return entry

    def get_entry(self, principal: Principal, values: dict[str, Any], args: dict[str, Any], cid: str) -> dict[str, Any]:
        with self.db.session() as db:
            found = self._find_row(db, values["entry_id"])
            if found is None:
                raise PublicError("NOT_FOUND", "The requested object was not found.")
            return {"status": "ok", "correlation_id": cid, "entry": self._entry(found[0], found[2])}

    def get_context_for(self, principal: Principal, values: dict[str, Any], args: dict[str, Any], cid: str) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "ok", "correlation_id": cid}
        with self.db.session() as db:
            if db.execute("SELECT 1 FROM project_registry WHERE name=?", (values["project"],)).fetchone() is None:
                raise PublicError("NOT_FOUND", "The requested object was not found.")
            for kind, table in _TABLES.items():
                built = _filters(kind, values, ("project", "domain", "scope"))
                if built is None:
                    result[f"{kind}s"] = []
                    continue
                clauses, params = built
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                rows = db.execute(f"SELECT * FROM {table}{where} ORDER BY created_at DESC LIMIT ?", [*params, values["max_items"]]).fetchall()
                result[f"{kind}s"] = [self._entry(kind, row) for row in rows]
        return result

    def query_log(self, principal: Principal, values: dict[str, Any], args: dict[str, Any], cid: str) -> dict[str, Any]:
        limit, offset, requested = values["limit"], values["offset"], values["type"]
        items: list[dict[str, Any]] = []
        with self.db.session() as db:
            for kind, table in _TABLES.items():
                if requested and requested != kind:
                    continue
                built = _filters(kind, values, ("project", "status", "domain", "confidence", "result", "period", "tags", "search"))
                if built is None:
                    continue
                clauses, params = built
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                rows = db.execute(f"SELECT * FROM {table}{where} ORDER BY created_at DESC", params).fetchall()
                items.extend(self._entry(kind, row) for row in rows)
        items.sort(key=lambda item: item["created_at"], reverse=True)
        page = items[offset:offset + limit]
        return {"status": "ok", "correlation_id": cid, "items": page, "limit": limit, "offset": offset, "next_offset": offset + len(page)}

    def query_log_fts5(self, principal: Principal, values: dict[str, Any], args: dict[str, Any], cid: str) -> dict[str, Any]:
        query = values["query"].strip()
        include = values["include_types"] or []
        if any(kind not in _KINDS for kind in include):
            raise _invalid("include_types")
        if not query:  # an empty pattern matches nothing; it is not an error
            return {"status": "ok", "correlation_id": cid, "items": []}
        # ponytail: max_items bounds each type, global_cap (when set) bounds the merged
        # result; raise to per-project scoring only if ranking quality matters.
        total = values["global_cap"] or values["max_items"]
        items: list[dict[str, Any]] = []
        with self.db.session() as db:
            found_ids: list[str] = []
            for kind in include or _KINDS:
                sql = "SELECT entry_id FROM entry_fts WHERE entry_fts MATCH ? AND entry_type=?"
                params: list[Any] = [query, kind]
                if values["project"]:
                    sql += " AND project=?"
                    params.append(values["project"])
                sql += " ORDER BY rank LIMIT ?"
                params.append(values["max_items"])
                try:
                    found_ids.extend(row[0] for row in db.execute(sql, params))
                except sqlite3.OperationalError as exc:  # malformed FTS5 syntax is caller input
                    raise _invalid("query") from exc
            for entry_id in found_ids[:total]:
                found = self._find_row(db, entry_id)
                if found:
                    items.append(self._entry(found[0], found[2]))
        return {"status": "ok", "correlation_id": cid, "items": items}
