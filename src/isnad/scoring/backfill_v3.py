"""Backfill all agents with v3 scores."""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill():
    from isnad.database import Database
    from isnad.scoring.engine_v3 import ScoringEngineV3

    db = Database()
    await db.connect()

    engine = ScoringEngineV3(db=db)

    async with db._pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM agents ORDER BY created_at")

    logger.info("Backfilling %d agents with v3 scoring...", len(rows))

    for row in rows:
        agent = dict(row)
        try:
            result = await engine.compute_and_store(agent)
            logger.info(
                "  %s (%s): score=%d confidence=%.2f tier=%s",
                agent.get("name", "?"), agent["id"][:8],
                result.final_score, result.confidence, result.tier,
            )
        except Exception as e:
            logger.error("  Failed for %s: %s", agent.get("name", agent["id"]), e)

    await db.close()
    logger.info("Backfill complete.")


def main():
    asyncio.run(backfill())


if __name__ == "__main__":
    main()
