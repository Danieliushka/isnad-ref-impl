"""ugig marketplace data collector for scoring v3."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class UgigData:
    completed_gigs: int = 0
    avg_rating: float = 0.0
    member_since: str = ""
    found: bool = False


def fetch_ugig_data(agent_name: str) -> UgigData:
    """Fetch ugig profile via CLI (synchronous)."""
    if not agent_name:
        return UgigData()
    try:
        result = subprocess.run(
            ["ugig", "profile", "show", agent_name, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return UgigData(
                completed_gigs=data.get("completed_gigs", 0),
                avg_rating=data.get("avg_rating", 0.0),
                member_since=data.get("member_since", ""),
                found=True,
            )
    except FileNotFoundError:
        logger.debug("ugig CLI not found")
    except subprocess.TimeoutExpired:
        logger.warning("ugig CLI timeout for %s", agent_name)
    except Exception as e:
        logger.warning("ugig fetch failed for %s: %s", agent_name, e)
    return UgigData()
