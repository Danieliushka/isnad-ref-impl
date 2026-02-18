#!/usr/bin/env python3
"""isnad quickstart — full trust chain in under 50 lines.

Run:  python3 examples/quickstart.py
"""
from isnad import (
    AgentIdentity, Attestation, TrustChain,
    ServiceListing, CommerceRegistry,
)
from isnad.commerce import ServiceTerms

# 1. Create agents (each gets a unique keypair)
alice = AgentIdentity()
bob = AgentIdentity()
carol = AgentIdentity()

print(f"👤 Alice: {alice.agent_id[:24]}…")
print(f"👤 Bob:   {bob.agent_id[:24]}…")
print(f"👤 Carol: {carol.agent_id[:24]}…")

# 2. Build attestations: Carol vouches for Alice, Alice vouches for Bob
att1 = Attestation(
    subject=alice.agent_id, witness=carol.agent_id,
    task="identity-verification", evidence="Verified via Clawk profile"
)
att1.sign(carol)

att2 = Attestation(
    subject=bob.agent_id, witness=alice.agent_id,
    task="commerce-capability", evidence="Completed 3 test trades"
)
att2.sign(alice)

# 3. Build and verify trust chain
chain = TrustChain()
chain.add(att1)
chain.add(att2)
score = chain.trust_score(bob.agent_id)
print(f"\n🔒 Trust chain built: {len(chain.attestations)} attestations")
print(f"📊 Bob's trust score: {score:.3f}")

# 4. Agent commerce: list a service and execute a trade
registry = CommerceRegistry()
terms = ServiceTerms(
    price_amount=50.0, price_currency="USD",
    delivery_time_seconds=86400, scope="data-analysis",
)
listing = ServiceListing(
    provider_id=alice.agent_id,
    service_name="ML Data Analysis",
    description="Machine learning pipeline for structured data",
    terms=terms, capabilities=["python", "sklearn", "pandas"],
)
registry.register_service(listing)
print(f"\n🏪 Service listed: {listing.service_name} @ ${terms.price_amount}")

trade = registry.initiate_trade(
    trade_id="trade-001", buyer_id=bob.agent_id, listing=listing,
)
registry.complete_trade(trade.trade_id, buyer_rating=5, seller_rating=4)
print(f"✅ Trade {trade.trade_id} completed! Buyer: 5★, Seller: 4★")
print(f"📈 Alice completion rate: {registry.get_completion_rate(alice.agent_id):.0%}")
print(f"📈 Alice avg rating: {registry.get_average_rating(alice.agent_id):.1f}★")

print("\n🎉 Full isnad flow: identity → attestation → trust score → commerce")
