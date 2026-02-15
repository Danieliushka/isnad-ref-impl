#!/usr/bin/env python3
"""
Enterprise Integration Example — isnad Agent Trust Protocol

Shows how to integrate isnad into enterprise agent infrastructure:
1. Issue verifiable credentials for your agents
2. Build trust chains across multi-agent workflows  
3. Verify agent identity before granting access
4. Score trust dynamically based on behavior

Compatible with: GitGuardian NHI, Strata Identity, any OIDC/OAuth flow.

Usage:
    python examples/enterprise_integration.py [sandbox_url]
"""

import sys
sys.path.insert(0, ".")
from isnad_client import IsnadClient

SANDBOX = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8420"


def enterprise_credentialing():
    """Enterprise agent credentialing and trust chain verification."""
    
    with IsnadClient(SANDBOX) as c:
        print("--- Scenario 1: Enterprise Agent Credentialing ---\n")
        
        # 1. Create organization trust anchor
        org = c.create_agent(alias="acme-corp-root")
        print(f"✅ Org trust anchor: {org['agent_id'][:24]}...")
        
        # 2. Issue credentials to worker agents
        data_agent = c.create_agent(alias="data-processor-v3")
        print(f"✅ Worker agent: {data_agent['agent_id'][:24]}...")
        
        # 3. Org attests the worker agent's role
        att1 = c.attest(
            attester=org["agent_id"],
            subject=data_agent["agent_id"],
            scope="credential:data-processor",
            confidence=0.95,
            detail="Authorized for analytics read/write. SOC2 compliant. Model: claude-sonnet-4 v3.2.1"
        )
        print(f"✅ Credential attestation: {att1['attestation_hash'][:16]}...")
        
        # 4. Worker delegates to a partner agent (cross-org trust)
        partner = c.create_agent(alias="partner-analytics-bot")
        att2 = c.attest(
            attester=data_agent["agent_id"],
            subject=partner["agent_id"],
            scope="delegation:read-shared-reports",
            confidence=0.8,
            detail="Delegated read access to shared analytics. Audit trail enabled."
        )
        print(f"✅ Cross-org delegation: {att2['attestation_hash'][:16]}...")
        
        # 5. Verify trust chain
        chain = c.get_chain(partner["agent_id"])
        print(f"\n🔍 Trust chain for partner agent:")
        print(f"   Attestations received: {len(chain.get('attestations', []))}")
        
        # 6. Check trust score
        score = c.trust_score(partner["agent_id"])
        print(f"   Trust score: {score.get('score', 'N/A')}")
        print(f"   Factors: {score.get('factors', {})}")
        
        return partner["agent_id"]


def nhi_lifecycle_example():
    """
    Non-Human Identity (NHI) lifecycle mapping.
    
    Pattern for integrating with:
    - GitGuardian NHI governance (credential rotation tracking)
    - Strata Maverics (agent auth orchestration)
    - Standard OIDC/OAuth service account flows
    """
    
    with IsnadClient(SANDBOX) as c:
        print("\n--- Scenario 2: NHI Lifecycle Integration ---\n")
        
        # Map existing service account to isnad identity
        nhi_agent = c.create_agent(alias="sa-42-gcp-project")
        print(f"✅ NHI mapped: {nhi_agent['agent_id'][:24]}...")
        
        # Security team attests the NHI's compliance
        security_team = c.create_agent(alias="security-team")
        att = c.attest(
            attester=security_team["agent_id"],
            subject=nhi_agent["agent_id"],
            scope="compliance:rotation-verified",
            confidence=0.9,
            detail="Credential rotation within 90d policy. Last rotated: 2026-02-15."
        )
        print(f"✅ Compliance attestation: {att['attestation_hash'][:16]}...")
        
        # Audit query: who trusts this NHI?
        chain = c.get_chain(nhi_agent["agent_id"])
        print(f"   Attestations: {len(chain.get('attestations', []))}")
        print("   Now trackable alongside agent-to-agent trust in unified chain")


if __name__ == "__main__":
    print("=" * 60)
    print("isnad — Enterprise Agent Trust Integration Demo")
    print(f"Sandbox: {SANDBOX}")
    print("=" * 60)
    print()
    
    enterprise_credentialing()
    nhi_lifecycle_example()
    
    print()
    print("=" * 60)
    print("Repo: https://github.com/gendolf-dev/isnad-ref-impl")
    print("Contact: gendolf@agentmail.to")
    print("=" * 60)
