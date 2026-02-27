#!/usr/bin/env python3
"""Daily trust score recalculation for all agents.

Connects directly to the database, computes trust scores using the same
logic as the GET /api/v1/agents/{agent_id}/trust-score endpoint, and
updates the agents table.

Usage:
    python scripts/recalculate_scores.py          # recalculate all
    python scripts/recalculate_scores.py --dry-run # show scores without updating
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import sys
from datetime import datetime, timezone

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("recalculate_scores")

# ---------------------------------------------------------------------------
# Trust score computation (mirrors api_v1._compute_trust_score)
# ---------------------------------------------------------------------------

_TRUST_WEIGHTS = {
    "attestation_count": 0.30,
    "source_diversity": 0.25,
    "registration_age": 0.25,
    "verification_status": 0.20,
}


def compute_trust_score(
    attestation_count: int,
    source_diversity: int,
    registration_age_days: int,
    is_verified: bool,
    is_certified: bool,
) -> int:
    """Compute trust score (0-100) from components."""
    if attestation_count == 0:
        att_score = 0.0
    else:
        att_score = min(math.log2(attestation_count + 1) / math.log2(11) * 100, 100.0)

    if source_diversity == 0:
        div_score = 0.0
    else:
        div_score = min(math.log2(source_diversity + 1) / math.log2(6) * 100, 100.0)

    age_score = min(registration_age_days / 365.0 * 100, 100.0)

    ver_score = 0.0
    if is_certified:
        ver_score += 60.0
    if is_verified:
        ver_score += 40.0
    ver_score = min(ver_score, 100.0)

    overall = (
        att_score * _TRUST_WEIGHTS["attestation_count"]
        + div_score * _TRUST_WEIGHTS["source_diversity"]
        + age_score * _TRUST_WEIGHTS["registration_age"]
        + ver_score * _TRUST_WEIGHTS["verification_status"]
    )
    return round(overall)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def recalculate(dry_run: bool = False) -> dict:
    """Recalculate trust scores for all agents. Returns summary stats."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            agents = await conn.fetch("SELECT id, created_at, is_certified FROM agents")

        now = datetime.now(timezone.utc)
        updated = 0
        errors = 0
        scores: list[tuple[str, int, int]] = []  # (agent_id, old_score, new_score)

        for agent in agents:
            agent_id = agent["id"]
            try:
                async with pool.acquire() as conn:
                    # Attestations
                    att_rows = await conn.fetch(
                        "SELECT witness_id FROM attestations WHERE subject_id = $1", agent_id
                    )
                    attestation_count = len(att_rows)
                    unique_witnesses = len({r["witness_id"] for r in att_rows})

                    # Registration age
                    created_at = agent["created_at"]
                    age_days = 0
                    if created_at:
                        if isinstance(created_at, str):
                            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            created = created_at
                        if created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        age_days = max(0, (now - created).days)

                    is_certified = bool(agent.get("is_certified", False))

                    # Check badges for verification
                    badge_row = await conn.fetchrow(
                        "SELECT 1 FROM badges WHERE agent_id = $1 AND badge_type = 'isnad_verified' LIMIT 1",
                        agent_id,
                    )
                    is_verified = badge_row is not None

                    new_score = compute_trust_score(
                        attestation_count=attestation_count,
                        source_diversity=unique_witnesses,
                        registration_age_days=age_days,
                        is_verified=is_verified,
                        is_certified=is_certified,
                    )

                    # Get old score
                    old_row = await conn.fetchrow(
                        "SELECT trust_score FROM agents WHERE id = $1", agent_id
                    )
                    old_score = int(old_row["trust_score"] or 0) if old_row else 0

                    scores.append((agent_id, old_score, new_score))

                    if not dry_run:
                        await conn.execute(
                            "UPDATE agents SET trust_score = $1, last_checked = $2 WHERE id = $3",
                            float(new_score), now.isoformat(), agent_id,
                        )
                    updated += 1

            except Exception as e:
                log.error("Failed for agent %s: %s", agent_id, e)
                errors += 1

        # Log results
        for agent_id, old, new in scores:
            change = "→" if old == new else ("↑" if new > old else "↓")
            log.info("  %s: %d %s %d", agent_id[:12], old, change, new)

        summary = {
            "total_agents": len(agents),
            "updated": updated,
            "errors": errors,
            "dry_run": dry_run,
            "timestamp": now.isoformat(),
        }
        log.info(
            "Done: %d agents processed, %d updated, %d errors%s",
            len(agents), updated, errors, " (DRY RUN)" if dry_run else "",
        )
        return summary

    finally:
        await pool.close()


def main():
    parser = argparse.ArgumentParser(description="Recalculate trust scores for all agents")
    parser.add_argument("--dry-run", action="store_true", help="Show scores without updating DB")
    args = parser.parse_args()
    asyncio.run(recalculate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
