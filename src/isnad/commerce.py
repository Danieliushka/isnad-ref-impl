"""
isnad.commerce — Trust primitives for agent-to-agent commerce.

Provides:
- ServiceListing: signed service offerings with terms
- TradeAttestation: cryptographic proof of completed trades
- DisputeRecord: signed dispute with evidence chain
- EscrowVerification: verify escrow lock/release attestations
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError
from .core import AgentIdentity, Attestation


@dataclass
class ServiceTerms:
    """Machine-readable service terms."""
    price_amount: float
    price_currency: str  # e.g. "USDC", "SOL", "USD"
    delivery_time_seconds: int
    scope: str  # what the service covers
    revisions: int = 0
    cancellation_window_seconds: int = 3600

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ServiceTerms":
        return cls(**d)


@dataclass
class ServiceListing:
    """A signed service offering from an agent."""
    provider_id: str
    service_name: str
    description: str
    terms: ServiceTerms
    capabilities: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    signature: Optional[bytes] = None

    def signing_payload(self) -> bytes:
        data = {
            "provider_id": self.provider_id,
            "service_name": self.service_name,
            "description": self.description,
            "terms": self.terms.to_dict(),
            "capabilities": self.capabilities,
            "created_at": self.created_at,
        }
        return json.dumps(data, sort_keys=True).encode()

    def sign(self, identity: AgentIdentity) -> "ServiceListing":
        """Sign this listing with the provider's identity."""
        self.signature = identity.sign(self.signing_payload())
        return self

    def verify(self, identity: AgentIdentity) -> bool:
        """Verify listing signature against provider's public key."""
        if not self.signature:
            return False
        try:
            vk = VerifyKey(identity.public_key_hex.encode(), encoder=HexEncoder)
            vk.verify(self.signing_payload(), self.signature)
            return True
        except (BadSignatureError, Exception):
            return False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["terms"] = self.terms.to_dict()
        if self.signature:
            d["signature"] = self.signature.hex()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ServiceListing":
        sig = bytes.fromhex(d.pop("signature")) if d.get("signature") else None
        terms = ServiceTerms.from_dict(d.pop("terms"))
        listing = cls(terms=terms, **d)
        listing.signature = sig
        return listing


@dataclass
class TradeRecord:
    """Record of a completed trade between two agents."""
    trade_id: str
    buyer_id: str
    seller_id: str
    service_name: str
    terms: ServiceTerms
    initiated_at: float
    completed_at: Optional[float] = None
    status: str = "pending"  # pending, completed, disputed, cancelled
    buyer_rating: Optional[int] = None  # 1-5
    seller_rating: Optional[int] = None  # 1-5

    def complete(self, buyer_rating: int = 5, seller_rating: int = 5) -> "TradeRecord":
        self.status = "completed"
        self.completed_at = time.time()
        self.buyer_rating = max(1, min(5, buyer_rating))
        self.seller_rating = max(1, min(5, seller_rating))
        return self

    def create_completion_attestation(
        self, attester: AgentIdentity, subject_id: str
    ) -> Attestation:
        """Create an isnad attestation for trade completion."""
        evidence_data = json.dumps({
            "trade_id": self.trade_id,
            "service": self.service_name,
            "rating": self.buyer_rating if subject_id == self.seller_id else self.seller_rating,
            "price": f"{self.terms.price_amount} {self.terms.price_currency}",
            "delivery_time": (self.completed_at or 0) - self.initiated_at,
        })
        att = Attestation(
            subject=subject_id,
            witness=attester.agent_id,
            task=f"trade_completed:{self.trade_id}",
            evidence=evidence_data,
        )
        att.sign(attester)
        return att

    def to_dict(self) -> dict:
        d = asdict(self)
        d["terms"] = self.terms.to_dict()
        return d


@dataclass
class DisputeRecord:
    """A dispute with evidence chain, signed by the disputing party."""
    dispute_id: str
    trade_id: str
    filed_by: str  # agent ID
    reason: str
    evidence: list[str] = field(default_factory=list)
    filed_at: float = field(default_factory=time.time)
    resolution: Optional[str] = None
    resolved_at: Optional[float] = None

    def resolve(self, resolution: str) -> "DisputeRecord":
        self.resolution = resolution
        self.resolved_at = time.time()
        return self

    def create_dispute_attestation(self, attester: AgentIdentity, subject_id: str) -> Attestation:
        """Create an isnad attestation recording the dispute."""
        att = Attestation(
            subject=subject_id,
            witness=attester.agent_id,
            task=f"trade_disputed:{self.trade_id}",
            evidence=json.dumps({"reason": self.reason, "evidence": self.evidence}),
        )
        att.sign(attester)
        return att


class CommerceRegistry:
    """Registry of service listings and trade history.

    Tracks listings, active trades, and generates trust-relevant
    attestations for the isnad chain.
    """

    def __init__(self):
        self._listings: dict[str, list[ServiceListing]] = {}  # provider_id -> listings
        self._trades: dict[str, TradeRecord] = {}  # trade_id -> record
        self._disputes: dict[str, DisputeRecord] = {}  # dispute_id -> record

    def register_service(self, listing: ServiceListing) -> None:
        """Register a signed service listing."""
        if listing.provider_id not in self._listings:
            self._listings[listing.provider_id] = []
        self._listings[listing.provider_id].append(listing)

    def find_services(
        self, capability: Optional[str] = None, max_price: Optional[float] = None
    ) -> list[ServiceListing]:
        """Search for services by capability or max price."""
        results = []
        for listings in self._listings.values():
            for listing in listings:
                if capability and capability not in listing.capabilities:
                    continue
                if max_price and listing.terms.price_amount > max_price:
                    continue
                results.append(listing)
        return results

    def initiate_trade(
        self, trade_id: str, buyer_id: str, listing: ServiceListing
    ) -> TradeRecord:
        """Start a trade based on a service listing."""
        trade = TradeRecord(
            trade_id=trade_id,
            buyer_id=buyer_id,
            seller_id=listing.provider_id,
            service_name=listing.service_name,
            terms=listing.terms,
            initiated_at=time.time(),
        )
        self._trades[trade_id] = trade
        return trade

    def complete_trade(
        self, trade_id: str, buyer_rating: int = 5, seller_rating: int = 5
    ) -> TradeRecord:
        """Mark a trade as completed with ratings."""
        trade = self._trades[trade_id]
        trade.complete(buyer_rating, seller_rating)
        return trade

    def file_dispute(self, dispute: DisputeRecord) -> None:
        """File a dispute for a trade."""
        if dispute.trade_id in self._trades:
            self._trades[dispute.trade_id].status = "disputed"
        self._disputes[dispute.dispute_id] = dispute

    def get_trade_history(self, agent_id: str) -> list[TradeRecord]:
        """Get all trades for an agent (as buyer or seller)."""
        return [
            t for t in self._trades.values()
            if t.buyer_id == agent_id or t.seller_id == agent_id
        ]

    def get_completion_rate(self, agent_id: str) -> float:
        """Calculate trade completion rate for an agent."""
        trades = self.get_trade_history(agent_id)
        if not trades:
            return 0.0
        completed = sum(1 for t in trades if t.status == "completed")
        return completed / len(trades)

    def get_average_rating(self, agent_id: str, as_role: str = "seller") -> float:
        """Get average rating for an agent as buyer or seller."""
        trades = [t for t in self.get_trade_history(agent_id) if t.status == "completed"]
        if not trades:
            return 0.0
        if as_role == "seller":
            ratings = [t.buyer_rating for t in trades if t.seller_id == agent_id and t.buyer_rating]
        else:
            ratings = [t.seller_rating for t in trades if t.buyer_id == agent_id and t.seller_rating]
        return sum(ratings) / len(ratings) if ratings else 0.0
