"""Tests for isnad.commerce module."""

import pytest
import time
from isnad.core import AgentIdentity
from isnad.commerce import (
    ServiceTerms, ServiceListing, TradeRecord, DisputeRecord, CommerceRegistry
)


@pytest.fixture
def seller():
    return AgentIdentity()


@pytest.fixture
def buyer():
    return AgentIdentity()


@pytest.fixture
def terms():
    return ServiceTerms(
        price_amount=10.0,
        price_currency="USDC",
        delivery_time_seconds=3600,
        scope="AI research report",
        revisions=2,
    )


@pytest.fixture
def listing(seller, terms):
    return ServiceListing(
        provider_id=seller.agent_id,
        service_name="AI Research",
        description="Deep research on AI topics",
        terms=terms,
        capabilities=["research", "analysis", "writing"],
    ).sign(seller)


class TestServiceTerms:
    def test_roundtrip(self, terms):
        d = terms.to_dict()
        restored = ServiceTerms.from_dict(d)
        assert restored.price_amount == 10.0
        assert restored.price_currency == "USDC"
        assert restored.scope == "AI research report"


class TestServiceListing:
    def test_sign_and_verify(self, listing, seller):
        assert listing.verify(seller)

    def test_tampered_listing_fails(self, listing, seller):
        listing.description = "tampered"
        assert not listing.verify(seller)

    def test_wrong_identity_fails(self, listing, buyer):
        assert not listing.verify(buyer)

    def test_unsigned_listing_fails(self, seller, terms):
        listing = ServiceListing(
            provider_id=seller.agent_id,
            service_name="Test",
            description="Test",
            terms=terms,
        )
        assert not listing.verify(seller)

    def test_serialization(self, listing):
        d = listing.to_dict()
        assert d["service_name"] == "AI Research"
        assert "signature" in d
        restored = ServiceListing.from_dict(d)
        assert restored.service_name == listing.service_name


class TestTradeRecord:
    def test_complete_trade(self, terms):
        trade = TradeRecord(
            trade_id="t1",
            buyer_id="buyer",
            seller_id="seller",
            service_name="Test",
            terms=terms,
            initiated_at=time.time(),
        )
        trade.complete(buyer_rating=4, seller_rating=5)
        assert trade.status == "completed"
        assert trade.buyer_rating == 4
        assert trade.completed_at is not None

    def test_rating_clamped(self, terms):
        trade = TradeRecord(
            trade_id="t2", buyer_id="b", seller_id="s",
            service_name="X", terms=terms, initiated_at=time.time(),
        )
        trade.complete(buyer_rating=10, seller_rating=-1)
        assert trade.buyer_rating == 5
        assert trade.seller_rating == 1

    def test_completion_attestation(self, seller, buyer, terms):
        trade = TradeRecord(
            trade_id="t3", buyer_id=buyer.agent_id, seller_id=seller.agent_id,
            service_name="Research", terms=terms, initiated_at=time.time(),
        )
        trade.complete(4, 5)
        att = trade.create_completion_attestation(buyer, seller.agent_id)
        assert "trade_completed:t3" in att.task
        assert att.verify()


class TestDisputeRecord:
    def test_dispute_and_resolve(self):
        dispute = DisputeRecord(
            dispute_id="d1", trade_id="t1", filed_by="buyer",
            reason="Service not delivered", evidence=["no response for 24h"],
        )
        assert dispute.resolution is None
        dispute.resolve("Refund issued")
        assert dispute.resolution == "Refund issued"
        assert dispute.resolved_at is not None

    def test_dispute_attestation(self, buyer, seller):
        dispute = DisputeRecord(
            dispute_id="d2", trade_id="t2", filed_by=buyer.agent_id,
            reason="Quality below spec", evidence=["output_hash:abc123"],
        )
        att = dispute.create_dispute_attestation(buyer, seller.agent_id)
        assert "trade_disputed:t2" in att.task
        assert att.verify()


class TestCommerceRegistry:
    def test_register_and_find(self, listing):
        reg = CommerceRegistry()
        reg.register_service(listing)
        results = reg.find_services(capability="research")
        assert len(results) == 1
        assert results[0].service_name == "AI Research"

    def test_find_by_price(self, listing):
        reg = CommerceRegistry()
        reg.register_service(listing)
        assert len(reg.find_services(max_price=5.0)) == 0
        assert len(reg.find_services(max_price=15.0)) == 1

    def test_trade_lifecycle(self, listing, buyer):
        reg = CommerceRegistry()
        reg.register_service(listing)
        trade = reg.initiate_trade("t1", buyer.agent_id, listing)
        assert trade.status == "pending"
        reg.complete_trade("t1", buyer_rating=5, seller_rating=4)
        assert trade.status == "completed"

    def test_dispute_flow(self, listing, buyer):
        reg = CommerceRegistry()
        reg.register_service(listing)
        trade = reg.initiate_trade("t1", buyer.agent_id, listing)
        dispute = DisputeRecord(
            dispute_id="d1", trade_id="t1", filed_by=buyer.agent_id,
            reason="Not delivered",
        )
        reg.file_dispute(dispute)
        assert trade.status == "disputed"

    def test_completion_rate(self, listing, buyer, seller):
        reg = CommerceRegistry()
        reg.register_service(listing)
        reg.initiate_trade("t1", buyer.agent_id, listing)
        reg.initiate_trade("t2", buyer.agent_id, listing)
        reg.complete_trade("t1")
        assert reg.get_completion_rate(seller.agent_id) == 0.5
        reg.complete_trade("t2")
        assert reg.get_completion_rate(seller.agent_id) == 1.0

    def test_average_rating(self, listing, buyer, seller):
        reg = CommerceRegistry()
        reg.register_service(listing)
        reg.initiate_trade("t1", buyer.agent_id, listing)
        reg.initiate_trade("t2", buyer.agent_id, listing)
        reg.complete_trade("t1", buyer_rating=4)
        reg.complete_trade("t2", buyer_rating=5)
        assert reg.get_average_rating(seller.agent_id, as_role="seller") == 4.5

    def test_trade_history(self, listing, buyer, seller):
        reg = CommerceRegistry()
        reg.register_service(listing)
        reg.initiate_trade("t1", buyer.agent_id, listing)
        assert len(reg.get_trade_history(buyer.agent_id)) == 1
        assert len(reg.get_trade_history(seller.agent_id)) == 1
