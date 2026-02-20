"""
isnad.x402 — HTTP 402 payment verification with trust-based pricing.

Bridges isnad trust scores with the x402 protocol (Coinbase),
enabling trust-aware API monetization:
- High-trust agents get discounts or free access
- Unknown agents pay full price
- Revoked agents are denied
"""

import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from enum import Enum


class PaymentStatus(Enum):
    """Status of an x402 payment."""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class PaymentChain(Enum):
    """Supported blockchain networks for x402."""
    BASE = "base"
    BASE_SEPOLIA = "base-sepolia"
    ETHEREUM = "ethereum"
    SOLANA = "solana"
    POLYGON = "polygon"


@dataclass
class PaymentRequirement:
    """x402 payment requirement returned in 402 responses.

    Compatible with x402 protocol PaymentRequirement schema.
    Extended with isnad trust-based pricing.
    """
    amount: str  # Amount in smallest unit (wei, lamports, etc.)
    currency: str  # e.g. "USDC", "ETH"
    chain: PaymentChain
    recipient: str  # Wallet address
    description: str = ""
    resource: str = ""  # The API endpoint being accessed
    # isnad extensions
    trust_discount_pct: float = 0.0  # Discount for trusted agents
    min_trust_score: float = 0.0  # Minimum trust to access at all

    def to_header(self) -> str:
        """Serialize to x402 Payment-Requirement header value."""
        data = {
            "amount": self.amount,
            "currency": self.currency,
            "chain": self.chain.value,
            "recipient": self.recipient,
        }
        if self.description:
            data["description"] = self.description
        if self.resource:
            data["resource"] = self.resource
        return json.dumps(data)

    @classmethod
    def from_header(cls, header: str) -> "PaymentRequirement":
        """Parse from x402 Payment-Requirement header."""
        data = json.loads(header)
        return cls(
            amount=data["amount"],
            currency=data["currency"],
            chain=PaymentChain(data["chain"]),
            recipient=data["recipient"],
            description=data.get("description", ""),
            resource=data.get("resource", ""),
        )


@dataclass
class PaymentProof:
    """Proof of payment for x402 verification.

    Submitted via the Payment header in HTTP requests.
    """
    tx_hash: str
    chain: PaymentChain
    payer: str  # Payer wallet address
    amount: str
    currency: str
    timestamp: float = 0.0
    # isnad: optional agent identity binding
    agent_did: Optional[str] = None  # isnad agent DID
    attestation_hash: Optional[str] = None  # Hash of isnad attestation

    def to_header(self) -> str:
        """Serialize to x402 Payment header value."""
        data = {
            "tx_hash": self.tx_hash,
            "chain": self.chain.value,
            "payer": self.payer,
            "amount": self.amount,
            "currency": self.currency,
        }
        if self.agent_did:
            data["x-isnad-did"] = self.agent_did
        if self.attestation_hash:
            data["x-isnad-attestation"] = self.attestation_hash
        return json.dumps(data)

    @classmethod
    def from_header(cls, header: str) -> "PaymentProof":
        """Parse from x402 Payment header."""
        data = json.loads(header)
        return cls(
            tx_hash=data["tx_hash"],
            chain=PaymentChain(data["chain"]),
            payer=data["payer"],
            amount=data["amount"],
            currency=data["currency"],
            agent_did=data.get("x-isnad-did"),
            attestation_hash=data.get("x-isnad-attestation"),
        )


@dataclass
class PaymentRecord:
    """Record of a verified payment, stored in trust chain."""
    requirement: PaymentRequirement
    proof: PaymentProof
    status: PaymentStatus
    verified_at: float = 0.0
    trust_score_at_payment: float = 0.0
    discount_applied: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class TrustPricingEngine:
    """Calculates dynamic pricing based on agent trust scores.

    Integrates isnad trust data with x402 payment requirements.
    Higher trust = lower price (earned through reputation).
    """

    def __init__(
        self,
        base_amount: str,
        currency: str = "USDC",
        chain: PaymentChain = PaymentChain.BASE,
        recipient: str = "",
        *,
        free_above: float = 0.95,  # Trust score above this = free
        discount_tiers: Optional[List[tuple]] = None,  # [(min_score, discount_pct), ...]
        min_trust: float = 0.0,  # Below this = denied
    ):
        self.base_amount = int(base_amount)
        self.currency = currency
        self.chain = chain
        self.recipient = recipient
        self.free_above = free_above
        self.min_trust = min_trust
        self.discount_tiers = sorted(
            discount_tiers or [
                (0.8, 50.0),   # 80%+ trust = 50% discount
                (0.6, 25.0),   # 60%+ trust = 25% discount
                (0.4, 10.0),   # 40%+ trust = 10% discount
            ],
            key=lambda t: t[0],
            reverse=True,  # Check highest tier first
        )

    def get_requirement(
        self,
        resource: str,
        trust_score: float = 0.0,
        description: str = "",
    ) -> Optional[PaymentRequirement]:
        """Generate payment requirement adjusted for trust score.

        Returns None if agent qualifies for free access.
        Raises ValueError if agent is below minimum trust.
        """
        if trust_score < self.min_trust:
            raise ValueError(
                f"Trust score {trust_score:.2f} below minimum {self.min_trust:.2f}"
            )

        if trust_score >= self.free_above:
            return None  # Free access for highly trusted agents

        discount = 0.0
        for min_score, disc_pct in self.discount_tiers:
            if trust_score >= min_score:
                discount = disc_pct
                break

        adjusted = int(self.base_amount * (1 - discount / 100))

        return PaymentRequirement(
            amount=str(adjusted),
            currency=self.currency,
            chain=self.chain,
            recipient=self.recipient,
            resource=resource,
            description=description or f"Access to {resource}",
            trust_discount_pct=discount,
            min_trust_score=self.min_trust,
        )

    def verify_sufficient(
        self, requirement: PaymentRequirement, proof: PaymentProof
    ) -> bool:
        """Check if payment proof meets requirement amount."""
        return int(proof.amount) >= int(requirement.amount)


class PaymentLedger:
    """In-memory ledger of x402 payments linked to agent identities.

    Provides payment history lookup and aggregate stats per agent.
    """

    def __init__(self):
        self._records: List[PaymentRecord] = []
        self._by_agent: Dict[str, List[PaymentRecord]] = {}
        self._by_tx: Dict[str, PaymentRecord] = {}

    def record_payment(self, record: PaymentRecord) -> None:
        """Add a payment record to the ledger."""
        self._records.append(record)
        self._by_tx[record.proof.tx_hash] = record
        if record.proof.agent_did:
            self._by_agent.setdefault(record.proof.agent_did, []).append(record)

    def get_by_tx(self, tx_hash: str) -> Optional[PaymentRecord]:
        """Look up payment by transaction hash."""
        return self._by_tx.get(tx_hash)

    def get_agent_payments(self, agent_did: str) -> List[PaymentRecord]:
        """Get all payments by an agent."""
        return self._by_agent.get(agent_did, [])

    def agent_total_paid(self, agent_did: str) -> int:
        """Total amount paid by an agent (in smallest unit)."""
        return sum(
            int(r.proof.amount)
            for r in self.get_agent_payments(agent_did)
            if r.status == PaymentStatus.VERIFIED
        )

    def agent_total_saved(self, agent_did: str) -> int:
        """Total discount amount saved by an agent due to trust."""
        return sum(
            int(r.discount_applied)
            for r in self.get_agent_payments(agent_did)
            if r.status == PaymentStatus.VERIFIED
        )

    @property
    def total_records(self) -> int:
        return len(self._records)

    @property
    def total_verified(self) -> int:
        return sum(1 for r in self._records if r.status == PaymentStatus.VERIFIED)
