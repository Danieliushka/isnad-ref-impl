"""
isnad.database — Async PostgreSQL persistence layer for the isnad trust platform.

Uses asyncpg for high-performance async PostgreSQL access.
Backwards-compatible interface: all public method signatures are preserved.

Configuration via DATABASE_URL environment variable:
    postgresql://isnad:isnad_secret@localhost:5432/isnad_db

Migration support: versioned SQL files in src/isnad/migrations/
"""

import json
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import asyncpg

__all__ = [
    "Database",
    "migrate_from_memory",
]

# ─── Config ────────────────────────────────────────────────────────

DEFAULT_DATABASE_URL = "postgresql://isnad:isnad_secret@localhost:5432/isnad_db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


# ─── Database Manager ──────────────────────────────────────────────

class Database:
    """Async PostgreSQL connection manager with schema migration support.

    Backwards-compatible drop-in replacement for the old aiosqlite version.
    All public methods preserve their original signatures.
    """

    def __init__(self, db_path: str = ""):
        """Initialize database.

        Args:
            db_path: For backwards compat. Ignored if DATABASE_URL is set.
                     If it looks like a postgres URI, use it directly.
        """
        self.database_url = os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            if db_path.startswith("postgresql://") or db_path.startswith("postgres://"):
                self.database_url = db_path
            else:
                self.database_url = DEFAULT_DATABASE_URL
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Open connection pool and ensure schema is applied."""
        self._pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            timeout=10,  # connection acquisition timeout
        )
        await self._apply_migrations()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def transaction(self):
        """Context manager for explicit transactions."""
        assert self._pool, "Database not connected"
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def _apply_migrations(self) -> None:
        """Apply versioned SQL migrations from migrations/ directory."""
        assert self._pool
        async with self._pool.acquire() as conn:
            # Ensure schema_version table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

            row = await conn.fetchrow("SELECT MAX(version) as v FROM schema_version")
            current = row["v"] if row and row["v"] else 0

            # Find and apply pending migrations
            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for mf in migration_files:
                # Extract version number from filename: 001_initial.sql -> 1
                version = int(mf.stem.split("_")[0])
                if version > current:
                    sql = mf.read_text()
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES ($1, $2)",
                        version, _now_iso(),
                    )

    # ─── Agents CRUD ───────────────────────────────────────────────

    async def create_agent(self, agent_id: str, public_key: str,
                           name: str = "", metadata: dict | None = None) -> dict:
        now = _now_iso()
        meta = json.dumps(metadata or {})
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO agents (id, name, public_key, created_at, metadata)
                   VALUES ($1, $2, $3, $4, $5)""",
                agent_id, name, public_key, now, meta,
            )
        return {
            "id": agent_id, "name": name, "public_key": public_key,
            "created_at": now, "metadata": meta,
            "is_certified": 0, "trust_score": 0.0, "last_checked": None,
        }

    async def get_agent(self, agent_id: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
        return _record_to_dict(row) if row else None

    async def get_agent_by_name(self, name: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agents WHERE LOWER(name) = LOWER($1)", name)
        return _record_to_dict(row) if row else None

    async def get_agent_by_pubkey(self, public_key: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agents WHERE public_key = $1", public_key)
        return _record_to_dict(row) if row else None

    async def get_agent_by_api_key(self, api_key: str) -> Optional[dict]:
        """Look up agent by raw API key (hashed for comparison)."""
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agents WHERE api_key_hash = $1", key_hash)
        return _record_to_dict(row) if row else None

    async def list_agents(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM agents ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
        return [_record_to_dict(r) for r in rows]

    async def update_agent(self, agent_id: str, **fields) -> bool:
        if not fields:
            return False
        # Build parameterized SET clause
        sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(fields))
        vals = list(fields.values()) + [agent_id]
        query = f"UPDATE agents SET {sets} WHERE id = ${len(vals)}"
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *vals)
        return result.split()[-1] != "0"  # "UPDATE N"

    async def delete_agent(self, agent_id: str) -> bool:
        """GDPR-compatible: deletes agent and all related records."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM attestations WHERE subject_id = $1 OR witness_id = $1",
                    agent_id,
                )
                await conn.execute("DELETE FROM certifications WHERE agent_id = $1", agent_id)
                await conn.execute("DELETE FROM trust_checks WHERE agent_id = $1", agent_id)
                await conn.execute("DELETE FROM platform_data WHERE agent_id = $1", agent_id)
                result = await conn.execute("DELETE FROM agents WHERE id = $1", agent_id)
        return result.split()[-1] != "0"

    # ─── Attestations CRUD ─────────────────────────────────────────

    async def create_attestation(self, attestation_id: str, subject_id: str,
                                  witness_id: str, task: str,
                                  evidence_uri: str = "", signature: str = "",
                                  witness_pubkey: str = "",
                                  timestamp: str = "") -> dict:
        ts = timestamp or _now_iso()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO attestations
                   (id, subject_id, witness_id, task, evidence_uri, signature, witness_pubkey, timestamp)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                attestation_id, subject_id, witness_id, task,
                evidence_uri, signature, witness_pubkey, ts,
            )
        return {
            "id": attestation_id, "subject_id": subject_id, "witness_id": witness_id,
            "task": task, "evidence_uri": evidence_uri, "signature": signature,
            "witness_pubkey": witness_pubkey, "timestamp": ts, "is_revoked": 0,
        }

    async def get_attestation(self, attestation_id: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM attestations WHERE id = $1", attestation_id)
        return _record_to_dict(row) if row else None

    async def get_attestations_for_subject(self, subject_id: str) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM attestations WHERE subject_id = $1 AND is_revoked = FALSE ORDER BY timestamp DESC",
                subject_id,
            )
        return [_record_to_dict(r) for r in rows]

    async def get_attestations_by_witness(self, witness_id: str) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM attestations WHERE witness_id = $1 ORDER BY timestamp DESC",
                witness_id,
            )
        return [_record_to_dict(r) for r in rows]

    async def revoke_attestation(self, attestation_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE attestations SET is_revoked = TRUE WHERE id = $1", attestation_id,
            )
        return result.split()[-1] != "0"

    async def count_attestations(self) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM attestations")
        return row["cnt"]

    # ─── Certifications CRUD ───────────────────────────────────────

    async def create_certification(self, cert_id: str, agent_id: str,
                                    score: float, category_scores: dict,
                                    certified_at: str, expires_at: str,
                                    badge_hash: str = "") -> dict:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO certifications
                   (id, agent_id, score, category_scores, certified_at, expires_at, badge_hash)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                cert_id, agent_id, score, json.dumps(category_scores),
                certified_at, expires_at, badge_hash,
            )
        return {
            "id": cert_id, "agent_id": agent_id, "score": score,
            "category_scores": category_scores, "certified_at": certified_at,
            "expires_at": expires_at, "badge_hash": badge_hash,
        }

    async def get_certification(self, cert_id: str) -> Optional[dict]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM certifications WHERE id = $1", cert_id)
        if not row:
            return None
        d = _record_to_dict(row)
        d["category_scores"] = json.loads(d["category_scores"]) if isinstance(d["category_scores"], str) else d["category_scores"]
        return d

    async def get_certifications_for_agent(self, agent_id: str) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM certifications WHERE agent_id = $1 ORDER BY certified_at DESC",
                agent_id,
            )
        result = []
        for r in rows:
            d = _record_to_dict(r)
            d["category_scores"] = json.loads(d["category_scores"]) if isinstance(d["category_scores"], str) else d["category_scores"]
            result.append(d)
        return result

    # ─── API Keys CRUD ─────────────────────────────────────────────

    async def create_api_key(self, raw_key: str, owner_email: str,
                              rate_limit: int = 100) -> dict:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now = _now_iso()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO api_keys (key_hash, owner_email, created_at, rate_limit)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                key_hash, owner_email, now, rate_limit,
            )
        return {
            "id": row["id"], "key_hash": key_hash,
            "owner_email": owner_email, "created_at": now,
            "rate_limit": rate_limit, "is_active": 1,
        }

    async def validate_api_key(self, raw_key: str) -> Optional[dict]:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM api_keys WHERE key_hash = $1 AND is_active = TRUE",
                key_hash,
            )
        return _record_to_dict(row) if row else None

    async def deactivate_api_key(self, key_hash: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE api_keys SET is_active = FALSE WHERE key_hash = $1", key_hash,
            )
        return result.split()[-1] != "0"

    # ─── Trust Checks CRUD ─────────────────────────────────────────

    async def create_trust_check(self, agent_id: str, score: float,
                                  report: dict, requester_ip: str = "") -> dict:
        now = _now_iso()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO trust_checks (agent_id, requested_at, score, report, requester_ip)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                agent_id, now, score, json.dumps(report), requester_ip,
            )
        return {
            "id": row["id"], "agent_id": agent_id,
            "requested_at": now, "score": score,
            "report": report, "requester_ip": requester_ip,
        }

    async def get_trust_checks(self, agent_id: str, limit: int = 20) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM trust_checks WHERE agent_id = $1 ORDER BY requested_at DESC LIMIT $2",
                agent_id, limit,
            )
        result = []
        for r in rows:
            d = _record_to_dict(r)
            d["report"] = json.loads(d["report"]) if isinstance(d["report"], str) else d["report"]
            result.append(d)
        return result

    # ─── Platform Data CRUD (new) ──────────────────────────────────

    async def create_platform_data(self, agent_id: str, platform_name: str,
                                    platform_url: str = "",
                                    raw_data: dict | None = None,
                                    metrics: dict | None = None) -> dict:
        """Create a platform data entry for an agent."""
        now = _now_iso()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO platform_data
                   (agent_id, platform_name, platform_url, raw_data, metrics, last_fetched)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                agent_id, platform_name, platform_url,
                json.dumps(raw_data or {}), json.dumps(metrics or {}), now,
            )
        return {
            "id": row["id"], "agent_id": agent_id,
            "platform_name": platform_name, "platform_url": platform_url,
            "raw_data": raw_data or {}, "metrics": metrics or {},
            "last_fetched": now,
        }

    # ─── Badges ─────────────────────────────────────────────────

    async def get_badges(self, agent_id: str) -> list[dict]:
        """Get all badges for an agent."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM badges WHERE agent_id = $1 ORDER BY created_at DESC",
                agent_id,
            )
        return [_record_to_dict(r) for r in rows]

    async def get_badge(self, agent_id: str, badge_type: str) -> Optional[dict]:
        """Get a specific badge for an agent."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM badges WHERE agent_id = $1 AND badge_type = $2",
                agent_id, badge_type,
            )
        return _record_to_dict(row) if row else None

    async def create_badge(self, agent_id: str, badge_type: str, status: str = "pending",
                           granted_at: Optional[str] = None, expires_at: Optional[str] = None) -> dict:
        """Create a badge record."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO badges (agent_id, badge_type, status, granted_at, expires_at)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (agent_id, badge_type) DO UPDATE
                   SET status = EXCLUDED.status, granted_at = EXCLUDED.granted_at, expires_at = EXCLUDED.expires_at
                   RETURNING *""",
                agent_id, badge_type, status, granted_at, expires_at,
            )
        return _record_to_dict(row)

    async def update_badge_status(self, agent_id: str, badge_type: str, status: str) -> Optional[dict]:
        """Update badge status."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE badges SET status = $3 WHERE agent_id = $1 AND badge_type = $2 RETURNING *",
                agent_id, badge_type, status,
            )
        return _record_to_dict(row) if row else None

    async def get_platform_data(self, agent_id: str) -> list[dict]:
        """Get all platform data for an agent."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM platform_data WHERE agent_id = $1 ORDER BY last_fetched DESC",
                agent_id,
            )
        return [_record_to_dict(r) for r in rows]

    # ─── Migration helper ──────────────────────────────────────────

    async def migrate_from_memory(self, identities: dict, trust_chain, revocation_registry) -> dict:
        """Migrate in-memory stores into PostgreSQL tables.

        Args:
            identities: dict[agent_id, AgentIdentity]
            trust_chain: TrustChain instance
            revocation_registry: RevocationRegistry instance

        Returns summary of migrated counts.
        """
        agents_count = 0
        att_count = 0

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for agent_id, identity in identities.items():
                    try:
                        await conn.execute(
                            """INSERT INTO agents (id, name, public_key, created_at)
                               VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                            agent_id, "", identity.public_key_hex, _now_iso(),
                        )
                        agents_count += 1
                    except Exception:
                        pass

                for att in trust_chain.attestations:
                    try:
                        is_revoked = revocation_registry.is_revoked(att.attestation_id)
                        await conn.execute(
                            """INSERT INTO attestations
                               (id, subject_id, witness_id, task, evidence_uri, signature, witness_pubkey, timestamp, is_revoked)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                               ON CONFLICT DO NOTHING""",
                            att.attestation_id, att.subject, att.witness, att.task,
                            att.evidence, att.signature, att.witness_pubkey,
                            att.timestamp, is_revoked,
                        )
                        att_count += 1
                    except Exception:
                        pass

        return {"agents": agents_count, "attestations": att_count}


# ─── Helpers ───────────────────────────────────────────────────────

def _now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    """Return current UTC time as ISO string (for dict returns)."""
    return _now().isoformat()


def _record_to_dict(record: asyncpg.Record) -> dict:
    """Convert asyncpg Record to plain dict."""
    return dict(record)


# ─── Convenience: module-level singleton ───────────────────────────

_default_db: Optional[Database] = None


async def get_db(db_path: str = "") -> Database:
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
