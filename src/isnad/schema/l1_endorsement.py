"""
L1 Endorsement — Peer endorses an intent or its result.

An Endorsement is a signed statement: "I, agent W, endorse intent I by agent X."
Endorsements are the social proof layer — they turn self-claims into witnessed facts.

Types:
  - PRE_ENDORSEMENT:  "I trust this agent to execute this intent"
  - POST_ENDORSEMENT: "I witnessed successful completion"
  - REJECTION:        "I witnessed failure or fraud"
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EndorsementType(str, Enum):
    PRE = "pre_endorsement"      # Endorsing intent before execution
    POST = "post_endorsement"    # Endorsing result after execution
    REJECTION = "rejection"      # Witnessed failure or fraud


class Endorsement(BaseModel):
    """
    L1 Endorsement of an intent.

    Fields:
        endorsement_id: Deterministic hash of (endorser, intent_id, type)
        intent_id:      The L0 Intent being endorsed
        endorser_id:    Agent providing the endorsement
        endorser_pubkey: Ed25519 public key hex of endorser
        endorsement_type: PRE, POST, or REJECTION
        confidence:     0.0–1.0 confidence in the endorsement
        comment:        Optional human-readable note
        evidence_url:   Optional link to evidence
        signature:      Ed25519 signature over canonical payload
        created_at:     ISO 8601
    """
    endorsement_id: str = Field(default="")
    intent_id: str = Field(..., description="L0 Intent ID being endorsed")
    endorser_id: str = Field(..., description="Endorsing agent's isnad ID")
    endorser_pubkey: Optional[str] = Field(default=None)
    endorsement_type: EndorsementType = Field(default=EndorsementType.POST)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    comment: Optional[str] = Field(default=None)
    evidence_url: Optional[str] = Field(default=None)
    signature: Optional[str] = Field(default=None)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def model_post_init(self, __context) -> None:
        if not self.endorsement_id:
            self.endorsement_id = self._compute_id()

    def _compute_id(self) -> str:
        payload = f"{self.endorser_id}:{self.intent_id}:{self.endorsement_type.value}"
        return f"endorse:{hashlib.sha256(payload.encode()).hexdigest()[:24]}"

    def canonical_payload(self) -> bytes:
        obj = {
            "intent_id": self.intent_id,
            "endorser_id": self.endorser_id,
            "endorsement_type": self.endorsement_type.value,
            "confidence": self.confidence,
            "comment": self.comment,
            "evidence_url": self.evidence_url,
        }
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, identity) -> "Endorsement":
        sig = identity.sign(self.canonical_payload())
        self.signature = sig.hex()
        self.endorser_pubkey = identity.public_key_hex
        return self

    def verify(self, verify_key) -> bool:
        if not self.signature:
            return False
        try:
            verify_key.verify(self.canonical_payload(), bytes.fromhex(self.signature))
            return True
        except Exception:
            return False
