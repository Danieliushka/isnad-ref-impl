"""
L0 Intent — Agent declares intent to perform an action.

An Intent is a signed declaration: "I, agent X, intend to do Y by time Z."
It is the atomic unit of the isnad intent-commit protocol.

Flow: Agent creates Intent → signs it → publishes to chain → executes → commits result.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IntentStatus(str, Enum):
    """Lifecycle states of an intent."""
    DECLARED = "declared"       # Agent published intent
    ENDORSED = "endorsed"       # At least one peer endorsed
    IN_PROGRESS = "in_progress" # Execution started
    COMMITTED = "committed"     # Result committed with evidence
    EXPIRED = "expired"         # Deadline passed without commit
    REVOKED = "revoked"         # Agent revoked before commit


class Intent(BaseModel):
    """
    L0 Intent declaration.

    Fields:
        intent_id:   Deterministic hash of (agent_id, action, nonce)
        agent_id:    Declaring agent's isnad ID
        action:      Human-readable action description
        action_type: Machine-readable category (e.g. "code_commit", "data_fetch", "payment")
        target:      What/who the action targets (optional)
        deadline:    Unix timestamp — intent expires after this
        nonce:       Unique per intent to prevent replay
        metadata:    Arbitrary key-value context
        signature:   Ed25519 signature over canonical payload
        status:      Current lifecycle state
        created_at:  ISO 8601 creation time
    """
    intent_id: str = Field(default="", description="Deterministic hash of (agent_id, action, nonce)")
    agent_id: str = Field(..., description="Declaring agent's isnad ID")
    action: str = Field(..., description="Human-readable action description")
    action_type: str = Field(default="generic", description="Machine-readable category")
    target: Optional[str] = Field(default=None, description="Target agent/resource")
    deadline: int = Field(
        default_factory=lambda: int(time.time()) + 3600,
        description="Unix timestamp expiry"
    )
    nonce: str = Field(
        default_factory=lambda: hashlib.sha256(
            f"{time.time_ns()}".encode()
        ).hexdigest()[:16],
        description="Replay-prevention nonce"
    )
    metadata: dict = Field(default_factory=dict)
    signature: Optional[str] = Field(default=None, description="Ed25519 hex signature")
    status: IntentStatus = Field(default=IntentStatus.DECLARED)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def model_post_init(self, __context) -> None:
        if not self.intent_id:
            self.intent_id = self._compute_id()

    def _compute_id(self) -> str:
        """Deterministic intent ID from agent + action + nonce."""
        payload = f"{self.agent_id}:{self.action}:{self.nonce}"
        return f"intent:{hashlib.sha256(payload.encode()).hexdigest()[:24]}"

    def canonical_payload(self) -> bytes:
        """Canonical bytes for signing — deterministic JSON of core fields."""
        obj = {
            "agent_id": self.agent_id,
            "action": self.action,
            "action_type": self.action_type,
            "target": self.target,
            "deadline": self.deadline,
            "nonce": self.nonce,
            "metadata": self.metadata,
        }
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, identity) -> "Intent":
        """Sign this intent with an AgentIdentity. Returns self for chaining."""
        sig = identity.sign(self.canonical_payload())
        self.signature = sig.hex()
        return self

    def verify(self, verify_key) -> bool:
        """Verify signature against a VerifyKey."""
        if not self.signature:
            return False
        try:
            verify_key.verify(self.canonical_payload(), bytes.fromhex(self.signature))
            return True
        except Exception:
            return False

    def is_expired(self) -> bool:
        return time.time() > self.deadline

    def commit(self, evidence_hash: str = "") -> "Intent":
        """Mark intent as committed with optional evidence hash."""
        self.status = IntentStatus.COMMITTED
        self.metadata["committed_at"] = datetime.now(timezone.utc).isoformat()
        if evidence_hash:
            self.metadata["evidence_hash"] = evidence_hash
        return self

    def revoke(self, reason: str = "") -> "Intent":
        """Revoke this intent."""
        self.status = IntentStatus.REVOKED
        self.metadata["revoked_at"] = datetime.now(timezone.utc).isoformat()
        if reason:
            self.metadata["revoke_reason"] = reason
        return self
