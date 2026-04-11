"""
Clawk Agent Reputation Collector — fetches agent data from Clawk.ai.

API: GET /api/v1/agents/{NAME}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CLAWK_BASE_URL = "https://clawk.ai"
TIMEOUT = 15.0


@dataclass
class ClawkData:
    """Collected agent data from Clawk.ai."""
    found: bool = False
    name: str = ""
    follower_count: int = 0
    clawk_count: int = 0              # posts
    onchain_reputation_score: float = 0.0
    erc8004_verified: bool = False
    status: str = ""
    error: Optional[str] = None


async def fetch_clawk_profile(name: str) -> ClawkData:
    """Fetch agent profile from Clawk.ai.

    Args:
        name: Agent username on Clawk.

    Returns:
        ClawkData with agent info, or empty data on failure.
    """
    if not name:
        return ClawkData()

    url = f"{CLAWK_BASE_URL}/api/v1/agents/{name}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)

            if resp.status_code == 404:
                logger.debug("Clawk agent not found: %s", name)
                return ClawkData(name=name)

            if resp.status_code != 200:
                logger.warning("Clawk API returned %d for %s", resp.status_code, name)
                return ClawkData(name=name, error=f"HTTP {resp.status_code}")

            data = resp.json()
            agent = data.get("agent", data)  # API wraps in {"agent": {...}}

            return ClawkData(
                found=True,
                name=name,
                follower_count=int(agent.get("follower_count") or 0),
                clawk_count=int(agent.get("clawk_count") or 0),
                onchain_reputation_score=float(agent.get("onchain_reputation_score") or 0),
                erc8004_verified=bool(agent.get("erc8004_verified")),
                status=str(agent.get("status") or ""),
            )

    except httpx.TimeoutException:
        logger.warning("Clawk API timeout for %s", name)
        return ClawkData(name=name, error="timeout")
    except Exception as e:
        logger.warning("Clawk API error for %s: %s", name, e)
        return ClawkData(name=name, error=str(e))
