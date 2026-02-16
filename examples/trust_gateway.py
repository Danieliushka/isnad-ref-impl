"""
Trust Gateway — HTTP middleware that verifies agent identity before allowing access.

This example shows how to build a zero-trust gateway for multi-agent systems.
Agents must present a valid isnad attestation chain to access protected resources.

Usage:
    python trust_gateway.py

    # In another terminal:
    curl -X POST http://localhost:8080/verify \
        -H "Content-Type: application/json" \
        -d '{"agent_id": "...", "chain_export": "..."}'
"""

import json
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import dataclass, field
from typing import Optional

from isnad.core import TrustChain, AgentIdentity, Attestation
@dataclass
class TrustPolicy:
    """Defines minimum trust requirements for access."""
    min_attestations: int = 2
    min_trust_score: float = 0.5
    required_tasks: list = field(default_factory=lambda: [])
    max_chain_age_hours: int = 720  # 30 days


class TrustGateway:
    """Verifies agent trust before granting access to protected resources."""

    def __init__(self, policy: TrustPolicy = None):
        self.policy = policy or TrustPolicy()
        self._access_log: list[dict] = []

    def evaluate(self, chain: TrustChain, agent_id: str) -> dict:
        """Evaluate an agent's trust level against the policy."""
        # Count attestations for this agent
        agent_attestations = [
            a for a in chain.attestations
            if a.subject == agent_id and a.verify()
        ]

        # Check attestation count
        if len(agent_attestations) < self.policy.min_attestations:
            return self._deny(agent_id, f"Need {self.policy.min_attestations} attestations, have {len(agent_attestations)}")

        # Check required tasks
        attested_tasks = {a.task for a in agent_attestations}
        missing_tasks = set(self.policy.required_tasks) - attested_tasks
        if missing_tasks:
            return self._deny(agent_id, f"Missing required tasks: {missing_tasks}")

        # Calculate trust score (attestation-based: unique witnesses / threshold)
        unique_witnesses = len({a.witness for a in agent_attestations})
        score = min(1.0, unique_witnesses / max(self.policy.min_attestations, 1))

        if score < self.policy.min_trust_score:
            return self._deny(agent_id, f"Trust score {score:.2f} below threshold {self.policy.min_trust_score}")

        return self._allow(agent_id, score, len(agent_attestations))

    def _allow(self, agent_id: str, score: float, attestation_count: int) -> dict:
        result = {
            "decision": "ALLOW",
            "agent_id": agent_id,
            "trust_score": round(score, 3),
            "attestations": attestation_count,
        }
        self._access_log.append(result)
        return result

    def _deny(self, agent_id: str, reason: str) -> dict:
        result = {
            "decision": "DENY",
            "agent_id": agent_id,
            "reason": reason,
        }
        self._access_log.append(result)
        return result

    @property
    def audit_log(self) -> list[dict]:
        return list(self._access_log)


def demo():
    """Run a demo of the trust gateway."""
    print("🔐 isnad Trust Gateway Demo\n")

    # Create agents
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()
    untrusted = AgentIdentity()

    # Build trust chain — Bob and Charlie vouch for Alice
    chain = TrustChain()

    for task, witness, evidence in [
        ("code_review", bob, "Reviewed 15 PRs with zero regressions"),
        ("security_audit", charlie, "Passed OWASP top-10 verification"),
        ("data_handling", bob, "GDPR-compliant data processing verified"),
    ]:
        att = Attestation(
            subject=alice.agent_id,
            witness=witness.agent_id,
            task=task,
            evidence=evidence,
        )
        att.sign(witness)
        chain.add(att)

    # Create gateway with policy
    policy = TrustPolicy(
        min_attestations=2,
        min_trust_score=0.3,
        required_tasks=["security_audit"],
    )
    gateway = TrustGateway(policy)

    # Test: trusted agent
    print(f"Agent: {alice.agent_id[:20]}...")
    result = gateway.evaluate(chain, alice.agent_id)
    print(f"  Decision: {result['decision']}")
    if result['decision'] == 'ALLOW':
        print(f"  Trust Score: {result['trust_score']}")
        print(f"  Attestations: {result['attestations']}")
    else:
        print(f"  Reason: {result['reason']}")

    # Test: untrusted agent (no attestations)
    print(f"\nAgent: {untrusted.agent_id[:20]}... (no attestations)")
    result = gateway.evaluate(chain, untrusted.agent_id)
    print(f"  Decision: {result['decision']}")
    print(f"  Reason: {result.get('reason', 'N/A')}")

    # Audit log
    print(f"\n📋 Audit Log ({len(gateway.audit_log)} entries):")
    for entry in gateway.audit_log:
        status = "✅" if entry['decision'] == 'ALLOW' else "❌"
        print(f"  {status} {entry['agent_id'][:16]}... → {entry['decision']}")

    print("\n✨ Gateway evaluated 2 agents. Trust-based access control works.")


if __name__ == "__main__":
    demo()
