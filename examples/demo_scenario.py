#!/usr/bin/env python3
"""
isnad Demo — Agent Trust in Action

Three AI agents build cryptographic trust through verified interactions.

Run: python examples/demo_scenario.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from isnad.core import AgentIdentity, Attestation, TrustChain


def main():
    print("=" * 60)
    print("🔐 isnad Demo — Cryptographic Trust Chains for AI Agents")
    print("=" * 60)

    # === Step 1: Create Agent Identities ===
    print("\n📋 Step 1: Generate Agent Identities\n")

    orchestrator = AgentIdentity()
    researcher = AgentIdentity()
    coder = AgentIdentity()

    agents = {
        "orchestrator": orchestrator,
        "researcher": researcher,
        "coder": coder,
    }
    for name, agent in agents.items():
        print(f"  ✅ {name}: {agent.agent_id[:24]}...")

    # === Step 2: Build Attestation Chain ===
    print("\n📋 Step 2: Create Signed Attestations\n")

    # Orchestrator attests researcher's analysis
    a1 = Attestation(
        subject=researcher.agent_id,
        witness=orchestrator.agent_id,
        task="research",
        evidence="https://example.com/report-42",
    ).sign(orchestrator)
    print(f"  ✅ orchestrator → researcher: 'research' (verified: {a1.verify()})")

    # Orchestrator attests coder's implementation
    a2 = Attestation(
        subject=coder.agent_id,
        witness=orchestrator.agent_id,
        task="code-review",
        evidence="https://github.com/org/repo/pull/99",
    ).sign(orchestrator)
    print(f"  ✅ orchestrator → coder: 'code-review' (verified: {a2.verify()})")

    # Researcher attests coder's data handling
    a3 = Attestation(
        subject=coder.agent_id,
        witness=researcher.agent_id,
        task="data-handling",
        evidence="https://example.com/pipeline-audit",
    ).sign(researcher)
    print(f"  ✅ researcher → coder: 'data-handling' (verified: {a3.verify()})")

    # Coder attests researcher (mutual trust)
    a4 = Attestation(
        subject=researcher.agent_id,
        witness=coder.agent_id,
        task="research",
        evidence="https://example.com/collab-results",
    ).sign(coder)
    print(f"  ✅ coder → researcher: 'research' (verified: {a4.verify()})")

    # === Step 3: Build Trust Chain & Compute Scores ===
    print("\n📋 Step 3: Trust Chain & Scores\n")

    chain = TrustChain()
    for att in [a1, a2, a3, a4]:
        chain.add(att)

    for name, agent in agents.items():
        score = chain.trust_score(agent.agent_id)
        bar = "█" * int(score * 20) if score > 0 else "░"
        print(f"  {name:15s} → {score:.3f} {bar}")

    # === Step 4: Verify Chain Integrity ===
    print("\n📋 Step 4: Verify Chain Integrity\n")

    verifications = [
        a1.verify(),
        a2.verify(),
        a3.verify(),
        a4.verify(),
    ]
    all_valid = all(verifications)
    print(f"  Chain integrity: {'✅ ALL VALID' if all_valid else '❌ INTEGRITY FAILURE'}")
    print(f"  Attestations: 4  |  Agents: 3")

    # === Step 5: Serialization (portable trust) ===
    print("\n📋 Step 5: Portable Trust — Serialize & Verify\n")

    serialized = a1.to_dict()
    restored = Attestation.from_dict(serialized)
    print(f"  Serialized: {len(json.dumps(serialized))} bytes")
    print(f"  Restored & verified: {restored.verify()}")

    print("\n" + "=" * 60)
    print("✅ Trust is cryptographic, not social.")
    print("   https://github.com/gendolf-agent/isnad-ref-impl")
    print("=" * 60)


if __name__ == "__main__":
    main()
