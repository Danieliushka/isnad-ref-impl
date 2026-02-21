"""
isnad.storage — Pluggable persistence backends for isnad data structures.

Backends: MemoryBackend, SQLiteBackend, FileBackend
Persistent wrappers: PersistentTrustChain, PersistentRevocationRegistry
GDPR: delete_by_agent() across all backends
"""

import json
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from isnad.core import (
    AgentIdentity,
    Attestation,
    RevocationEntry,
    RevocationRegistry,
    TrustChain,
)


# ─── Abstract Backend ──────────────────────────────────────────────

class StorageBackend(ABC):
    """Abstract persistence interface."""

    @abstractmethod
    def save(self, key: str, data: dict) -> None: ...

    @abstractmethod
    def load(self, key: str) -> Optional[dict]: ...

    @abstractmethod
    def delete(self, key: str) -> bool: ...

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    # Bulk operations (default impls, backends may override)
    def save_many(self, items: dict[str, dict]) -> None:
        for k, v in items.items():
            self.save(k, v)

    def load_many(self, keys: list[str]) -> dict[str, Optional[dict]]:
        return {k: self.load(k) for k in keys}

    def delete_many(self, keys: list[str]) -> int:
        return sum(1 for k in keys if self.delete(k))

    def delete_by_agent(self, agent_id: str) -> int:
        """GDPR: delete all records referencing agent_id."""
        deleted = 0
        for key in self.list_keys():
            data = self.load(key)
            if data and _references_agent(data, agent_id):
                if self.delete(key):
                    deleted += 1
        return deleted


def _references_agent(data: dict, agent_id: str) -> bool:
    """Check if a data dict references the given agent_id."""
    for v in data.values():
        if v == agent_id:
            return True
    return False


# ─── Memory Backend ────────────────────────────────────────────────

class MemoryBackend(StorageBackend):
    """In-memory dict storage (default, for testing)."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def save(self, key: str, data: dict) -> None:
        self._store[key] = data

    def load(self, key: str) -> Optional[dict]:
        return self._store.get(key)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def list_keys(self, prefix: str = "") -> list[str]:
        return [k for k in self._store if k.startswith(prefix)]

    def exists(self, key: str) -> bool:
        return key in self._store


# ─── SQLite Backend ────────────────────────────────────────────────

class SQLiteBackend(StorageBackend):
    """File-based SQLite with WAL mode, thread-safe."""

    def __init__(self, db_path: str = "isnad.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                agent_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_agent ON kv(agent_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON kv(created_at)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_key_prefix ON kv(key)")
        self._conn.commit()

    def save(self, key: str, data: dict) -> None:
        agent_id = data.get("subject") or data.get("witness") or data.get("revoked_by")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv (key, data, agent_id, created_at) VALUES (?, ?, ?, ?)",
                (key, json.dumps(data), agent_id, datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()

    def load(self, key: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT data FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    def list_keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM kv WHERE key LIKE ?", (prefix + "%",)
            ).fetchall()
        return [r[0] for r in rows]

    def exists(self, key: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM kv WHERE key = ?", (key,)).fetchone()
        return row is not None

    def query_by_agent(self, agent_id: str) -> list[dict]:
        """Query all records for a given agent_id."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, data FROM kv WHERE agent_id = ?", (agent_id,)
            ).fetchall()
        return [json.loads(r[1]) for r in rows]

    def save_many(self, items: dict[str, dict]) -> None:
        with self._lock:
            for k, data in items.items():
                agent_id = data.get("subject") or data.get("witness") or data.get("revoked_by")
                self._conn.execute(
                    "INSERT OR REPLACE INTO kv (key, data, agent_id, created_at) VALUES (?, ?, ?, ?)",
                    (k, json.dumps(data), agent_id, datetime.now(timezone.utc).isoformat()),
                )
            self._conn.commit()

    def delete_many(self, keys: list[str]) -> int:
        with self._lock:
            total = 0
            for k in keys:
                cur = self._conn.execute("DELETE FROM kv WHERE key = ?", (k,))
                total += cur.rowcount
            self._conn.commit()
            return total

    def delete_by_agent(self, agent_id: str) -> int:
        """GDPR: delete all records where agent_id matches."""
        with self._lock:
            # Delete by indexed agent_id column
            cur = self._conn.execute("DELETE FROM kv WHERE agent_id = ?", (agent_id,))
            # Also scan for references in data
            rows = self._conn.execute("SELECT key, data FROM kv").fetchall()
            extra_keys = []
            for key, raw in rows:
                data = json.loads(raw)
                if _references_agent(data, agent_id):
                    extra_keys.append(key)
            extra = 0
            for k in extra_keys:
                c = self._conn.execute("DELETE FROM kv WHERE key = ?", (k,))
                extra += c.rowcount
            self._conn.commit()
            return cur.rowcount + extra

    def close(self):
        self._conn.close()


# ─── File Backend ──────────────────────────────────────────────────

class FileBackend(StorageBackend):
    """JSONL-based file storage. One file per namespace."""

    def __init__(self, base_dir: str = "isnad_data", namespace: str = "default"):
        self._base_dir = Path(base_dir)
        self._namespace = namespace
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def _filepath(self) -> Path:
        return self._base_dir / f"{self._namespace}.jsonl"

    def _read_all(self) -> dict[str, dict]:
        """Read all records from JSONL file."""
        records: dict[str, dict] = {}
        if not self._filepath.exists():
            return records
        with open(self._filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                key = entry.get("__key__")
                if entry.get("__deleted__"):
                    records.pop(key, None)
                else:
                    records[key] = {k: v for k, v in entry.items() if k != "__key__"}
        return records

    def _rewrite(self, records: dict[str, dict]) -> None:
        """Compact rewrite of the JSONL file."""
        with open(self._filepath, "w") as f:
            for key, data in records.items():
                entry = {"__key__": key, **data}
                f.write(json.dumps(entry) + "\n")

    def save(self, key: str, data: dict) -> None:
        with self._lock:
            entry = {"__key__": key, **data}
            with open(self._filepath, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def load(self, key: str) -> Optional[dict]:
        with self._lock:
            records = self._read_all()
        return records.get(key)

    def delete(self, key: str) -> bool:
        with self._lock:
            records = self._read_all()
            if key not in records:
                return False
            # Append delete marker
            with open(self._filepath, "a") as f:
                f.write(json.dumps({"__key__": key, "__deleted__": True}) + "\n")
            return True

    def list_keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            records = self._read_all()
        return [k for k in records if k.startswith(prefix)]

    def exists(self, key: str) -> bool:
        with self._lock:
            records = self._read_all()
        return key in records

    def delete_by_agent(self, agent_id: str) -> int:
        with self._lock:
            records = self._read_all()
            to_delete = [k for k, v in records.items() if _references_agent(v, agent_id)]
            if not to_delete:
                return 0
            with open(self._filepath, "a") as f:
                for key in to_delete:
                    f.write(json.dumps({"__key__": key, "__deleted__": True}) + "\n")
            return len(to_delete)


# ─── Persistent TrustChain ─────────────────────────────────────────

class PersistentTrustChain:
    """Wraps TrustChain + StorageBackend. Auto-persists on add(), hydrates on init."""

    def __init__(self, backend: StorageBackend, prefix: str = "attestation:",
                 revocation_registry: Optional[RevocationRegistry] = None):
        self._backend = backend
        self._prefix = prefix
        self._chain = TrustChain(revocation_registry=revocation_registry)
        self._hydrate()

    def _hydrate(self) -> None:
        """Load all attestations from backend."""
        for key in self._backend.list_keys(self._prefix):
            data = self._backend.load(key)
            if data:
                att = Attestation.from_dict(data)
                # Add directly to chain internals to avoid re-persisting
                if att.verify():
                    self._chain.attestations.append(att)
                    self._chain._by_subject.setdefault(att.subject, []).append(att)
                    self._chain._by_witness.setdefault(att.witness, []).append(att)

    def add(self, attestation: Attestation, event_bus=None) -> bool:
        """Add attestation and persist."""
        result = self._chain.add(attestation, event_bus=event_bus)
        if result:
            key = f"{self._prefix}{attestation.attestation_id}"
            self._backend.save(key, attestation.to_dict())
        return result

    def trust_score(self, agent_id: str, scope: Optional[str] = None) -> float:
        return self._chain.trust_score(agent_id, scope=scope)

    def chain_trust(self, source: str, target: str, max_hops: int = 5) -> float:
        return self._chain.chain_trust(source, target, max_hops=max_hops)

    @property
    def attestations(self) -> list[Attestation]:
        return self._chain.attestations

    @property
    def backend(self) -> StorageBackend:
        return self._backend


# ─── Persistent RevocationRegistry ─────────────────────────────────

class PersistentRevocationRegistry:
    """Wraps RevocationRegistry + StorageBackend. Auto-persists on revoke()."""

    def __init__(self, backend: StorageBackend, prefix: str = "revocation:"):
        self._backend = backend
        self._prefix = prefix
        self._registry = RevocationRegistry()
        self._hydrate()

    def _hydrate(self) -> None:
        for key in self._backend.list_keys(self._prefix):
            data = self._backend.load(key)
            if data:
                entry = RevocationEntry.from_dict(data)
                self._registry.revoke(entry)

    def revoke(self, entry: RevocationEntry, event_bus=None) -> None:
        self._registry.revoke(entry, event_bus=event_bus)
        key = f"{self._prefix}{entry.target_id}_{int(entry.timestamp * 1000)}"
        self._backend.save(key, entry.to_dict())

    def is_revoked(self, target_id: str, scope: Optional[str] = None) -> bool:
        return self._registry.is_revoked(target_id, scope=scope)

    def get_revocations(self, target_id: str) -> list[RevocationEntry]:
        return self._registry.get_revocations(target_id)

    @property
    def all_entries(self) -> list[RevocationEntry]:
        return self._registry.all_entries

    @property
    def backend(self) -> StorageBackend:
        return self._backend


__all__ = [
    "StorageBackend",
    "MemoryBackend",
    "SQLiteBackend",
    "FileBackend",
    "PersistentTrustChain",
    "PersistentRevocationRegistry",
]
