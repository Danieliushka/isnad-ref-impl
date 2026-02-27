"""Management command: recalculate scores for all agents."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import asyncpg

from .engine import ScoringEngine, ScoreBreakdown
from .github_collector import fetch_github_data, extract_github_username

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql://isnad:isnad_secret@localhost:5432/isnad_db"


async def recalculate_agent(conn: asyncpg.Connection, agent: dict, engine: ScoringEngine) -> ScoreBreakdown:
    """Recalculate score for a single agent."""
    agent_id = agent["id"]
    agent_dict = dict(agent)

    # Get attestations
    attestations = await conn.fetch(
        "SELECT * FROM attestations WHERE subject_id = $1 AND is_revoked = FALSE",
        agent_id,
    )
    attestations = [dict(a) for a in attestations]

    # Get GitHub data if available
    platforms = agent_dict.get("platforms", [])
    if isinstance(platforms, str):
        try:
            platforms = json.loads(platforms)
        except Exception:
            platforms = []

    github_data = None
    gh_username = extract_github_username(platforms)
    if gh_username:
        logger.info("  Fetching GitHub data for %s...", gh_username)
        github_data = await fetch_github_data(gh_username)
        if github_data:
            logger.info("  GitHub: %d repos, %d stars, %d followers, age=%d days",
                        github_data.public_repos, github_data.total_stars,
                        github_data.followers, github_data.account_age_days)

    # Compute score
    breakdown = engine.compute(agent_dict, attestations, github_data)

    # Save to DB
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        "UPDATE agents SET trust_score = $1, last_checked = $2 WHERE id = $3",
        breakdown.total_score, now, agent_id,
    )

    # Save breakdown to trust_checks
    report = {
        "total_score": breakdown.total_score,
        "tier": breakdown.tier,
        "categories": [
            {
                "name": c.name,
                "raw_score": c.raw_score,
                "max_points": c.max_points,
                "normalized": c.normalized,
                "weighted": c.weighted,
                "details": c.details,
            }
            for c in breakdown.categories
        ],
        "github_data": breakdown.github_data,
    }
    await conn.execute(
        """INSERT INTO trust_checks (agent_id, requested_at, score, report, requester_ip)
           VALUES ($1, $2, $3, $4, $5)""",
        agent_id, now, breakdown.total_score / 100.0, json.dumps(report), "scoring-engine",
    )

    return breakdown


async def recalculate_all():
    """Recalculate scores for all agents."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        agents = await conn.fetch("SELECT * FROM agents ORDER BY name")
        engine = ScoringEngine()

        logger.info("Recalculating scores for %d agents...", len(agents))

        for agent in agents:
            name = agent.get("name", agent["id"])
            logger.info("Processing: %s", name)
            try:
                breakdown = await recalculate_agent(conn, agent, engine)
                logger.info("  → Score: %.1f (%s)", breakdown.total_score, breakdown.tier)
                for c in breakdown.categories:
                    logger.info("    %s: %.1f/%.0f (normalized: %.1f)", c.name, c.raw_score, c.max_points, c.normalized)
            except Exception as e:
                logger.error("  Failed: %s", e)

        logger.info("Done!")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(recalculate_all())
