#!/usr/bin/env python3
"""
isnad.storage — Pluggable persistence backends for Isnad trust data.

Provides an abstract StorageBackend interface and concrete implementations:
  - MemoryBackend:  In-memory (default, same as current behavior)
  - SQLiteBackend:  File-based SQLite for single-node persistence
  - FileBackend:    JSON-file based storage for simple deployments

Usage:
    from isnad.storage import SQLiteBackend, PersistentTrustChain

    backend = SQLiteBackend("trust.db")
    chain = PersistentTrustChain(backend)
    chain.add(attestation)  # auto-persisted
"""

import json
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from isnad.core import (
    Attestation,
    RevocationEntry,
    Delegation,
    TrustChain,
    RevocationRegistry,
    DelegationRegistry,
)


# ─── Abstract Backend ──────────────────────────────────────────────

class StorageBackend(ABC):
    """Abstract interface for isnad persistence."""

    @abstractmethod
    def store_attestation(self, attestation: Attestation) -> None:
        """Persist a single attestation."""

    @abstractmethod
    def load_attestations(self) -> List[dict]:
        """Load all attestations as dicts."""

    @abstractmethod
    def store_revocation(self, entry: RevocationEntry) -> None:
        """Persist a revocation entry."""

    @abstractmethod
    def load_revocations(self) -> List[dict]:
        """Load all revocation entries as dicts."""

    @abstractmethod
    def store_delegation(self, delegation: Delegation) -> None:
        """Persist a delegation."""

    @abstractmethod
    def load_delegations(self) -> List[dict]:
        """Load all delegations as dicts."""

    @abstractmethod
    def delete_by_agent(self, agent_id: str) -> int:
        """Delete all data for an agent (GDPR Art. 17). Returns count deleted."""

    @abstractmethod
    def count(self, collection: str) -> int:
        """Count items in a collection (attestations/revocations/delegations)."""

    def close(self) -> None:
        """Clean up resources."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── Memory Backend ────────────────────────────────────────────────

class MemoryBackend(StorageBackend):
    """In-memory storage (no persistence). Default behavior."""

    def __init__(self):
        self._attestations: List[dict] = []
        self._revocations: List[dict] = []
        self._delegations: List[dict] = []
        self._lock = threading.Lock()

    def store_attestation(self, attestation: Attestation) -> None:
        with self._lock:
            self._attestations.append(attestation.to_dict())

    def load_attestations(self) -> List[dict]:
        with self._lock:
            return list(self._attestations)

    def store_revocation(self, entry: RevocationEntry) -> None:
        with self._lock:
            self._revocations.append(entry.to_dict())

    def load_revocations(self) -> List[dict]:
        with self._lock:
            return list(self._revocations)

    def store_delegation(self, delegation: Delegation) -> None:
        with self._lock:
            self._delegations.append(delegation.to_dict())

    def load_delegations(self) -> List[dict]:
        with self._lock:
            return list(self._delegations)

    def delete_by_agent(self, agent_id: str) -> int:
        with self._lock:
            count = 0
            for store, fields in [
                (self._attestations, ("subject", "witness")),
                (self._revocations, ("revoked_by",)),
                (self._delegations, ("principal", "delegate")),
            ]:
                before = len(store)
                store[:] = [
                    item for item in store
                    if not any(item.get(f) == agent_id for f in fields)
                ]
                count += before - len(store)
            return count

    def count(self, collection: str) -> int:
        with self._lock:
            return len(getattr(self, f"_{collection}", []))


# ─── SQLite Backend ────────────────────────────────────────────────

class SQLiteBackend(StorageBackend):
    """SQLite-based persistence for single-node deployments."""

    def __init__(self, db_path: str = "isnad.db", wal_mode: bool = True):
        self.db_path = db_path
        self._local = threading.local()
        self._wal_mode = wal_mode
        # Initialize schema on main thread
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            if self._wal_mode:
                self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS attestations (
                attestation_id TEXT PRIMARY KEY,
                witness TEXT NOT NULL,
                subject TEXT NOT NULL,
                task TEXT NOT NULL,
                evidence TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                signature TEXT,
                witness_pubkey TEXT,
                data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_att_subject ON attestations(subject);
            CREATE INDEX IF NOT EXISTS idx_att_witness ON attestations(witness);
            CREATE INDEX IF NOT EXISTS idx_att_timestamp ON attestations(timestamp);

            CREATE TABLE IF NOT EXISTS revocations (
                revocation_id TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                revoked_by TEXT NOT NULL,
                reason TEXT DEFAULT '',
                timestamp REAL NOT NULL,
                scope TEXT DEFAULT 'general',
                data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rev_target ON revocations(target_id);
            CREATE INDEX IF NOT EXISTS idx_rev_by ON revocations(revoked_by);

            CREATE TABLE IF NOT EXISTS delegations (
                delegation_id TEXT PRIMARY KEY,
                principal TEXT NOT NULL,
                delegate TEXT NOT NULL,
                scopes TEXT DEFAULT '["*"]',
                max_depth INTEGER DEFAULT 0,
                expires_at REAL,
                timestamp REAL NOT NULL,
                data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_del_delegate ON delegations(delegate);
            CREATE INDEX IF NOT EXISTS idx_del_principal ON delegations(principal);
        """)
        conn.commit()

    def store_attestation(self, attestation: Attestation) -> None:
        d = attestation.to_dict()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO attestations
               (attestation_id, witness, subject, task, evidence,
                timestamp, signature, witness_pubkey, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                d["attestation_id"], d["witness"], d["subject"],
                d["task"], d.get("evidence", ""), d["timestamp"],
                d.get("signature", ""), d.get("witness_pubkey", ""),
                json.dumps(d),
            ),
        )
        conn.commit()

    def load_attestations(self) -> List[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM attestations ORDER BY timestamp").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def store_revocation(self, entry: RevocationEntry) -> None:
        d = entry.to_dict()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO revocations
               (revocation_id, target_id, revoked_by, reason, timestamp, scope, data)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                d.get("revocation_id", d["target_id"]),
                d["target_id"], d["revoked_by"],
                d.get("reason", ""), d["timestamp"],
                d.get("scope", "general"), json.dumps(d),
            ),
        )
        conn.commit()

    def load_revocations(self) -> List[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM revocations ORDER BY timestamp").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def store_delegation(self, delegation: Delegation) -> None:
        d = delegation.to_dict()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO delegations
               (delegation_id, principal, delegate, scopes, max_depth,
                expires_at, timestamp, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                d["delegation_id"], d["principal"], d["delegate"],
                json.dumps(d.get("scopes", ["*"])), d.get("max_depth", 0),
                d.get("expires_at"), d["timestamp"], json.dumps(d),
            ),
        )
        conn.commit()

    def load_delegations(self) -> List[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT data FROM delegations ORDER BY timestamp").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def delete_by_agent(self, agent_id: str) -> int:
        conn = self._get_conn()
        count = 0
        count += conn.execute(
            "DELETE FROM attestations WHERE subject=? OR witness=?",
            (agent_id, agent_id),
        ).rowcount
        count += conn.execute(
            "DELETE FROM revocations WHERE revoked_by=?",
            (agent_id,),
        ).rowcount
        count += conn.execute(
            "DELETE FROM delegations WHERE principal=? OR delegate=?",
            (agent_id, agent_id),
        ).rowcount
        conn.commit()
        return count

    def count(self, collection: str) -> int:
        table_map = {
            "attestations": "attestations",
            "revocations": "revocations",
            "delegations": "delegations",
        }
        table = table_map.get(collection)
        if not table:
            return 0
        conn = self._get_conn()
        row = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
        return row["c"]

    def query_attestations(
        self,
        subject: Optional[str] = None,
        witness: Optional[str] = None,
        task: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """Advanced query with filters — SQLite advantage over in-memory."""
        conn = self._get_conn()
        conditions = ["1=1"]
        params: list = []

        if subject:
            conditions.append("subject = ?")
            params.append(subject)
        if witness:
            conditions.append("witness = ?")
            params.append(witness)
        if task:
            conditions.append("task = ?")
            params.append(task)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = " AND ".join(conditions)
        params.append(limit)
        rows = conn.execute(
            f"SELECT data FROM attestations WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# ─── File Backend ──────────────────────────────────────────────────

class FileBackend(StorageBackend):
    """JSON-file persistence for simple deployments."""

    def __init__(self, directory: str = "isnad_data"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _file(self, name: str) -> Path:
        return self.directory / f"{name}.jsonl"

    def _append(self, name: str, data: dict) -> None:
        with self._lock:
            with open(self._file(name), "a") as f:
                f.write(json.dumps(data, separators=(",", ":")) + "\n")

    def _load(self, name: str) -> List[dict]:
        path = self._file(name)
        if not path.exists():
            return []
        with self._lock:
            items = []
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        items.append(json.loads(line))
            return items

    def _rewrite(self, name: str, items: List[dict]) -> None:
        with self._lock:
            with open(self._file(name), "w") as f:
                for item in items:
                    f.write(json.dumps(item, separators=(",", ":")) + "\n")

    def store_attestation(self, attestation: Attestation) -> None:
        self._append("attestations", attestation.to_dict())

    def load_attestations(self) -> List[dict]:
        return self._load("attestations")

    def store_revocation(self, entry: RevocationEntry) -> None:
        self._append("revocations", entry.to_dict())

    def load_revocations(self) -> List[dict]:
        return self._load("revocations")

    def store_delegation(self, delegation: Delegation) -> None:
        self._append("delegations", delegation.to_dict())

    def load_delegations(self) -> List[dict]:
        return self._load("delegations")

    def delete_by_agent(self, agent_id: str) -> int:
        count = 0
        for name, fields in [
            ("attestations", ("subject", "witness")),
            ("revocations", ("revoked_by",)),
            ("delegations", ("principal", "delegate")),
        ]:
            items = self._load(name)
            filtered = [
                item for item in items
                if not any(item.get(f) == agent_id for f in fields)
            ]
            count += len(items) - len(filtered)
            if count > 0:
                self._rewrite(name, filtered)
        return count

    def count(self, collection: str) -> int:
        return len(self._load(collection))


# ─── Persistent Wrappers ──────────────────────────────────────────

class PersistentTrustChain(TrustChain):
    """TrustChain with automatic persistence via StorageBackend."""

    def __init__(self, backend: StorageBackend, revocation_registry=None):
        super().__init__(revocation_registry=revocation_registry)
        self.backend = backend
        self._load_from_backend()

    def _load_from_backend(self) -> None:
        """Hydrate in-memory state from backend."""
        for data in self.backend.load_attestations():
            att = Attestation.from_dict(data)
            super().add(att)

    def add(self, attestation: Attestation, event_bus=None) -> bool:
        """Add attestation and persist."""
        result = super().add(attestation, event_bus=event_bus)
        if result:
            self.backend.store_attestation(attestation)
        return result


class PersistentRevocationRegistry(RevocationRegistry):
    """RevocationRegistry with automatic persistence."""

    def __init__(self, backend: StorageBackend):
        super().__init__()
        self.backend = backend
        self._load_from_backend_init()

    def _load_from_backend_init(self) -> None:
        for data in self.backend.load_revocations():
            entry = RevocationEntry.from_dict(data)
            self._revoked.setdefault(entry.target_id, []).append(entry)

    def revoke(self, entry: RevocationEntry, event_bus=None) -> None:
        super().revoke(entry, event_bus=event_bus)
        self.backend.store_revocation(entry)


class PersistentDelegationRegistry(DelegationRegistry):
    """DelegationRegistry with automatic persistence."""

    def __init__(self, backend: StorageBackend, revocation_registry=None):
        super().__init__(revocation_registry=revocation_registry)
        self.backend = backend
        self._load_from_backend()

    def _load_from_backend(self) -> None:
        for data in self.backend.load_delegations():
            deleg = Delegation.from_dict(data)
            super().add(deleg)

    def add(self, delegation: Delegation) -> bool:
        result = super().add(delegation)
        if result:
            self.backend.store_delegation(delegation)
        return result
