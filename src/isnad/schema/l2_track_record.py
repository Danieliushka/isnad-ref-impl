"""
L2 Track Record — Aggregated history of an agent's fulfilled intents.

A TrackRecord summarises an agent's commitment reliability:
how many intents declared, how many committed, expired, revoked,
and the endorsement ratio. This feeds directly into the trust score.
"""

import time
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class TrackEntry(BaseModel):
    """Single entry in an agent's track record."""
    intent_id: str
    action_type: str
    status: str               # committed | expired | revoked
    endorsement_count: int = 0
    rejection_count: int = 0
    committed_at: Optional[str] = None
    deadline: int = 0
    on_time: bool = True      # committed before deadline?

    @property
    def net_endorsements(self) -> int:
        return self.endorsement_count - self.rejection_count


class TrackRecord(BaseModel):
    """
    L2 Track Record for an agent.

    Computed from the set of L0 Intents and L1 Endorsements.
    """
    agent_id: str
    entries: List[TrackEntry] = Field(default_factory=list)
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── Aggregate metrics ───────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def committed(self) -> int:
        return sum(1 for e in self.entries if e.status == "committed")

    @property
    def expired(self) -> int:
        return sum(1 for e in self.entries if e.status == "expired")

    @property
    def revoked(self) -> int:
        return sum(1 for e in self.entries if e.status == "revoked")

    @property
    def on_time_rate(self) -> float:
        """Fraction of committed intents delivered before deadline."""
        committed = [e for e in self.entries if e.status == "committed"]
        if not committed:
            return 0.0
        return sum(1 for e in committed if e.on_time) / len(committed)

    @property
    def commitment_rate(self) -> float:
        """Fraction of declared intents that were committed (not expired/revoked)."""
        if not self.entries:
            return 0.0
        return self.committed / self.total

    @property
    def endorsement_ratio(self) -> float:
        """Average net endorsements per committed entry."""
        committed = [e for e in self.entries if e.status == "committed"]
        if not committed:
            return 0.0
        return sum(e.net_endorsements for e in committed) / len(committed)

    def add_entry(self, entry: TrackEntry) -> None:
        self.entries.append(entry)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def summary(self) -> dict:
        """Compact summary for API responses and scoring."""
        return {
            "agent_id": self.agent_id,
            "total_intents": self.total,
            "committed": self.committed,
            "expired": self.expired,
            "revoked": self.revoked,
            "commitment_rate": round(self.commitment_rate, 3),
            "on_time_rate": round(self.on_time_rate, 3),
            "endorsement_ratio": round(self.endorsement_ratio, 2),
            "updated_at": self.updated_at,
        }
