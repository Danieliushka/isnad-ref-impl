"""Internal DB collector — attestations from PostgreSQL."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InternalData:
    attestations: list[dict] = field(default_factory=list)
    attestations_from_established: int = 0
    attestations_from_emerging: int = 0
    negative_attestations: int = 0


async def fetch_internal_data(db, agent_id: str) -> InternalData:
    """Fetch attestation data from the isnad database."""
    data = InternalData()
    if db is None:
        return data

    try:
        async with db._pool.acquire() as conn:
            # Get attestations for this agent
            rows = await conn.fetch(
                "SELECT * FROM attestations WHERE subject_id = $1 AND is_revoked = FALSE",
                agent_id,
            )
            data.attestations = [dict(r) for r in rows]

            # Count negative attestations
            neg_rows = await conn.fetch(
                "SELECT COUNT(*) as cnt FROM attestations WHERE subject_id = $1 AND is_revoked = FALSE AND is_negative = TRUE",
                agent_id,
            )
            data.negative_attestations = neg_rows[0]["cnt"] if neg_rows else 0

            # Count attestations from established/emerging agents
            established = await conn.fetch(
                """SELECT COUNT(DISTINCT a.witness_id) as cnt
                   FROM attestations a
                   JOIN agents ag ON ag.id = a.witness_id
                   WHERE a.subject_id = $1 AND a.is_revoked = FALSE
                   AND ag.trust_score >= 60""",
                agent_id,
            )
            data.attestations_from_established = established[0]["cnt"] if established else 0

            emerging = await conn.fetch(
                """SELECT COUNT(DISTINCT a.witness_id) as cnt
                   FROM attestations a
                   JOIN agents ag ON ag.id = a.witness_id
                   WHERE a.subject_id = $1 AND a.is_revoked = FALSE
                   AND ag.trust_score >= 20 AND ag.trust_score < 60""",
                agent_id,
            )
            data.attestations_from_emerging = emerging[0]["cnt"] if emerging else 0

    except Exception as e:
        logger.warning("Internal data fetch failed for %s: %s", agent_id, e)

    return data
