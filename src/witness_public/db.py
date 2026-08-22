"""SQLite schema and transaction primitives for Witness."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_TRIGGER_UPDATE = "CREATE TRIGGER operations_log_no_update BEFORE UPDATE ON operations_log BEGIN SELECT RAISE(ABORT, 'operations_log is append-only'); END"
_TRIGGER_DELETE = "CREATE TRIGGER operations_log_no_delete BEFORE DELETE ON operations_log BEGIN SELECT RAISE(ABORT, 'operations_log is append-only'); END"

# public-contract.json audit.required_fields plus event_type, which carries the
# required_events classification. Startup verifies every one of them.
AUDIT_COLUMNS = (
    "event_id", "occurred_at", "principal_subject_id", "asserted_subject_id",
    "client_id", "role", "tool_name", "object_type", "object_id_or_redacted",
    "result_code", "correlation_id", "request_id", "event_type",
    "principal_pubkey", "owner_pubkey", "profile_id", "profile_version_sha256",
    "tenant_id", "runtime_generation", "envelope_nonce", "payload_sha256",
)


class WitnessDatabase:
    def __init__(self, path: str | Path, fault_injector: Any = None):
        self.path = str(path)
        self.fault_injector = fault_injector
        self.tampered = False
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    def _initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.session() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version(version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS project_registry(
              name TEXT PRIMARY KEY, domains TEXT NOT NULL, description TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions(
              id TEXT PRIMARY KEY, project TEXT NOT NULL, status TEXT NOT NULL,
              title TEXT NOT NULL, decision TEXT NOT NULL, domain TEXT NOT NULL,
              scope TEXT NOT NULL, alternatives TEXT NOT NULL, rationale TEXT NOT NULL,
              severity TEXT NOT NULL, pinned INTEGER NOT NULL, based_on TEXT NOT NULL,
              decision_ids TEXT NOT NULL, tags TEXT NOT NULL, task_id TEXT NOT NULL,
              impact_level TEXT NOT NULL, created_at TEXT NOT NULL, actor_subject_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS insights(
              id TEXT PRIMARY KEY, project TEXT NOT NULL, status TEXT NOT NULL,
              title TEXT NOT NULL, insight TEXT NOT NULL, confidence REAL NOT NULL,
              applies_to TEXT NOT NULL, applies_projects TEXT NOT NULL,
              applies_domains TEXT NOT NULL, actionable_in TEXT NOT NULL,
              based_on TEXT NOT NULL, tags TEXT NOT NULL, mcp_scope TEXT NOT NULL,
              applies_to_mcps TEXT NOT NULL, impact_level TEXT NOT NULL,
              created_at TEXT NOT NULL, actor_subject_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outcomes(
              id TEXT PRIMARY KEY, project TEXT NOT NULL, status TEXT NOT NULL,
              task_summary TEXT NOT NULL, result TEXT NOT NULL, domain TEXT NOT NULL,
              skills_used TEXT NOT NULL, tools_used TEXT NOT NULL, workflow_chain TEXT NOT NULL,
              duration_planned INTEGER, duration_actual INTEGER, root_cause TEXT NOT NULL,
              root_cause_category TEXT NOT NULL, prevented_by TEXT NOT NULL,
              decision_ids TEXT NOT NULL, based_on TEXT NOT NULL, quality_score REAL,
              execution_quality REAL, decision_quality REAL,
              compliant_with_decisions TEXT NOT NULL, tokens_input INTEGER,
              tokens_output INTEGER, tokens_total INTEGER, tags TEXT NOT NULL,
              session_id TEXT NOT NULL, task_id TEXT NOT NULL, impact_level TEXT NOT NULL,
              created_at TEXT NOT NULL, actor_subject_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records(
              id TEXT PRIMARY KEY, project TEXT NOT NULL, status TEXT NOT NULL,
              record_type TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
              based_on TEXT NOT NULL, references_json TEXT NOT NULL, tags TEXT NOT NULL,
              created_at TEXT NOT NULL, actor_subject_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS status_changes(
              id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL,
              old_status TEXT NOT NULL, new_status TEXT NOT NULL, reason TEXT NOT NULL,
              occurred_at TEXT NOT NULL, actor_subject_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY, source_id TEXT, target_id TEXT);
            CREATE TABLE IF NOT EXISTS operations_log(
              event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL,
              principal_subject_id TEXT NOT NULL, asserted_subject_id TEXT NOT NULL,
              client_id TEXT NOT NULL, role TEXT NOT NULL, tool_name TEXT NOT NULL,
              object_type TEXT NOT NULL, object_id_or_redacted TEXT NOT NULL,
              result_code TEXT NOT NULL, correlation_id TEXT NOT NULL,
              request_id TEXT NOT NULL, event_type TEXT NOT NULL,
              principal_pubkey TEXT NOT NULL, owner_pubkey TEXT NOT NULL,
              profile_id TEXT NOT NULL, profile_version_sha256 TEXT NOT NULL,
              tenant_id TEXT NOT NULL, runtime_generation TEXT NOT NULL,
              envelope_nonce TEXT NOT NULL, payload_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency(
              subject_id TEXT NOT NULL, tool_name TEXT NOT NULL, request_id TEXT NOT NULL,
              payload_hash TEXT NOT NULL, response_json TEXT NOT NULL,
              PRIMARY KEY(subject_id, tool_name, request_id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(
              entry_id UNINDEXED, entry_type UNINDEXED, project UNINDEXED, text
            );
            """)
            if db.execute("SELECT version FROM schema_version LIMIT 1").fetchone() is None:
                db.execute(_TRIGGER_UPDATE)
                db.execute(_TRIGGER_DELETE)
                db.execute("INSERT INTO schema_version(version) VALUES ('1.0.0-draft.1')")
                db.commit()
            self.tampered = not self._audit_protection_intact(db)

    @staticmethod
    def _audit_protection_intact(db: sqlite3.Connection) -> bool:
        """Verify the append-only audit table columns and both trigger digests."""
        columns = {row[1] for row in db.execute("PRAGMA table_info(operations_log)")}
        # Any missing *or additional* column changes the audit storage contract.
        # Extra fields are especially dangerous because they can create an
        # unaudited sink for credentials or content while the canonical fields
        # and append-only triggers still look intact.
        if columns != set(AUDIT_COLUMNS):
            return False
        observed = {
            row[0]: " ".join((row[1] or "").split())
            for row in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?)",
                ("operations_log_no_update", "operations_log_no_delete"),
            )
        }
        return observed == {
            "operations_log_no_update": " ".join(_TRIGGER_UPDATE.split()),
            "operations_log_no_delete": " ".join(_TRIGGER_DELETE.split()),
        }

    def inject(self, stage: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(stage)
