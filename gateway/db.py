"""SQLite durable state boundary for session taint, approvals, and consumed
capability-token nonces (gate 4: "make state and identity claims precise").

The in-memory dicts in gateway.taint.TaintStore and approval.tokens.ApprovalStore
stay the primary read/write path for the demo's per-process speed; this module
is the write-through, restart-surviving backing store behind them. On process
restart, a session or approval that dropped out of memory is rehydrated here
instead of silently reappearing as fresh/unknown state.

Single-process, single-writer only (WAL mode, one connection, one lock) — this
is sufficient for the hackathon's single-process deployment shape, not a
production multi-writer store. See STATUS.md for the migration note.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import threading
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS taint_sources (
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    trust TEXT NOT NULL,
    residency TEXT NOT NULL,
    shingle_index TEXT NOT NULL,
    entities TEXT NOT NULL,
    PRIMARY KEY (session_id, source_id)
);
CREATE TABLE IF NOT EXISTS session_flags (
    session_id TEXT PRIMARY KEY,
    untrusted_ingested INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    call_hash TEXT NOT NULL,
    tool TEXT NOT NULL,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    exp REAL NOT NULL,
    decision TEXT NOT NULL,
    decided_by TEXT,
    decided_at REAL,
    capability_token TEXT,
    consumed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS consumed_nonces (
    nonce_key TEXT PRIMARY KEY
);
"""

_APPROVAL_COLUMNS = [
    "approval_id", "call_hash", "tool", "session_id", "agent_id", "created_at",
    "exp", "decision", "decided_by", "decided_at", "capability_token", "consumed",
]


class StateDB:
    def __init__(self, path: pathlib.Path | str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- taint ---

    def save_source(
        self,
        session_id: str,
        source_id: str,
        trust: str,
        residency: str,
        shingle_index: list[list[str]],
        entities: list[str],
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO taint_sources VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, source_id, trust, residency, json.dumps(shingle_index), json.dumps(sorted(entities))),
            )
            self._conn.commit()

    def load_sources(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT source_id, trust, residency, shingle_index, entities FROM taint_sources WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return [
            {
                "source_id": r[0],
                "trust": r[1],
                "residency": r[2],
                "shingle_index": json.loads(r[3]),
                "entities": json.loads(r[4]),
            }
            for r in rows
        ]

    def set_untrusted(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO session_flags (session_id, untrusted_ingested) VALUES (?, 1) "
                "ON CONFLICT(session_id) DO UPDATE SET untrusted_ingested = 1",
                (session_id,),
            )
            self._conn.commit()

    def is_untrusted(self, session_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT untrusted_ingested FROM session_flags WHERE session_id = ?", (session_id,)
            ).fetchone()
        return bool(row and row[0])

    # --- approvals ---

    def save_approval(self, approval: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval.approval_id, approval.call_hash, approval.tool, approval.session_id,
                    approval.agent_id, approval.created_at, approval.exp, approval.decision,
                    approval.decided_by, approval.decided_at, approval.capability_token,
                    int(approval.consumed),
                ),
            )
            self._conn.commit()

    def load_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {', '.join(_APPROVAL_COLUMNS)} FROM approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(zip(_APPROVAL_COLUMNS, row))
        record["consumed"] = bool(record["consumed"])
        return record

    # --- consumed-nonce replay guard ---

    def add_consumed_nonce(self, nonce_key: str) -> None:
        with self._lock:
            self._conn.execute("INSERT OR IGNORE INTO consumed_nonces VALUES (?)", (nonce_key,))
            self._conn.commit()

    def has_consumed_nonce(self, nonce_key: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM consumed_nonces WHERE nonce_key = ?", (nonce_key,)
            ).fetchone()
        return row is not None
