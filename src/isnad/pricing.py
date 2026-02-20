"""
isnad.pricing — Trust-based dynamic pricing for agent services.

Provides:
- PricingTier: define price tiers based on trust score ranges
- TrustPricingPolicy: set pricing rules with trust discounts
- PriceQuote: generated quote with trust-adjusted pricing
- price_for_agent: compute price for an agent based on their trust score
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class DiscountType(Enum):
    """Type of trust-based discount."""
    NONE = "none"
    PERCENTAGE = "percentage"
    FIXED = "fixed"
    TIERED = "tiered"


@dataclass
class PricingTier:
    """A pricing tier based on trust score range.
    
    Agents with trust scores in [min_score, max_score) get this tier's pricing.
    """
    name: str
    min_score: float  # inclusive
    max_score: float  # exclusive (use float('inf') for unbounded)
    price_amount: float
    price_currency: str = "USDC"
    
    def matches(self, score: float) -> bool:
        """Check if a trust score falls within this tier."""
        return self.min_score <= score < self.max_score
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "min_score": self.min_score,
            "max_score": self.max_score if self.max_score != float('inf') else "inf",
            "price_amount": self.price_amount,
            "price_currency": self.price_currency,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "PricingTier":
        max_score = float('inf') if d.get("max_score") == "inf" else d["max_score"]
        return cls(
            name=d["name"],
            min_score=d["min_score"],
            max_score=max_score,
            price_amount=d["price_amount"],
            price_currency=d.get("price_currency", "USDC"),
        )


@dataclass 
class TrustPricingPolicy:
    """Pricing policy with trust-based adjustments.
    
    Supports:
    - Base price for unknown/untrusted agents
    - Tiered pricing based on trust score ranges
    - Minimum trust score to access the service at all
    - Free tier for highly trusted agents
    """
    service_name: str
    base_price: float
    base_currency: str = "USDC"
    min_trust_score: float = 0.0  # minimum score to access service
    tiers: list = field(default_factory=list)  # list of PricingTier
    free_above: Optional[float] = None  # trust score above which service is free
    created_at: float = field(default_factory=time.time)
    
    def add_tier(self, name: str, min_score: float, max_score: float, 
                 price: float, currency: str = "USDC") -> "TrustPricingPolicy":
        """Add a pricing tier. Returns self for chaining."""
        self.tiers.append(PricingTier(
            name=name,
            min_score=min_score,
            max_score=max_score,
            price_amount=price,
            price_currency=currency,
        ))
        # Sort tiers by min_score for consistent lookup
        self.tiers.sort(key=lambda t: t.min_score)
        return self
    
    def get_price(self, trust_score: float) -> Optional["PriceQuote"]:
        """Get price quote for an agent with given trust score.
        
        Returns None if agent doesn't meet minimum trust requirement.
        """
        if trust_score < self.min_trust_score:
            return None  # Access denied
        
        if self.free_above is not None and trust_score >= self.free_above:
            return PriceQuote(
                service_name=self.service_name,
                original_price=self.base_price,
                final_price=0.0,
                currency=self.base_currency,
                trust_score=trust_score,
                tier_name="free",
                discount_pct=100.0,
                reason=f"Trust score {trust_score:.2f} >= free threshold {self.free_above}",
            )
        
        # Find matching tier (last matching tier wins for overlaps)
        matched_tier = None
        for tier in self.tiers:
            if tier.matches(trust_score):
                matched_tier = tier
        
        if matched_tier:
            discount_pct = (1.0 - matched_tier.price_amount / self.base_price) * 100 if self.base_price > 0 else 0.0
            return PriceQuote(
                service_name=self.service_name,
                original_price=self.base_price,
                final_price=matched_tier.price_amount,
                currency=matched_tier.price_currency,
                trust_score=trust_score,
                tier_name=matched_tier.name,
                discount_pct=max(0.0, discount_pct),
                reason=f"Trust tier: {matched_tier.name}",
            )
        
        # No tier matched — use base price
        return PriceQuote(
            service_name=self.service_name,
            original_price=self.base_price,
            final_price=self.base_price,
            currency=self.base_currency,
            trust_score=trust_score,
            tier_name="base",
            discount_pct=0.0,
            reason="No tier matched, using base price",
        )
    
    def to_dict(self) -> dict:
        return {
            "service_name": self.service_name,
            "base_price": self.base_price,
            "base_currency": self.base_currency,
            "min_trust_score": self.min_trust_score,
            "tiers": [t.to_dict() for t in self.tiers],
            "free_above": self.free_above,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "TrustPricingPolicy":
        policy = cls(
            service_name=d["service_name"],
            base_price=d["base_price"],
            base_currency=d.get("base_currency", "USDC"),
            min_trust_score=d.get("min_trust_score", 0.0),
            free_above=d.get("free_above"),
            created_at=d.get("created_at", time.time()),
        )
        for t in d.get("tiers", []):
            policy.tiers.append(PricingTier.from_dict(t))
        return policy


@dataclass
class PriceQuote:
    """A computed price quote for an agent."""
    service_name: str
    original_price: float
    final_price: float
    currency: str
    trust_score: float
    tier_name: str
    discount_pct: float
    reason: str
    generated_at: float = field(default_factory=time.time)
    
    @property
    def is_free(self) -> bool:
        return self.final_price == 0.0
    
    @property
    def is_denied(self) -> bool:
        return False  # PriceQuote is only created for accepted agents
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def summary(self) -> str:
        """Human-readable pricing summary."""
        if self.is_free:
            return f"✅ {self.service_name}: FREE (trust: {self.trust_score:.2f}, {self.reason})"
        if self.discount_pct > 0:
            return (f"💰 {self.service_name}: {self.final_price} {self.currency} "
                    f"({self.discount_pct:.0f}% off, trust: {self.trust_score:.2f}, tier: {self.tier_name})")
        return f"💰 {self.service_name}: {self.final_price} {self.currency} (trust: {self.trust_score:.2f})"


def price_for_agent(policy: TrustPricingPolicy, trust_score: float) -> Optional[PriceQuote]:
    """Convenience function: compute price for an agent given a policy and trust score.
    
    Returns None if agent is denied access (below min trust score).
    
    Example:
        >>> policy = TrustPricingPolicy("API Call", base_price=0.01)
        >>> policy.add_tier("trusted", 0.7, 0.9, 0.005)
        >>> policy.add_tier("highly_trusted", 0.9, float('inf'), 0.001)
        >>> quote = price_for_agent(policy, 0.85)
        >>> quote.final_price
        0.005
    """
    return policy.get_price(trust_score)
