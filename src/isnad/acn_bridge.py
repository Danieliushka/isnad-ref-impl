#!/usr/bin/env python3
"""
ACN Bridge — Agent Credit Network ↔ isnad Trust Score bidirectional mapping.

PoC scaffold for Risueno collaboration: maps traditional credit scores (300–850)
to isnad trust scores (0.0–1.0) and back, with on-chain oracle integration stubs
for Base Sepolia testnet via Chainlink.

Usage:
    bridge = ACNBridge()
    trust = bridge.credit_to_trust(720)        # -> TrustScore ~0.76
    credit = bridge.trust_to_credit(0.76)      # -> ~720.0
    att = bridge.create_attestation("agent:abc", 720, trust.score)
    assert bridge.verify_attestation(att)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ─── Data Types ────────────────────────────────────────────────────

@dataclass
class TrustScore:
    """Trust score with metadata."""
    score: float          # 0.0–1.0
    confidence: float     # 0.0–1.0, how reliable the mapping is
    source: str = "acn_bridge"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass
class MappingCurve:
    """Configurable mapping curve parameters.

    The mapping uses a power curve: normalized = ((credit - min) / (max - min)) ^ exponent
    - exponent=1.0 → linear
    - exponent>1.0 → rewards higher credit scores more
    - exponent<1.0 → diminishing returns at top end
    """
    credit_min: float = 300.0
    credit_max: float = 850.0
    exponent: float = 1.0       # 1.0 = linear, >1 = convex, <1 = concave
    trust_floor: float = 0.0    # minimum trust score output
    trust_ceiling: float = 1.0  # maximum trust score output


# ─── ACN Bridge ────────────────────────────────────────────────────

class ACNBridge:
    """Bidirectional mapping between credit scores and isnad trust scores."""

    ACN_ATTESTATION_VERSION = "0.1.0"

    def __init__(self, curve: Optional[MappingCurve] = None):
        self.curve = curve or MappingCurve()

    def credit_to_trust(self, credit_score: float) -> TrustScore:
        """Map a credit score (300–850) to a TrustScore (0–1).

        Clamps input to [credit_min, credit_max], applies power curve,
        scales to [trust_floor, trust_ceiling].
        """
        c = self.curve
        clamped = max(c.credit_min, min(c.credit_max, credit_score))
        normalized = (clamped - c.credit_min) / (c.credit_max - c.credit_min)
        curved = math.pow(normalized, c.exponent)
        score = c.trust_floor + curved * (c.trust_ceiling - c.trust_floor)

        # Confidence is lower at extremes and for out-of-range inputs
        in_range = c.credit_min <= credit_score <= c.credit_max
        confidence = 0.95 if in_range else 0.5

        return TrustScore(score=round(score, 6), confidence=confidence)

    def trust_to_credit(self, trust_score: float) -> float:
        """Reverse mapping: trust score (0–1) → credit score (300–850).

        Inverts the power curve applied in credit_to_trust.
        """
        c = self.curve
        clamped = max(c.trust_floor, min(c.trust_ceiling, trust_score))
        # Invert the floor/ceiling scaling
        range_width = c.trust_ceiling - c.trust_floor
        if range_width == 0:
            normalized = 0.0
        else:
            normalized = (clamped - c.trust_floor) / range_width
        # Invert the power curve
        if c.exponent == 0:
            inv = 0.0
        else:
            inv = math.pow(normalized, 1.0 / c.exponent)
        return round(c.credit_min + inv * (c.credit_max - c.credit_min), 2)

    def create_attestation(
        self,
        agent_id: str,
        credit_score: float,
        trust_score: float,
    ) -> dict:
        """Create an isnad-style attestation linking credit and trust scores.

        Returns a dict compatible with isnad attestation format, containing
        both scores, mapping metadata, and an integrity hash.
        """
        ts = datetime.now(timezone.utc).isoformat()
        payload = {
            "version": self.ACN_ATTESTATION_VERSION,
            "type": "acn_credit_trust_mapping",
            "subject": agent_id,
            "credit_score": credit_score,
            "trust_score": trust_score,
            "curve": {
                "exponent": self.curve.exponent,
                "credit_range": [self.curve.credit_min, self.curve.credit_max],
                "trust_range": [self.curve.trust_floor, self.curve.trust_ceiling],
            },
            "timestamp": ts,
        }
        # Integrity hash over canonical payload
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload["integrity_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        return payload

    def verify_attestation(self, attestation: dict) -> bool:
        """Verify attestation integrity hash.

        Checks that the integrity_hash matches the canonical payload.
        """
        try:
            att = dict(attestation)
            stored_hash = att.pop("integrity_hash", None)
            if not stored_hash:
                return False
            canonical = json.dumps(att, sort_keys=True, separators=(",", ":"))
            expected = hashlib.sha256(canonical.encode()).hexdigest()
            return stored_hash == expected
        except Exception:
            return False


# ─── Chainlink Oracle Adapter (Stub) ──────────────────────────────

class ChainlinkAdapter:
    """Stub adapter for Chainlink oracle on Base Sepolia.

    In production, this would use web3.py to interact with a Chainlink
    oracle contract that stores agent trust/credit scores on-chain.

    Config via env vars:
        BASE_SEPOLIA_RPC_URL   — RPC endpoint (default: https://sepolia.base.org)
        ACN_ORACLE_CONTRACT    — Oracle contract address
        ACN_PRIVATE_KEY        — Wallet private key for tx signing
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        contract_address: Optional[str] = None,
    ):
        self.rpc_url = rpc_url or os.environ.get(
            "BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"
        )
        self.contract_address = contract_address or os.environ.get(
            "ACN_ORACLE_CONTRACT", ""
        )
        self._store: dict[str, float] = {}  # in-memory stub

    def push_score(self, agent_id: str, score: float) -> str:
        """Push a score to the on-chain oracle (stub).

        Returns a fake tx hash. In production, sends a transaction
        to the oracle contract's updateScore(agentId, score) function.
        """
        self._store[agent_id] = score
        fake_tx = hashlib.sha256(
            f"{agent_id}:{score}:{time.time()}".encode()
        ).hexdigest()
        return f"0x{fake_tx}"

    def read_score(self, agent_id: str) -> float:
        """Read a score from the on-chain oracle (stub).

        Returns the stored score or 0.0 if not found.
        In production, calls the oracle contract's getScore(agentId) view.
        """
        return self._store.get(agent_id, 0.0)


# ─── API Endpoint Helper ──────────────────────────────────────────

def acn_map_handler(request_body: dict) -> dict:
    """Handler for POST /acn/map endpoint.

    Request body:
        {
            "agent_id": "agent:abc123",
            "credit_score": 720,          // optional, provide one
            "trust_score": 0.76,          // optional, provide one
            "curve_exponent": 1.0         // optional
        }

    Response:
        {
            "agent_id": "...",
            "credit_score": 720,
            "trust_score": {...},
            "attestation": {...}
        }

    Add to api_server.py:
        @app.post("/acn/map")
        async def acn_map(body: dict):
            return acn_map_handler(body)
    """
    agent_id = request_body.get("agent_id", "anonymous")
    exponent = request_body.get("curve_exponent", 1.0)
    bridge = ACNBridge(curve=MappingCurve(exponent=exponent))

    credit = request_body.get("credit_score")
    trust = request_body.get("trust_score")

    if credit is not None:
        trust_result = bridge.credit_to_trust(credit)
        attestation = bridge.create_attestation(agent_id, credit, trust_result.score)
        return {
            "agent_id": agent_id,
            "direction": "credit_to_trust",
            "credit_score": credit,
            "trust_score": trust_result.to_dict(),
            "attestation": attestation,
        }
    elif trust is not None:
        credit_result = bridge.trust_to_credit(trust)
        attestation = bridge.create_attestation(agent_id, credit_result, trust)
        return {
            "agent_id": agent_id,
            "direction": "trust_to_credit",
            "credit_score": credit_result,
            "trust_score": trust,
            "attestation": attestation,
        }
    else:
        return {"error": "Provide either credit_score or trust_score"}
