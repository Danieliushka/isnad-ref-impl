"""Platform URL verifier — async HEAD requests."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class PlatformVerification:
    total: int = 0
    verified: int = 0
    name_matches: int = 0


async def verify_platforms(platforms: list[dict], agent_name: str = "") -> PlatformVerification:
    """Verify platform URLs with HEAD requests and check name matches."""
    result = PlatformVerification(total=len(platforms))
    if not platforms:
        return result

    timeout = aiohttp.ClientTimeout(total=10)
    agent_name_lower = agent_name.lower().replace(" ", "").replace("-", "").replace("_", "")

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for p in platforms:
                url = p.get("url", "")
                if not url or not url.startswith("http"):
                    continue
                try:
                    async with session.head(url, allow_redirects=True) as resp:
                        if resp.status < 400:
                            result.verified += 1
                            # Check name match in URL
                            if agent_name_lower and agent_name_lower in url.lower().replace("-", "").replace("_", ""):
                                result.name_matches += 1
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Platform verification error: %s", e)

    return result
