"""Intent-Commit data models (L0-L3)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class IntentLevel(IntEnum):
    """Escalating levels of intent commitment."""
    L0 = 0  # Plaintext declaration
    L1 = 1  # Hash commitment (SHA-256 + nonce)
    L2 = 2  # Signed commitment + scope binding
    L3 = 3  # Multi-party witnessed commitment


class CommitmentStatus(str):
    COMMITTED = "committed"
    REVEALED = "revealed"
    EXPIRED = "expired"
    VIOLATED = "violated"


class IntentScope(BaseModel):
    """Declared scope for L2+ commitments."""
    tools: list[str] = Field(default_factory=list, description="Allowed tool identifiers")
    resources: list[str] = Field(default_factory=list, description="Allowed resource URIs")
    max_actions: Optional[int] = Field(None, description="Max number of actions permitted")
    timeout_seconds: Optional[int] = Field(None, description="Max duration in seconds")
    max_value_usd: Optional[float] = Field(None, description="Max monetary value (L3)")


class WitnessAck(BaseModel):
    """Witness acknowledgment for L3 commitments."""
    agent_id: str
    pubkey: str
    ack_signature: str
    ack_timestamp: datetime


class IntentCommitment(BaseModel):
    """A commitment at any level (L0-L3)."""
    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    level: IntentLevel
    commitment_hash: Optional[str] = None  # SHA-256 hex (L1+)
    scope: Optional[IntentScope] = None  # L2+
    signature: Optional[str] = None  # Ed25519 sig (L2+)
    witnesses: list[WitnessAck] = Field(default_factory=list)  # L3
    committed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revealed_at: Optional[datetime] = None
    intent_plaintext: Optional[str] = None
    nonce: Optional[str] = None
    status: str = CommitmentStatus.COMMITTED


class IntentCommitRequest(BaseModel):
    """Request to create a new commitment."""
    agent_id: str
    level: IntentLevel
    intent_plaintext: Optional[str] = None  # Required for L0, optional for L1+ (revealed later)
    scope: Optional[IntentScope] = None  # Required for L2+
    commitment_hash: Optional[str] = None  # Required for L1+ (pre-computed by agent)
    signature: Optional[str] = None  # Required for L2+


class IntentRevealRequest(BaseModel):
    """Request to reveal a committed intent."""
    commitment_id: UUID
    intent_plaintext: str
    nonce: str
    timestamp: str  # ISO format, must match what was hashed


def compute_commitment_hash(intent: str, nonce: str, timestamp: str) -> str:
    """Compute SHA-256(intent || nonce || timestamp) as hex string."""
    payload = f"{intent}{nonce}{timestamp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_nonce() -> str:
    """Generate a cryptographically secure nonce."""
    return secrets.token_hex(16)


def verify_reveal(commitment_hash: str, intent: str, nonce: str, timestamp: str) -> bool:
    """Verify that a reveal matches the stored commitment hash."""
    computed = compute_commitment_hash(intent, nonce, timestamp)
    return secrets.compare_digest(computed, commitment_hash)
