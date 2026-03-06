"""
CoinPay DID Reputation Collector — fetches reputation data from CoinPayPortal.

API: GET /api/reputation/agent/{did}/reputation
Docs: https://coinpayportal.com/docs#reputation

Returns trust vector (E,P,B,D,R,A,C) and window stats (7d, 30d, 90d, lifetime).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

COINPAY_BASE_URL = "https://coinpayportal.com"
TIMEOUT = 10.0


@dataclass
class CoinPayTrustVector:
    """7-dimension trust vector from CoinPay CPTL v2."""
    economic: float = 0.0       # E — economic activity score
    productivity: float = 0.0   # P — task completion score
    behavioral: float = 0.0     # B — dispute rate (higher = fewer disputes)
    diversity: float = 0.0      # D — unique counterparties
    recency: float = 0.0        # R — time-decay multiplier
    anomaly: float = 0.0        # A — anomaly penalty (0 = clean)
    compliance: float = 0.0     # C — compliance penalty (0 = clean)


@dataclass
class CoinPayData:
    """Collected reputation data from CoinPayPortal."""
    found: bool = False
    did: str = ""
    score: float = 0.0           # overall score (0-5 scale)
    total_tasks: int = 0
    success_rate: float = 0.0    # 0.0-1.0
    trust_vector: CoinPayTrustVector = field(default_factory=CoinPayTrustVector)
    # Window stats (lifetime)
    lifetime_volume_usd: float = 0.0
    lifetime_dispute_rate: float = 0.0
    unique_buyers: int = 0
    error: Optional[str] = None


async def fetch_coinpay_reputation(did: str) -> CoinPayData:
    """Fetch reputation data for a DID from CoinPayPortal.
    
    Args:
        did: A CoinPay DID string, e.g. "did:coinpay:abc123" or "did:key:z6Mk..."
    
    Returns:
        CoinPayData with reputation information, or empty data if not found.
    """
    if not did:
        return CoinPayData()

    url = f"{COINPAY_BASE_URL}/api/reputation/agent/{did}/reputation"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)

            if resp.status_code == 404:
                logger.debug("CoinPay DID not found: %s", did)
                return CoinPayData(did=did)

            if resp.status_code != 200:
                logger.warning("CoinPay API returned %d for %s", resp.status_code, did)
                return CoinPayData(did=did, error=f"HTTP {resp.status_code}")

            data = resp.json()
            if not data.get("success"):
                return CoinPayData(did=did, error="API returned success=false")

            # Parse trust vector (top-level key)
            tv = CoinPayTrustVector()
            tv_data = data.get("trust_vector") or {}
            if tv_data:
                tv.economic = float(tv_data.get("E", 0))
                tv.productivity = float(tv_data.get("P", 0))
                tv.behavioral = float(tv_data.get("B", 0))
                tv.diversity = float(tv_data.get("D", 0))
                tv.recency = float(tv_data.get("R", 0))
                tv.anomaly = float(tv_data.get("A", 0))
                tv.compliance = float(tv_data.get("C", 0))

            # Score from trust_tier (not top-level)
            trust_tier = data.get("trust_tier") or {}
            score = float(trust_tier.get("score", 0))

            # Window stats from reputation.windows.all_time
            rep = data.get("reputation") or {}
            windows = rep.get("windows") or {}
            all_time = windows.get("all_time") or {}

            total_tasks = int(all_time.get("task_count", 0))
            accepted = int(all_time.get("accepted_count", 0))
            success_rate = float(all_time.get("accepted_rate", 0))
            # If accepted_rate not provided, compute from counts
            if success_rate == 0 and total_tasks > 0:
                success_rate = accepted / total_tasks

            return CoinPayData(
                found=True,
                did=did,
                score=score,
                total_tasks=total_tasks,
                success_rate=success_rate,
                trust_vector=tv,
                lifetime_volume_usd=float(all_time.get("total_volume", 0)),
                lifetime_dispute_rate=float(all_time.get("dispute_rate", 0)),
                unique_buyers=int(all_time.get("unique_buyers", 0)),
            )

    except httpx.TimeoutException:
        logger.warning("CoinPay API timeout for %s", did)
        return CoinPayData(did=did, error="timeout")
    except Exception as e:
        logger.warning("CoinPay API error for %s: %s", did, e)
        return CoinPayData(did=did, error=str(e))
