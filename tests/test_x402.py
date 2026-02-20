"""Tests for isnad.x402 — HTTP 402 payment verification with trust pricing."""

import json
import pytest
from isnad.x402 import (
    PaymentRequirement, PaymentProof, PaymentRecord,
    PaymentStatus, PaymentChain,
    TrustPricingEngine, PaymentLedger,
)


class TestPaymentRequirement:
    def test_create_basic(self):
        req = PaymentRequirement(
            amount="1000000",
            currency="USDC",
            chain=PaymentChain.BASE,
            recipient="0xabc123",
        )
        assert req.amount == "1000000"
        assert req.chain == PaymentChain.BASE

    def test_to_header_roundtrip(self):
        req = PaymentRequirement(
            amount="500000",
            currency="USDC",
            chain=PaymentChain.BASE_SEPOLIA,
            recipient="0xdef456",
            description="API call",
            resource="/api/verify",
        )
        header = req.to_header()
        parsed = PaymentRequirement.from_header(header)
        assert parsed.amount == req.amount
        assert parsed.chain == req.chain
        assert parsed.recipient == req.recipient
        assert parsed.description == req.description

    def test_from_header_minimal(self):
        data = json.dumps({
            "amount": "100",
            "currency": "ETH",
            "chain": "ethereum",
            "recipient": "0x123",
        })
        req = PaymentRequirement.from_header(data)
        assert req.chain == PaymentChain.ETHEREUM
        assert req.description == ""


class TestPaymentProof:
    def test_create_with_isnad(self):
        proof = PaymentProof(
            tx_hash="0xabc",
            chain=PaymentChain.SOLANA,
            payer="CZTub123",
            amount="1000000",
            currency="USDC",
            agent_did="did:isnad:agent1",
            attestation_hash="deadbeef",
        )
        assert proof.agent_did == "did:isnad:agent1"

    def test_header_roundtrip_with_isnad(self):
        proof = PaymentProof(
            tx_hash="0xdef",
            chain=PaymentChain.BASE,
            payer="0xpayer",
            amount="500000",
            currency="USDC",
            agent_did="did:isnad:gendolf",
            attestation_hash="cafe",
        )
        header = proof.to_header()
        parsed = PaymentProof.from_header(header)
        assert parsed.tx_hash == proof.tx_hash
        assert parsed.agent_did == "did:isnad:gendolf"
        assert parsed.attestation_hash == "cafe"

    def test_header_without_isnad(self):
        proof = PaymentProof(
            tx_hash="0x111",
            chain=PaymentChain.POLYGON,
            payer="0xp",
            amount="100",
            currency="ETH",
        )
        header = proof.to_header()
        data = json.loads(header)
        assert "x-isnad-did" not in data


class TestTrustPricingEngine:
    def setup_method(self):
        self.engine = TrustPricingEngine(
            base_amount="1000000",
            currency="USDC",
            chain=PaymentChain.BASE,
            recipient="0xservice",
            free_above=0.95,
            min_trust=0.1,
        )

    def test_free_for_high_trust(self):
        req = self.engine.get_requirement("/api/verify", trust_score=0.96)
        assert req is None  # Free access

    def test_full_price_for_low_trust(self):
        req = self.engine.get_requirement("/api/verify", trust_score=0.2)
        assert req is not None
        assert req.amount == "1000000"  # No discount

    def test_discount_for_medium_trust(self):
        req = self.engine.get_requirement("/api/verify", trust_score=0.85)
        assert req is not None
        assert int(req.amount) == 500000  # 50% discount
        assert req.trust_discount_pct == 50.0

    def test_25pct_discount_tier(self):
        req = self.engine.get_requirement("/api/verify", trust_score=0.65)
        assert int(req.amount) == 750000  # 25% discount

    def test_10pct_discount_tier(self):
        req = self.engine.get_requirement("/api/verify", trust_score=0.45)
        assert int(req.amount) == 900000  # 10% discount

    def test_below_min_trust_raises(self):
        with pytest.raises(ValueError, match="below minimum"):
            self.engine.get_requirement("/api/verify", trust_score=0.05)

    def test_zero_trust_with_zero_min(self):
        engine = TrustPricingEngine(
            base_amount="1000",
            currency="USDC",
            chain=PaymentChain.BASE,
            recipient="0x",
            min_trust=0.0,
        )
        req = engine.get_requirement("/test", trust_score=0.0)
        assert req is not None
        assert req.amount == "1000"

    def test_custom_discount_tiers(self):
        engine = TrustPricingEngine(
            base_amount="10000",
            currency="USDC",
            chain=PaymentChain.BASE,
            recipient="0x",
            discount_tiers=[(0.9, 90.0), (0.5, 50.0)],
        )
        req = engine.get_requirement("/test", trust_score=0.92)
        assert int(req.amount) <= 1000  # ~90% off (int truncation)

    def test_verify_sufficient(self):
        req = PaymentRequirement(
            amount="1000", currency="USDC",
            chain=PaymentChain.BASE, recipient="0x",
        )
        proof_ok = PaymentProof(
            tx_hash="0x1", chain=PaymentChain.BASE,
            payer="0xp", amount="1500", currency="USDC",
        )
        proof_low = PaymentProof(
            tx_hash="0x2", chain=PaymentChain.BASE,
            payer="0xp", amount="500", currency="USDC",
        )
        assert self.engine.verify_sufficient(req, proof_ok) is True
        assert self.engine.verify_sufficient(req, proof_low) is False

    def test_description_default(self):
        req = self.engine.get_requirement("/api/data", trust_score=0.3)
        assert "api/data" in req.description

    def test_boundary_free_above(self):
        req = self.engine.get_requirement("/test", trust_score=0.95)
        assert req is None  # Exactly at threshold = free

    def test_boundary_min_trust(self):
        req = self.engine.get_requirement("/test", trust_score=0.1)
        assert req is not None  # Exactly at min = allowed


class TestPaymentLedger:
    def setup_method(self):
        self.ledger = PaymentLedger()

    def _make_record(self, tx="0x1", agent="did:isnad:a1", amount="1000",
                     status=PaymentStatus.VERIFIED, discount=0):
        return PaymentRecord(
            requirement=PaymentRequirement(
                amount=amount, currency="USDC",
                chain=PaymentChain.BASE, recipient="0xr",
            ),
            proof=PaymentProof(
                tx_hash=tx, chain=PaymentChain.BASE,
                payer="0xp", amount=amount, currency="USDC",
                agent_did=agent,
            ),
            status=status,
            discount_applied=discount,
        )

    def test_record_and_lookup(self):
        rec = self._make_record()
        self.ledger.record_payment(rec)
        assert self.ledger.get_by_tx("0x1") is rec
        assert self.ledger.total_records == 1

    def test_agent_payments(self):
        self.ledger.record_payment(self._make_record(tx="0x1"))
        self.ledger.record_payment(self._make_record(tx="0x2"))
        self.ledger.record_payment(self._make_record(tx="0x3", agent="did:isnad:a2"))
        assert len(self.ledger.get_agent_payments("did:isnad:a1")) == 2
        assert len(self.ledger.get_agent_payments("did:isnad:a2")) == 1

    def test_total_paid(self):
        self.ledger.record_payment(self._make_record(tx="0x1", amount="500"))
        self.ledger.record_payment(self._make_record(tx="0x2", amount="300"))
        self.ledger.record_payment(self._make_record(
            tx="0x3", amount="200", status=PaymentStatus.REJECTED
        ))
        assert self.ledger.agent_total_paid("did:isnad:a1") == 800  # Rejected excluded

    def test_total_saved(self):
        self.ledger.record_payment(self._make_record(tx="0x1", discount=100))
        self.ledger.record_payment(self._make_record(tx="0x2", discount=200))
        assert self.ledger.agent_total_saved("did:isnad:a1") == 300

    def test_unknown_agent(self):
        assert self.ledger.get_agent_payments("unknown") == []
        assert self.ledger.agent_total_paid("unknown") == 0

    def test_total_verified(self):
        self.ledger.record_payment(self._make_record(tx="0x1"))
        self.ledger.record_payment(self._make_record(
            tx="0x2", status=PaymentStatus.PENDING
        ))
        assert self.ledger.total_verified == 1
        assert self.ledger.total_records == 2

    def test_no_agent_did(self):
        rec = self._make_record(tx="0x1")
        rec.proof.agent_did = None
        self.ledger.record_payment(rec)
        assert self.ledger.total_records == 1
        assert len(self.ledger._by_agent) == 0  # Not indexed by agent
