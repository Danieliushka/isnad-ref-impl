"""Background asyncio worker that periodically scans agent platforms.

Configuration via environment:
    WORKER_INTERVAL  — scan interval in seconds (default 3600 = 1h)
    RATE_LIMIT_RPS   — max requests per second (default 5)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

from .connectors import get_connector_for_url
from .connectors.base import ConnectorResult

logger = logging.getLogger(__name__)


class PlatformWorker:
    """Background worker that scans agent platforms and stores results."""

    def __init__(self, db, *, interval: int | None = None, rate_limit_rps: float | None = None):
        self.db = db
        self.interval = interval or int(os.environ.get("WORKER_INTERVAL", "3600"))
        self.rate_limit_rps = rate_limit_rps or float(os.environ.get("RATE_LIMIT_RPS", "5"))
        self._task: asyncio.Task | None = None
        self._running = False
        self._min_delay = 1.0 / self.rate_limit_rps  # seconds between requests
        self._last_request_time = 0.0

    async def start(self) -> None:
        """Start the background scan loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("PlatformWorker started (interval=%ds, rate_limit=%.1f rps)",
                     self.interval, self.rate_limit_rps)

    async def stop(self) -> None:
        """Stop the background loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("PlatformWorker stopped")

    async def _loop(self) -> None:
        """Main scan loop."""
        while self._running:
            try:
                await self.scan_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker scan cycle failed")
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    async def scan_all(self) -> int:
        """Scan all agents with platforms. Returns number of platforms scanned."""
        logger.info("Starting platform scan cycle")
        count = 0

        try:
            agents = await self.db.list_agents(limit=10000, offset=0)
        except Exception:
            logger.exception("Failed to list agents")
            return 0

        for agent in agents:
            agent_id = agent["id"]
            platforms_raw = agent.get("platforms", "[]")
            if isinstance(platforms_raw, str):
                try:
                    platforms = json.loads(platforms_raw)
                except Exception:
                    continue
            else:
                platforms = platforms_raw

            if not isinstance(platforms, list):
                continue

            for plat in platforms:
                if not isinstance(plat, dict):
                    continue
                url = plat.get("url", "")
                name = plat.get("name", "")
                if not url:
                    continue

                try:
                    result = await self._fetch_with_rate_limit(url)
                    await self._store_result(agent_id, name, url, result)
                    count += 1
                    logger.debug("Scanned %s for agent %s: alive=%s",
                                 url, agent_id, result["alive"])
                except Exception:
                    logger.exception("Failed to scan %s for agent %s", url, agent_id)

        logger.info("Platform scan cycle complete: %d platforms scanned", count)
        return count

    async def scan_agent(self, agent_id: str) -> list[ConnectorResult]:
        """Scan a single agent's platforms (for manual trigger)."""
        agent = await self.db.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        platforms_raw = agent.get("platforms", "[]")
        if isinstance(platforms_raw, str):
            platforms = json.loads(platforms_raw)
        else:
            platforms = platforms_raw

        results = []
        for plat in (platforms or []):
            if not isinstance(plat, dict):
                continue
            url = plat.get("url", "")
            name = plat.get("name", "")
            if not url:
                continue

            result = await self._fetch_with_rate_limit(url)
            await self._store_result(agent_id, name, url, result)
            results.append(result)

        return results

    async def _fetch_with_rate_limit(self, url: str) -> ConnectorResult:
        """Fetch with rate limiting."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_delay:
            await asyncio.sleep(self._min_delay - elapsed)

        connector = get_connector_for_url(url)
        result = await connector.fetch(url)
        self._last_request_time = time.monotonic()
        return result

    async def _store_result(self, agent_id: str, platform_name: str,
                            url: str, result: ConnectorResult) -> None:
        """Store connector result in platform_data table."""
        # Check if entry exists
        existing = await self.db.get_platform_data(agent_id)
        found = None
        for entry in existing:
            if entry.get("platform_url") == url or entry.get("platform_name") == platform_name:
                found = entry
                break

        now = datetime.now(timezone.utc).isoformat()

        if found:
            # Update existing
            async with self.db._pool.acquire() as conn:
                await conn.execute(
                    """UPDATE platform_data
                       SET raw_data = $1, metrics = $2, last_fetched = $3
                       WHERE id = $4""",
                    json.dumps(result["raw_data"]),
                    json.dumps(result["metrics"]),
                    now,
                    found["id"],
                )
        else:
            # Create new
            await self.db.create_platform_data(
                agent_id=agent_id,
                platform_name=result["platform"],
                platform_url=url,
                raw_data=result["raw_data"],
                metrics=result["metrics"],
            )
