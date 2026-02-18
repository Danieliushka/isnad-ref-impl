"""TrustPolicy — Declarative trust requirements for agent interactions.

Agents define policies like "only trade with agents scoring >0.7 who have
at least 3 endorsements and a verified delegation chain". The PolicyEngine
evaluates these against isnad data automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .core import Attestation as IsnadAttestation


class PolicyAction(str, Enum):
    """What to do when policy matches/fails."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_REVIEW = "require_review"
    RATE_LIMIT = "rate_limit"


@dataclass
class TrustRequirement:
    """A single trust condition."""
    min_trust_score: Optional[float] = None
    min_endorsements: Optional[int] = None
    max_chain_length: Optional[int] = None
    required_scopes: Optional[list[str]] = None
    required_issuer_ids: Optional[list[str]] = None
    max_age_seconds: Optional[int] = None

    def evaluate(self, context: "EvaluationContext") -> bool:
        """Check if context meets this requirement."""
        if self.min_trust_score is not None:
            if context.trust_score < self.min_trust_score:
                return False
        if self.min_endorsements is not None:
            if context.endorsement_count < self.min_endorsements:
                return False
        if self.max_chain_length is not None:
            if context.chain_length > self.max_chain_length:
                return False
        if self.required_scopes is not None:
            if not all(s in context.scopes for s in self.required_scopes):
                return False
        if self.required_issuer_ids is not None:
            if not any(i in context.issuer_ids for i in self.required_issuer_ids):
                return False
        if self.max_age_seconds is not None:
            if context.chain_age_seconds > self.max_age_seconds:
                return False
        return True


@dataclass
class EvaluationContext:
    """Data available for policy evaluation."""
    agent_id: str
    trust_score: float = 0.0
    endorsement_count: int = 0
    chain_length: int = 0
    scopes: list[str] = field(default_factory=list)
    issuer_ids: list[str] = field(default_factory=list)
    chain_age_seconds: int = 0
    attestations: list[IsnadAttestation] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class PolicyRule:
    """A named rule with requirement and action."""
    name: str
    requirement: TrustRequirement
    on_match: PolicyAction = PolicyAction.ALLOW
    on_fail: PolicyAction = PolicyAction.DENY
    description: str = ""
    priority: int = 0  # higher = evaluated first


@dataclass
class PolicyDecision:
    """Result of policy evaluation."""
    action: PolicyAction
    rule_name: str
    matched: bool
    reason: str
    context_agent_id: str

    def allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "rule_name": self.rule_name,
            "matched": self.matched,
            "reason": self.reason,
            "agent_id": self.context_agent_id,
        }


class TrustPolicy:
    """A collection of rules that define trust requirements.

    Usage:
        policy = TrustPolicy("commerce-policy")
        policy.add_rule(PolicyRule(
            name="min-trust",
            requirement=TrustRequirement(min_trust_score=0.7),
            on_fail=PolicyAction.DENY,
        ))
        policy.add_rule(PolicyRule(
            name="endorsed",
            requirement=TrustRequirement(min_endorsements=3),
            on_fail=PolicyAction.REQUIRE_REVIEW,
            priority=1,
        ))

        ctx = EvaluationContext(agent_id="agent-123", trust_score=0.8, endorsement_count=5)
        decision = policy.evaluate(ctx)
        if decision.allowed():
            # proceed with interaction
    """

    def __init__(self, name: str, default_action: PolicyAction = PolicyAction.DENY):
        self.name = name
        self.default_action = default_action
        self.rules: list[PolicyRule] = []

    def add_rule(self, rule: PolicyRule) -> "TrustPolicy":
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        return self

    def evaluate(self, context: EvaluationContext) -> PolicyDecision:
        """Evaluate all rules against context. First failing rule wins."""
        for rule in self.rules:
            met = rule.requirement.evaluate(context)
            if not met:
                return PolicyDecision(
                    action=rule.on_fail,
                    rule_name=rule.name,
                    matched=False,
                    reason=f"Failed requirement: {rule.name}" + (f" — {rule.description}" if rule.description else ""),
                    context_agent_id=context.agent_id,
                )

        # All rules passed
        if self.rules:
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                rule_name="all_passed",
                matched=True,
                reason="All policy rules satisfied",
                context_agent_id=context.agent_id,
            )

        return PolicyDecision(
            action=self.default_action,
            rule_name="default",
            matched=False,
            reason="No rules defined, using default action",
            context_agent_id=context.agent_id,
        )

    def evaluate_batch(self, contexts: list[EvaluationContext]) -> list[PolicyDecision]:
        """Evaluate policy against multiple agents."""
        return [self.evaluate(ctx) for ctx in contexts]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "default_action": self.default_action.value,
            "rules": [
                {
                    "name": r.name,
                    "requirement": asdict(r.requirement),
                    "on_match": r.on_match.value,
                    "on_fail": r.on_fail.value,
                    "description": r.description,
                    "priority": r.priority,
                }
                for r in self.rules
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "TrustPolicy":
        policy = cls(
            name=data["name"],
            default_action=PolicyAction(data.get("default_action", "deny")),
        )
        for rd in data.get("rules", []):
            req_data = rd.get("requirement", {})
            req = TrustRequirement(
                min_trust_score=req_data.get("min_trust_score"),
                min_endorsements=req_data.get("min_endorsements"),
                max_chain_length=req_data.get("max_chain_length"),
                required_scopes=req_data.get("required_scopes"),
                required_issuer_ids=req_data.get("required_issuer_ids"),
                max_age_seconds=req_data.get("max_age_seconds"),
            )
            rule = PolicyRule(
                name=rd["name"],
                requirement=req,
                on_match=PolicyAction(rd.get("on_match", "allow")),
                on_fail=PolicyAction(rd.get("on_fail", "deny")),
                description=rd.get("description", ""),
                priority=rd.get("priority", 0),
            )
            policy.add_rule(rule)
        return policy

    @classmethod
    def from_json(cls, json_str: str) -> "TrustPolicy":
        return cls.from_dict(json.loads(json_str))


# --- Preset policies ---

def strict_commerce_policy() -> TrustPolicy:
    """High-trust policy for financial transactions."""
    p = TrustPolicy("strict-commerce")
    p.add_rule(PolicyRule(
        name="high-trust-score",
        requirement=TrustRequirement(min_trust_score=0.8),
        description="Commerce requires high trust score",
        priority=10,
    ))
    p.add_rule(PolicyRule(
        name="endorsed",
        requirement=TrustRequirement(min_endorsements=3),
        description="Must have at least 3 endorsements",
        priority=5,
    ))
    p.add_rule(PolicyRule(
        name="short-chain",
        requirement=TrustRequirement(max_chain_length=5),
        description="Attestation chain must be reasonably short",
        priority=3,
    ))
    p.add_rule(PolicyRule(
        name="fresh-attestation",
        requirement=TrustRequirement(max_age_seconds=86400),
        description="Attestations must be less than 24h old",
        priority=2,
    ))
    return p


def open_discovery_policy() -> TrustPolicy:
    """Permissive policy for agent discovery/browsing."""
    p = TrustPolicy("open-discovery", default_action=PolicyAction.ALLOW)
    p.add_rule(PolicyRule(
        name="minimal-trust",
        requirement=TrustRequirement(min_trust_score=0.3),
        description="Basic trust threshold for discovery",
        on_fail=PolicyAction.RATE_LIMIT,
        priority=1,
    ))
    return p


# --- PolicyEngine: multi-policy composition (strictest wins) ---

# Strictness ordering: DENY > REQUIRE_REVIEW > RATE_LIMIT > ALLOW
_ACTION_STRICTNESS: dict[PolicyAction, int] = {
    PolicyAction.DENY: 3,
    PolicyAction.REQUIRE_REVIEW: 2,
    PolicyAction.RATE_LIMIT: 1,
    PolicyAction.ALLOW: 0,
}


class PolicyEngine:
    """Evaluates multiple TrustPolicies; strictest decision wins.

    Usage:
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.STRICT)
        engine.add_policy(custom_policy)
        decision = engine.evaluate(context)
    """

    def __init__(self) -> None:
        self.policies: list[TrustPolicy] = []

    def add_policy(self, policy: TrustPolicy) -> "PolicyEngine":
        self.policies.append(policy)
        return self

    def evaluate(self, context: EvaluationContext) -> PolicyDecision:
        """Evaluate all policies; return the strictest decision."""
        if not self.policies:
            return PolicyDecision(
                action=PolicyAction.DENY,
                rule_name="no_policies",
                matched=False,
                reason="No policies configured in engine",
                context_agent_id=context.agent_id,
            )

        decisions = [p.evaluate(context) for p in self.policies]
        # Pick strictest
        strictest = max(decisions, key=lambda d: _ACTION_STRICTNESS[d.action])
        return PolicyDecision(
            action=strictest.action,
            rule_name=strictest.rule_name,
            matched=strictest.matched,
            reason=f"[{len(decisions)} policies evaluated, strictest wins] {strictest.reason}",
            context_agent_id=context.agent_id,
        )

    def evaluate_batch(self, contexts: list[EvaluationContext]) -> list[PolicyDecision]:
        return [self.evaluate(ctx) for ctx in contexts]


class DefaultPolicies:
    """Preset policy configurations."""

    STRICT: TrustPolicy = None  # type: ignore[assignment]
    MODERATE: TrustPolicy = None  # type: ignore[assignment]
    PERMISSIVE: TrustPolicy = None  # type: ignore[assignment]

    @staticmethod
    def _build_strict() -> TrustPolicy:
        """score > 0.8, max 24h attestation age."""
        p = TrustPolicy("strict")
        p.add_rule(PolicyRule(
            name="strict-trust-score",
            requirement=TrustRequirement(min_trust_score=0.8),
            description="Strict: trust score must exceed 0.8",
            priority=10,
        ))
        p.add_rule(PolicyRule(
            name="strict-freshness",
            requirement=TrustRequirement(max_age_seconds=86400),  # 24h
            description="Strict: attestations must be < 24h old",
            priority=5,
        ))
        return p

    @staticmethod
    def _build_moderate() -> TrustPolicy:
        """score > 0.5, max 7 days."""
        p = TrustPolicy("moderate")
        p.add_rule(PolicyRule(
            name="moderate-trust-score",
            requirement=TrustRequirement(min_trust_score=0.5),
            description="Moderate: trust score must exceed 0.5",
            priority=10,
        ))
        p.add_rule(PolicyRule(
            name="moderate-freshness",
            requirement=TrustRequirement(max_age_seconds=604800),  # 7d
            description="Moderate: attestations must be < 7 days old",
            priority=5,
        ))
        return p

    @staticmethod
    def _build_permissive() -> TrustPolicy:
        """score > 0.2, no age limit."""
        p = TrustPolicy("permissive", default_action=PolicyAction.ALLOW)
        p.add_rule(PolicyRule(
            name="permissive-trust-score",
            requirement=TrustRequirement(min_trust_score=0.2),
            description="Permissive: basic trust threshold",
            on_fail=PolicyAction.DENY,
            priority=10,
        ))
        return p


# Initialize class-level presets
DefaultPolicies.STRICT = DefaultPolicies._build_strict()
DefaultPolicies.MODERATE = DefaultPolicies._build_moderate()
DefaultPolicies.PERMISSIVE = DefaultPolicies._build_permissive()


def scoped_delegation_policy(required_scopes: list[str]) -> TrustPolicy:
    """Policy requiring specific delegation scopes."""
    p = TrustPolicy("scoped-delegation")
    p.add_rule(PolicyRule(
        name="scope-check",
        requirement=TrustRequirement(required_scopes=required_scopes),
        description=f"Requires scopes: {', '.join(required_scopes)}",
        priority=10,
    ))
    p.add_rule(PolicyRule(
        name="basic-trust",
        requirement=TrustRequirement(min_trust_score=0.5),
        description="Minimum trust for scoped operations",
        priority=5,
    ))
    return p
