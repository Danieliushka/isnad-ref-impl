"""
Moltbook Agent Profile Collector — fetches agent reputation from Moltbook.

API: GET /api/v1/agents/profile?name={NAME}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MOLTBOOK_BASE_URL = "https://www.moltbook.com"
TIMEOUT = 15.0


@dataclass
class MoltbookData:
    """Collected profile data from Moltbook."""
    found: bool = False
    name: str = ""
    karma: float = 0.0
    follower_count: int = 0
    posts_count: int = 0
    comments_count: int = 0
    is_verified: bool = False
    last_active: str = ""
    error: Optional[str] = None


async def fetch_moltbook_profile(name: str) -> MoltbookData:
    """Fetch agent profile from Moltbook.

    Args:
        name: Agent username on Moltbook.

    Returns:
        MoltbookData with profile info, or empty data on failure.
    """
    if not name:
        return MoltbookData()

    url = f"{MOLTBOOK_BASE_URL}/api/v1/agents/profile"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params={"name": name})

            if resp.status_code == 404:
                logger.debug("Moltbook agent not found: %s", name)
                return MoltbookData(name=name)

            if resp.status_code != 200:
                logger.warning("Moltbook API returned %d for %s", resp.status_code, name)
                return MoltbookData(name=name, error=f"HTTP {resp.status_code}")

            data = resp.json()
            agent = data.get("agent", data)  # API wraps in {"agent": {...}}

            return MoltbookData(
                found=True,
                name=name,
                karma=float(agent.get("karma") or 0),
                follower_count=int(agent.get("follower_count") or 0),
                posts_count=int(agent.get("posts_count") or 0),
                comments_count=int(agent.get("comments_count") or 0),
                is_verified=bool(agent.get("is_verified")),
                last_active=str(agent.get("last_active") or ""),
            )

    except httpx.TimeoutException:
        logger.warning("Moltbook API timeout for %s", name)
        return MoltbookData(name=name, error="timeout")
    except Exception as e:
        logger.warning("Moltbook API error for %s: %s", name, e)
        return MoltbookData(name=name, error=str(e))
