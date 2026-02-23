"""
isnad.database — Async SQLite persistence layer for the isnad trust platform.

Provides structured tables (not KV) for agents, attestations, certifications,
API keys, and trust checks. Uses aiosqlite for FastAPI compatibility.

Migration support: schema versioning via a `schema_version` table.
"""

import json
import hashlib
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

__all__ = [
    "Database",
    "migrate_from_memory",
]

# ─── Schema ────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,              -- agent:<hash>
    name TEXT,
    public_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',       -- JSON
    is_certified INTEGER DEFAULT 0,
    trust_score REAL DEFAULT 0.0,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS attestations (
    id TEXT PRIMARY KEY,              -- attestation_id (sha256[:16])
    subject_id TEXT NOT NULL,
    witness_id TEXT NOT NULL,
    task TEXT NOT NULL,
    evidence_uri TEXT DEFAULT '',
    signature TEXT,
    witness_pubkey TEXT,
    timestamp TEXT NOT NULL,
    is_revoked INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS certifications (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    score REAL NOT NULL,
    category_scores TEXT DEFAULT '{}', -- JSON
    certified_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    badge_hash TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    owner_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rate_limit INTEGER DEFAULT 100,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trust_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    score REAL,
    report TEXT DEFAULT '{}',         -- JSON
    requester_ip TEXT
);
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_attestations_subject ON attestations(subject_id);
CREATE INDEX IF NOT EXISTS idx_attestations_witness ON attestations(witness_id);
CREATE INDEX IF NOT EXISTS idx_attestations_task ON attestations(task);
CREATE INDEX IF NOT EXISTS idx_attestations_timestamp ON attestations(timestamp);
CREATE INDEX IF NOT EXISTS idx_certifications_agent ON certifications(agent_id);
CREATE INDEX IF NOT EXISTS idx_certifications_expires ON certifications(expires_at);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_trust_checks_agent ON trust_checks(agent_id);
CREATE INDEX IF NOT EXISTS idx_trust_checks_time ON trust_checks(requested_at);
"""


# ─── Database Manager ──────────────────────────────────────────────

class Database:
    """Async SQLite connection manager with schema migration support."""

    def __init__(self, db_path: str = "isnad.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open connection and ensure schema is applied."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._apply_schema()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @asynccontextmanager
    async def transaction(self):
        """Context manager for explicit transactions."""
        assert self._db, "Database not connected"
        async with self._db.execute("BEGIN"):
            try:
                yield self._db
                await self._db.commit()
            except Exception:
                await self._db.rollback()
                raise

    async def _apply_schema(self) -> None:
        """Apply schema migrations."""
        assert self._db
        for stmt in _TABLES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._db.execute(stmt)
        for stmt in _INDEXES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._db.execute(stmt)

        # Record schema version
        row = await (await self._db.execute(
            "SELECT MAX(version) FROM schema_version"
        )).fetchone()
        current = row[0] if row and row[0] else 0
        if current < SCHEMA_VERSION:
            await self._db.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _now_iso()),
            )
        await self._db.commit()

    # ─── Agents CRUD ───────────────────────────────────────────────

    async def create_agent(self, agent_id: str, public_key: str,
                           name: str = "", metadata: dict | None = None) -> dict:
        row = {
            "id": agent_id,
            "name": name,
            "public_key": public_key,
            "created_at": _now_iso(),
            "metadata": json.dumps(metadata or {}),
            "is_certified": 0,
            "trust_score": 0.0,
            "last_checked": None,
        }
        await self._db.execute(
            "INSERT INTO agents (id, name, public_key, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (row["id"], row["name"], row["public_key"], row["created_at"], row["metadata"]),
        )
        await self._db.commit()
        return row

    async def get_agent(self, agent_id: str) -> Optional[dict]:
        cur = await self._db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = await cur.fetchone()
        return _row_to_dict(cur, row) if row else None

    async def get_agent_by_pubkey(self, public_key: str) -> Optional[dict]:
        cur = await self._db.execute("SELECT * FROM agents WHERE public_key = ?", (public_key,))
        row = await cur.fetchone()
        return _row_to_dict(cur, row) if row else None

    async def list_agents(self, limit: int = 100, offset: int = 0) -> list[dict]:
        cur = await self._db.execute(
            "SELECT * FROM agents ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]

    async def update_agent(self, agent_id: str, **fields) -> bool:
        if not fields:
            return False
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [agent_id]
        cur = await self._db.execute(f"UPDATE agents SET {sets} WHERE id = ?", vals)
        await self._db.commit()
        return cur.rowcount > 0

    async def delete_agent(self, agent_id: str) -> bool:
        """GDPR-compatible: deletes agent and all related records."""
        await self._db.execute("DELETE FROM attestations WHERE subject_id = ? OR witness_id = ?", (agent_id, agent_id))
        await self._db.execute("DELETE FROM certifications WHERE agent_id = ?", (agent_id,))
        await self._db.execute("DELETE FROM trust_checks WHERE agent_id = ?", (agent_id,))
        cur = await self._db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        await self._db.commit()
        return cur.rowcount > 0

    # ─── Attestations CRUD ─────────────────────────────────────────

    async def create_attestation(self, attestation_id: str, subject_id: str,
                                  witness_id: str, task: str,
                                  evidence_uri: str = "", signature: str = "",
                                  witness_pubkey: str = "",
                                  timestamp: str = "") -> dict:
        ts = timestamp or _now_iso()
        await self._db.execute(
            """INSERT INTO attestations
               (id, subject_id, witness_id, task, evidence_uri, signature, witness_pubkey, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (attestation_id, subject_id, witness_id, task, evidence_uri,
             signature, witness_pubkey, ts),
        )
        await self._db.commit()
        return {
            "id": attestation_id, "subject_id": subject_id, "witness_id": witness_id,
            "task": task, "evidence_uri": evidence_uri, "signature": signature,
            "witness_pubkey": witness_pubkey, "timestamp": ts, "is_revoked": 0,
        }

    async def get_attestation(self, attestation_id: str) -> Optional[dict]:
        cur = await self._db.execute("SELECT * FROM attestations WHERE id = ?", (attestation_id,))
        row = await cur.fetchone()
        return _row_to_dict(cur, row) if row else None

    async def get_attestations_for_subject(self, subject_id: str) -> list[dict]:
        cur = await self._db.execute(
            "SELECT * FROM attestations WHERE subject_id = ? AND is_revoked = 0 ORDER BY timestamp DESC",
            (subject_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]

    async def get_attestations_by_witness(self, witness_id: str) -> list[dict]:
        cur = await self._db.execute(
            "SELECT * FROM attestations WHERE witness_id = ? ORDER BY timestamp DESC",
            (witness_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]

    async def revoke_attestation(self, attestation_id: str) -> bool:
        cur = await self._db.execute(
            "UPDATE attestations SET is_revoked = 1 WHERE id = ?", (attestation_id,),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def count_attestations(self) -> int:
        row = await (await self._db.execute("SELECT COUNT(*) FROM attestations")).fetchone()
        return row[0]

    # ─── Certifications CRUD ───────────────────────────────────────

    async def create_certification(self, cert_id: str, agent_id: str,
                                    score: float, category_scores: dict,
                                    certified_at: str, expires_at: str,
                                    badge_hash: str = "") -> dict:
        await self._db.execute(
            """INSERT INTO certifications
               (id, agent_id, score, category_scores, certified_at, expires_at, badge_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cert_id, agent_id, score, json.dumps(category_scores),
             certified_at, expires_at, badge_hash),
        )
        await self._db.commit()
        return {
            "id": cert_id, "agent_id": agent_id, "score": score,
            "category_scores": category_scores, "certified_at": certified_at,
            "expires_at": expires_at, "badge_hash": badge_hash,
        }

    async def get_certification(self, cert_id: str) -> Optional[dict]:
        cur = await self._db.execute("SELECT * FROM certifications WHERE id = ?", (cert_id,))
        row = await cur.fetchone()
        if not row:
            return None
        d = _row_to_dict(cur, row)
        d["category_scores"] = json.loads(d["category_scores"])
        return d

    async def get_certifications_for_agent(self, agent_id: str) -> list[dict]:
        cur = await self._db.execute(
            "SELECT * FROM certifications WHERE agent_id = ? ORDER BY certified_at DESC",
            (agent_id,),
        )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(cur, r)
            d["category_scores"] = json.loads(d["category_scores"])
            result.append(d)
        return result

    # ─── API Keys CRUD ─────────────────────────────────────────────

    async def create_api_key(self, raw_key: str, owner_email: str,
                              rate_limit: int = 100) -> dict:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now = _now_iso()
        cur = await self._db.execute(
            """INSERT INTO api_keys (key_hash, owner_email, created_at, rate_limit)
               VALUES (?, ?, ?, ?)""",
            (key_hash, owner_email, now, rate_limit),
        )
        await self._db.commit()
        return {
            "id": cur.lastrowid, "key_hash": key_hash,
            "owner_email": owner_email, "created_at": now,
            "rate_limit": rate_limit, "is_active": 1,
        }

    async def validate_api_key(self, raw_key: str) -> Optional[dict]:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        cur = await self._db.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
            (key_hash,),
        )
        row = await cur.fetchone()
        return _row_to_dict(cur, row) if row else None

    async def deactivate_api_key(self, key_hash: str) -> bool:
        cur = await self._db.execute(
            "UPDATE api_keys SET is_active = 0 WHERE key_hash = ?", (key_hash,),
        )
        await self._db.commit()
        return cur.rowcount > 0

    # ─── Trust Checks CRUD ─────────────────────────────────────────

    async def create_trust_check(self, agent_id: str, score: float,
                                  report: dict, requester_ip: str = "") -> dict:
        now = _now_iso()
        cur = await self._db.execute(
            """INSERT INTO trust_checks (agent_id, requested_at, score, report, requester_ip)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_id, now, score, json.dumps(report), requester_ip),
        )
        await self._db.commit()
        return {
            "id": cur.lastrowid, "agent_id": agent_id,
            "requested_at": now, "score": score,
            "report": report, "requester_ip": requester_ip,
        }

    async def get_trust_checks(self, agent_id: str, limit: int = 20) -> list[dict]:
        cur = await self._db.execute(
            "SELECT * FROM trust_checks WHERE agent_id = ? ORDER BY requested_at DESC LIMIT ?",
            (agent_id, limit),
        )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(cur, r)
            d["report"] = json.loads(d["report"])
            result.append(d)
        return result

    # ─── Migration helper ──────────────────────────────────────────

    async def migrate_from_memory(self, identities: dict, trust_chain, revocation_registry) -> dict:
        """Migrate in-memory stores from api.py into SQLite tables.

        Args:
            identities: dict[agent_id, AgentIdentity]
            trust_chain: TrustChain instance
            revocation_registry: RevocationRegistry instance

        Returns summary of migrated counts.
        """
        agents_count = 0
        att_count = 0
        rev_count = 0

        # Migrate agents
        for agent_id, identity in identities.items():
            try:
                await self.create_agent(
                    agent_id=agent_id,
                    public_key=identity.public_key_hex,
                    name="",
                )
                agents_count += 1
            except Exception:
                pass  # already exists

        # Migrate attestations
        for att in trust_chain.attestations:
            try:
                is_revoked = revocation_registry.is_revoked(att.attestation_id)
                await self._db.execute(
                    """INSERT OR IGNORE INTO attestations
                       (id, subject_id, witness_id, task, evidence_uri, signature, witness_pubkey, timestamp, is_revoked)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (att.attestation_id, att.subject, att.witness, att.task,
                     att.evidence, att.signature, att.witness_pubkey,
                     att.timestamp, int(is_revoked)),
                )
                att_count += 1
            except Exception:
                pass

        await self._db.commit()
        return {"agents": agents_count, "attestations": att_count}


# ─── Helpers ───────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(cursor, row) -> dict:
    """Convert sqlite row to dict using cursor description."""
    if row is None:
        return {}
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


# ─── Convenience: module-level singleton ───────────────────────────

_default_db: Optional[Database] = None


async def get_db(db_path: str = "isnad.db") -> Database:
    """Get or create the module-level Database singleton."""
    global _default_db
    if _default_db is None:
        _default_db = Database(db_path)
        await _default_db.connect()
    return _default_db


async def close_db() -> None:
    """Close the module-level singleton."""
    global _default_db
    if _default_db:
        await _default_db.close()
        _default_db = None
