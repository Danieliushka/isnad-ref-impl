"""Tests for isnad.pricing — trust-based dynamic pricing."""

import pytest
from isnad.pricing import (
    PricingTier, TrustPricingPolicy, PriceQuote, 
    price_for_agent, DiscountType,
)


class TestPricingTier:
    def test_matches_in_range(self):
        tier = PricingTier("basic", 0.0, 0.5, 0.01)
        assert tier.matches(0.0)
        assert tier.matches(0.25)
        assert tier.matches(0.49)
        assert not tier.matches(0.5)
    
    def test_matches_unbounded(self):
        tier = PricingTier("premium", 0.9, float('inf'), 0.001)
        assert tier.matches(0.9)
        assert tier.matches(0.99)
        assert tier.matches(100.0)
        assert not tier.matches(0.89)
    
    def test_to_dict_and_back(self):
        tier = PricingTier("test", 0.5, float('inf'), 0.005, "SOL")
        d = tier.to_dict()
        assert d["max_score"] == "inf"
        restored = PricingTier.from_dict(d)
        assert restored.max_score == float('inf')
        assert restored.price_currency == "SOL"


class TestTrustPricingPolicy:
    def test_base_price_no_tiers(self):
        policy = TrustPricingPolicy("API", base_price=0.01)
        quote = policy.get_price(0.5)
        assert quote.final_price == 0.01
        assert quote.tier_name == "base"
        assert quote.discount_pct == 0.0
    
    def test_tiered_pricing(self):
        policy = TrustPricingPolicy("API", base_price=0.01)
        policy.add_tier("trusted", 0.5, 0.8, 0.005)
        policy.add_tier("premium", 0.8, float('inf'), 0.001)
        
        # Below all tiers
        q1 = policy.get_price(0.3)
        assert q1.final_price == 0.01
        assert q1.tier_name == "base"
        
        # In trusted tier
        q2 = policy.get_price(0.6)
        assert q2.final_price == 0.005
        assert q2.tier_name == "trusted"
        assert q2.discount_pct == 50.0
        
        # In premium tier
        q3 = policy.get_price(0.95)
        assert q3.final_price == 0.001
        assert q3.tier_name == "premium"
        assert q3.discount_pct == 90.0
    
    def test_min_trust_score_denied(self):
        policy = TrustPricingPolicy("Premium API", base_price=0.05, min_trust_score=0.3)
        assert policy.get_price(0.1) is None
        assert policy.get_price(0.29) is None
        assert policy.get_price(0.3) is not None
    
    def test_free_above_threshold(self):
        policy = TrustPricingPolicy("API", base_price=0.01, free_above=0.95)
        
        q1 = policy.get_price(0.5)
        assert q1.final_price == 0.01
        assert not q1.is_free
        
        q2 = policy.get_price(0.95)
        assert q2.final_price == 0.0
        assert q2.is_free
        assert q2.discount_pct == 100.0
        assert q2.tier_name == "free"
    
    def test_chaining(self):
        policy = (TrustPricingPolicy("API", 0.01)
                  .add_tier("silver", 0.5, 0.7, 0.007)
                  .add_tier("gold", 0.7, 0.9, 0.003)
                  .add_tier("platinum", 0.9, float('inf'), 0.001))
        assert len(policy.tiers) == 3
        # Tiers should be sorted
        assert policy.tiers[0].name == "silver"
        assert policy.tiers[2].name == "platinum"
    
    def test_serialization(self):
        policy = TrustPricingPolicy("Test", 0.05, min_trust_score=0.2, free_above=0.99)
        policy.add_tier("basic", 0.3, 0.7, 0.03)
        
        d = policy.to_dict()
        restored = TrustPricingPolicy.from_dict(d)
        
        assert restored.service_name == "Test"
        assert restored.base_price == 0.05
        assert restored.min_trust_score == 0.2
        assert restored.free_above == 0.99
        assert len(restored.tiers) == 1
        assert restored.tiers[0].name == "basic"
    
    def test_zero_base_price(self):
        policy = TrustPricingPolicy("Free API", base_price=0.0)
        policy.add_tier("paid", 0.0, 0.5, 0.01)
        
        q = policy.get_price(0.3)
        assert q.final_price == 0.01
        assert q.discount_pct == 0.0  # no discount on zero base


class TestPriceQuote:
    def test_summary_free(self):
        q = PriceQuote("API", 0.01, 0.0, "USDC", 0.95, "free", 100.0, "free tier")
        assert "FREE" in q.summary()
        assert q.is_free
    
    def test_summary_discount(self):
        q = PriceQuote("API", 0.01, 0.005, "USDC", 0.7, "trusted", 50.0, "tier")
        s = q.summary()
        assert "50%" in s
        assert "0.005" in s
    
    def test_summary_full_price(self):
        q = PriceQuote("API", 0.01, 0.01, "USDC", 0.2, "base", 0.0, "base")
        s = q.summary()
        assert "0.01" in s


class TestPriceForAgent:
    def test_convenience_function(self):
        policy = TrustPricingPolicy("Test", 0.01)
        policy.add_tier("trusted", 0.7, 0.9, 0.005)
        
        q = price_for_agent(policy, 0.85)
        assert q is not None
        assert q.final_price == 0.005
    
    def test_denied(self):
        policy = TrustPricingPolicy("Test", 0.01, min_trust_score=0.5)
        assert price_for_agent(policy, 0.3) is None


class TestEdgeCases:
    def test_overlapping_tiers(self):
        """Last matching tier wins for overlaps."""
        policy = TrustPricingPolicy("API", 0.01)
        policy.add_tier("a", 0.3, 0.8, 0.007)
        policy.add_tier("b", 0.5, 0.9, 0.003)
        
        # Score 0.6 matches both — last one (b) wins
        q = policy.get_price(0.6)
        assert q.tier_name == "b"
    
    def test_exact_boundary(self):
        policy = TrustPricingPolicy("API", 0.01)
        policy.add_tier("low", 0.0, 0.5, 0.008)
        policy.add_tier("high", 0.5, 1.0, 0.003)
        
        # Exactly 0.5 should match "high" (min inclusive, max exclusive)
        q = policy.get_price(0.5)
        assert q.tier_name == "high"
    
    def test_negative_trust_score(self):
        policy = TrustPricingPolicy("API", 0.01, min_trust_score=0.0)
        assert policy.get_price(-0.1) is None
    
    def test_discount_type_enum(self):
        assert DiscountType.PERCENTAGE.value == "percentage"
        assert DiscountType.TIERED.value == "tiered"
