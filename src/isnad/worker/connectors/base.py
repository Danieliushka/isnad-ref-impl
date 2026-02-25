"""Base connector interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict, Literal


class ConnectorMetrics(TypedDict, total=False):
    activity_score: int        # 0-100
    reputation_score: int      # 0-100
    longevity_days: int
    verification_level: str    # none|basic|verified
    evidence_count: int


class ConnectorResult(TypedDict):
    platform: str
    url: str
    alive: bool
    raw_data: dict
    metrics: ConnectorMetrics


class BaseConnector(ABC):
    """Abstract base for all platform connectors."""

    platform_name: str = "unknown"

    @abstractmethod
    async def fetch(self, url: str) -> ConnectorResult:
        """Fetch platform data for the given URL.

        Must return a ConnectorResult even on failure (alive=False).
        """
        ...

    def _dead_result(self, url: str, error: str = "") -> ConnectorResult:
        """Return a result for an unreachable platform."""
        return ConnectorResult(
            platform=self.platform_name,
            url=url,
            alive=False,
            raw_data={"error": error} if error else {},
            metrics=ConnectorMetrics(
                activity_score=0,
                reputation_score=0,
                longevity_days=0,
                verification_level="none",
                evidence_count=0,
            ),
        )
