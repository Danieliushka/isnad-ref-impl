#!/usr/bin/env python3
"""
Isnad Verification Middleware — drop-in trust verification for any HTTP service.

Provides a simple decorator/middleware that verifies incoming agent requests
carry valid isnad attestation chains before processing them.

Usage:
    # As a standalone demo
    python examples/verify_middleware.py

    # In your code
    from verify_middleware import IsnadVerifier
    verifier = IsnadVerifier(min_trust=0.6, required_scopes=["api-access"])
    result = verifier.verify_request(headers)
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, ".")
from src.isnad.core import AgentIdentity, Attestation, TrustChain


@dataclass
class VerificationResult:
    """Result of verifying an agent's request."""
    allowed: bool
    agent_id: Optional[str] = None
    trust_score: float = 0.0
    scopes: list = field(default_factory=list)
    reason: str = ""


class IsnadVerifier:
    """
    Drop-in verification layer for agent-to-agent or agent-to-service requests.
    
    Checks:
    1. Request carries a valid isnad attestation chain (X-Isnad-Chain header)
    2. Chain signatures are cryptographically valid
    3. Trust score meets minimum threshold
    4. Required scopes (tasks) are attested
    """
    
    def __init__(
        self,
        min_trust: float = 0.5,
        required_scopes: list = None,
        trusted_issuers: list = None,
    ):
        self.min_trust = min_trust
        self.required_scopes = required_scopes or []
        self.trusted_issuers = trusted_issuers  # None = accept any
    
    def verify_request(self, headers: dict) -> VerificationResult:
        """Verify an incoming request's isnad attestation chain."""
        
        chain_header = headers.get("X-Isnad-Chain") or headers.get("x-isnad-chain")
        if not chain_header:
            return VerificationResult(allowed=False, reason="Missing X-Isnad-Chain header")
        
        try:
            chain_data = json.loads(chain_header)
        except json.JSONDecodeError:
            return VerificationResult(allowed=False, reason="Malformed X-Isnad-Chain (invalid JSON)")
        
        # Reconstruct attestations
        attestations = []
        for att_data in chain_data.get("attestations", []):
            try:
                att = Attestation.from_dict(att_data)
                attestations.append(att)
            except Exception as e:
                return VerificationResult(allowed=False, reason=f"Invalid attestation: {e}")
        
        if not attestations:
            return VerificationResult(allowed=False, reason="Empty attestation chain")
        
        subject_id = chain_data.get("agent_id")
        if not subject_id:
            return VerificationResult(allowed=False, reason="Missing agent_id in chain")
        
        # Build trust chain and verify signatures
        chain = TrustChain()
        valid_atts = []
        for att in attestations:
            if att.verify():
                chain.add(att)
                valid_atts.append(att)
        
        if not valid_atts:
            return VerificationResult(
                allowed=False, agent_id=subject_id,
                reason="No attestations with valid signatures"
            )
        
        # Check trust score
        score = chain.trust_score(subject_id)
        if score < self.min_trust:
            return VerificationResult(
                allowed=False, agent_id=subject_id, trust_score=score,
                reason=f"Trust score {score:.2f} below threshold {self.min_trust:.2f}"
            )
        
        # Check required scopes (mapped to attestation 'task' field)
        attested_tasks = {att.to_dict().get("task", "") for att in valid_atts if att.subject == subject_id}
        missing = set(self.required_scopes) - attested_tasks
        if missing:
            return VerificationResult(
                allowed=False, agent_id=subject_id, trust_score=score,
                scopes=list(attested_tasks),
                reason=f"Missing required scopes: {missing}"
            )
        
        # Check trusted issuers
        if self.trusted_issuers is not None:
            issuers = {att.witness for att in valid_atts}
            if not issuers & set(self.trusted_issuers):
                return VerificationResult(
                    allowed=False, agent_id=subject_id, trust_score=score,
                    reason="No attestations from trusted issuers"
                )
        
        return VerificationResult(
            allowed=True, agent_id=subject_id, trust_score=score,
            scopes=list(attested_tasks), reason="Verified"
        )


def demo():
    """Demo: create agents, attest, and verify a simulated request."""
    print("=== Isnad Verification Middleware Demo ===\n")
    
    # Create agents
    org = AgentIdentity()
    worker = AgentIdentity()
    reviewer = AgentIdentity()
    
    print(f"Organization: {org.agent_id}")
    print(f"Worker:       {worker.agent_id}")
    print(f"Reviewer:     {reviewer.agent_id}\n")
    
    # Org attests worker has api-access
    att1 = Attestation(
        subject=worker.agent_id,
        witness=org.agent_id,
        task="api-access",
        evidence="internal-onboarding-2026-02-17",
        witness_pubkey=org.public_key_hex
    )
    att1.sign(org)
    
    # Reviewer attests worker did code-review
    att2 = Attestation(
        subject=worker.agent_id,
        witness=reviewer.agent_id,
        task="code-review",
        evidence="https://github.com/acme/repo/pull/99",
        witness_pubkey=reviewer.public_key_hex
    )
    att2.sign(reviewer)
    
    # Worker builds request with chain header
    chain_header = json.dumps({
        "agent_id": worker.agent_id,
        "attestations": [att1.to_dict(), att2.to_dict()]
    })
    
    headers = {"X-Isnad-Chain": chain_header}
    
    # === Test 1: Basic verification (should pass) ===
    print("--- Test 1: Basic verification ---")
    verifier = IsnadVerifier(min_trust=0.3, required_scopes=["api-access"])
    result = verifier.verify_request(headers)
    print(f"  Allowed: {result.allowed}")
    print(f"  Trust:   {result.trust_score:.2f}")
    print(f"  Scopes:  {result.scopes}")
    print(f"  Reason:  {result.reason}\n")
    
    # === Test 2: High trust threshold (should fail) ===
    print("--- Test 2: High trust threshold ---")
    strict = IsnadVerifier(min_trust=0.99)
    result = strict.verify_request(headers)
    print(f"  Allowed: {result.allowed}")
    print(f"  Reason:  {result.reason}\n")
    
    # === Test 3: Missing scope (should fail) ===
    print("--- Test 3: Required scope not attested ---")
    scoped = IsnadVerifier(min_trust=0.1, required_scopes=["admin-access"])
    result = scoped.verify_request(headers)
    print(f"  Allowed: {result.allowed}")
    print(f"  Reason:  {result.reason}\n")
    
    # === Test 4: No chain header (should fail) ===
    print("--- Test 4: Missing chain header ---")
    result = verifier.verify_request({})
    print(f"  Allowed: {result.allowed}")
    print(f"  Reason:  {result.reason}\n")
    
    # === Test 5: Trusted issuers filter ===
    print("--- Test 5: Trusted issuers ---")
    issuer_check = IsnadVerifier(min_trust=0.1, trusted_issuers=[org.agent_id])
    result = issuer_check.verify_request(headers)
    print(f"  Allowed: {result.allowed}")
    print(f"  Reason:  {result.reason}\n")
    
    print("✅ Middleware demo complete.")


if __name__ == "__main__":
    demo()
