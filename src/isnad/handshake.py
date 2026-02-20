"""
isnad.handshake — Multi-Agent Trust Handshake Protocol

Enables two agents to establish mutual trust before collaboration:
1. Initiator sends HandshakeRequest (signed, with capabilities needed)
2. Responder verifies identity, checks trust score, sends HandshakeResponse
3. Both sides have a signed HandshakeSession they can reference

Use cases:
- Agent-to-agent API calls with trust verification
- Multi-agent task delegation (e.g., La Movida workflows)
- Trust-gated resource sharing
"""

import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from enum import Enum

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError

from .core import AgentIdentity


class HandshakeStatus(Enum):
    """Status of a handshake."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class HandshakeRequest:
    """Request from initiator to establish trust session."""
    request_id: str
    initiator_id: str
    initiator_pubkey: str
    responder_id: str
    capabilities_needed: list[str] = field(default_factory=list)
    proposed_duration_s: float = 3600.0  # 1 hour default
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0
    signature: str = ""

    def signable_payload(self) -> bytes:
        data = {
            "request_id": self.request_id,
            "initiator_id": self.initiator_id,
            "responder_id": self.responder_id,
            "capabilities_needed": sorted(self.capabilities_needed),
            "proposed_duration_s": self.proposed_duration_s,
            "timestamp": self.timestamp,
        }
        return json.dumps(data, sort_keys=True).encode()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HandshakeResponse:
    """Response from responder accepting/rejecting handshake."""
    request_id: str
    responder_id: str
    responder_pubkey: str
    status: HandshakeStatus = HandshakeStatus.PENDING
    granted_capabilities: list[str] = field(default_factory=list)
    trust_score: float = 0.0
    session_duration_s: float = 3600.0
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0
    signature: str = ""

    def signable_payload(self) -> bytes:
        data = {
            "request_id": self.request_id,
            "responder_id": self.responder_id,
            "status": self.status.value,
            "granted_capabilities": sorted(self.granted_capabilities),
            "trust_score": self.trust_score,
            "session_duration_s": self.session_duration_s,
            "timestamp": self.timestamp,
        }
        return json.dumps(data, sort_keys=True).encode()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class HandshakeSession:
    """Active trust session between two agents."""
    session_id: str
    initiator_id: str
    responder_id: str
    capabilities: list[str]
    trust_score: float
    created_at: float
    expires_at: float
    request_signature: str
    response_signature: str

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def remaining_s(self) -> float:
        return max(0, self.expires_at - time.time())

    def to_dict(self) -> dict:
        return asdict(self)


class TrustPolicy:
    """Policy for accepting/rejecting handshakes based on trust scores."""

    def __init__(
        self,
        min_trust: float = 0.0,
        max_duration_s: float = 86400.0,
        allowed_capabilities: Optional[list[str]] = None,
        require_known_agent: bool = False,
    ):
        self.min_trust = min_trust
        self.max_duration_s = max_duration_s
        self.allowed_capabilities = allowed_capabilities
        self.require_known_agent = require_known_agent

    def evaluate(
        self, request: HandshakeRequest, trust_score: float, is_known: bool
    ) -> tuple[HandshakeStatus, list[str], str]:
        """Evaluate a handshake request against this policy.
        
        Returns (status, granted_capabilities, reason).
        """
        if self.require_known_agent and not is_known:
            return HandshakeStatus.REJECTED, [], "unknown agent"

        if trust_score < self.min_trust:
            return (
                HandshakeStatus.REJECTED, [],
                f"trust score {trust_score:.2f} below minimum {self.min_trust:.2f}"
            )

        duration = min(request.proposed_duration_s, self.max_duration_s)

        if self.allowed_capabilities is not None:
            granted = [
                c for c in request.capabilities_needed
                if c in self.allowed_capabilities
            ]
        else:
            granted = list(request.capabilities_needed)

        return HandshakeStatus.ACCEPTED, granted, "ok"


class HandshakeManager:
    """Manages handshake lifecycle for an agent."""

    def __init__(self, identity: AgentIdentity, policy: Optional[TrustPolicy] = None):
        self.identity = identity
        self.policy = policy or TrustPolicy()
        self._pending: Dict[str, HandshakeRequest] = {}
        self._sessions: Dict[str, HandshakeSession] = {}

    def create_request(
        self,
        responder_id: str,
        capabilities: list[str],
        duration_s: float = 3600.0,
        metadata: Optional[dict] = None,
    ) -> HandshakeRequest:
        """Create and sign a handshake request."""
        now = time.time()
        req_id = hashlib.sha256(
            f"{self.identity.agent_id}:{responder_id}:{now}".encode()
        ).hexdigest()[:16]

        request = HandshakeRequest(
            request_id=req_id,
            initiator_id=self.identity.agent_id,
            initiator_pubkey=self.identity.signing_key.verify_key.encode(HexEncoder).decode(),
            responder_id=responder_id,
            capabilities_needed=capabilities,
            proposed_duration_s=duration_s,
            metadata=metadata or {},
            timestamp=now,
        )

        sig = self.identity.signing_key.sign(request.signable_payload())
        request.signature = sig.signature.hex()
        return request

    def receive_request(
        self,
        request: HandshakeRequest,
        trust_score: float = 0.0,
        is_known: bool = True,
    ) -> HandshakeResponse:
        """Process an incoming handshake request and return response."""
        # Verify signature
        if not self._verify_request_signature(request):
            return HandshakeResponse(
                request_id=request.request_id,
                responder_id=self.identity.agent_id,
                responder_pubkey=self.identity.signing_key.verify_key.encode(HexEncoder).decode(),
                status=HandshakeStatus.REJECTED,
                metadata={"reason": "invalid signature"},
                timestamp=time.time(),
            )

        # Check if request is for us
        if request.responder_id != self.identity.agent_id:
            return HandshakeResponse(
                request_id=request.request_id,
                responder_id=self.identity.agent_id,
                responder_pubkey=self.identity.signing_key.verify_key.encode(HexEncoder).decode(),
                status=HandshakeStatus.REJECTED,
                metadata={"reason": "wrong responder"},
                timestamp=time.time(),
            )

        # Evaluate against policy
        status, granted, reason = self.policy.evaluate(request, trust_score, is_known)

        duration = min(request.proposed_duration_s, self.policy.max_duration_s)

        response = HandshakeResponse(
            request_id=request.request_id,
            responder_id=self.identity.agent_id,
            responder_pubkey=self.identity.signing_key.verify_key.encode(HexEncoder).decode(),
            status=status,
            granted_capabilities=granted,
            trust_score=trust_score,
            session_duration_s=duration,
            metadata={"reason": reason},
            timestamp=time.time(),
        )

        # Sign response
        sig = self.identity.signing_key.sign(response.signable_payload())
        response.signature = sig.signature.hex()

        # If accepted, create session
        if status == HandshakeStatus.ACCEPTED:
            session = HandshakeSession(
                session_id=request.request_id,
                initiator_id=request.initiator_id,
                responder_id=self.identity.agent_id,
                capabilities=granted,
                trust_score=trust_score,
                created_at=response.timestamp,
                expires_at=response.timestamp + duration,
                request_signature=request.signature,
                response_signature=response.signature,
            )
            self._sessions[session.session_id] = session

        return response

    def complete_handshake(
        self, request: HandshakeRequest, response: HandshakeResponse
    ) -> Optional[HandshakeSession]:
        """Complete handshake on initiator side after receiving response."""
        if response.status != HandshakeStatus.ACCEPTED:
            return None

        if not self._verify_response_signature(response):
            return None

        session = HandshakeSession(
            session_id=request.request_id,
            initiator_id=self.identity.agent_id,
            responder_id=response.responder_id,
            capabilities=response.granted_capabilities,
            trust_score=response.trust_score,
            created_at=response.timestamp,
            expires_at=response.timestamp + response.session_duration_s,
            request_signature=request.signature,
            response_signature=response.signature,
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[HandshakeSession]:
        """Get active session by ID."""
        session = self._sessions.get(session_id)
        if session and session.is_expired:
            del self._sessions[session_id]
            return None
        return session

    def active_sessions(self) -> List[HandshakeSession]:
        """List all active (non-expired) sessions."""
        now = time.time()
        expired = [k for k, v in self._sessions.items() if v.expires_at < now]
        for k in expired:
            del self._sessions[k]
        return list(self._sessions.values())

    def revoke_session(self, session_id: str) -> bool:
        """Revoke an active session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def _verify_request_signature(self, request: HandshakeRequest) -> bool:
        try:
            vk = VerifyKey(bytes.fromhex(request.initiator_pubkey))
            vk.verify(request.signable_payload(), bytes.fromhex(request.signature))
            return True
        except (BadSignatureError, Exception):
            return False

    def _verify_response_signature(self, response: HandshakeResponse) -> bool:
        try:
            vk = VerifyKey(bytes.fromhex(response.responder_pubkey))
            vk.verify(response.signable_payload(), bytes.fromhex(response.signature))
            return True
        except (BadSignatureError, Exception):
            return False
