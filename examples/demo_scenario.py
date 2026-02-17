#!/usr/bin/env python3
"""
isnad Demo Scenario — Agent Trust in Action

This demo simulates a real-world scenario where three AI agents
build trust through verified interactions.

Run: python examples/demo_scenario.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.trustscore.engine import TrustScoreEngine


def main():
    print("=" * 60)
    print("🔐 isnad Demo — Cryptographic Trust Chains for AI Agents")
    print("=" * 60)

    # === Step 1: Create Agent Identities ===
    print("\n📋 Step 1: Generate Agent Identities\n")

    orchestrator = AgentIdentity.generate("orchestrator-prime")
    researcher = AgentIdentity.generate("researcher-alpha")
    coder = AgentIdentity.generate("coder-beta")

    agents = {
        "orchestrator": orchestrator,
        "researcher": researcher,
        "coder": coder,
    }
    for name, agent in agents.items():
        print(f"  ✅ {name}: {agent.agent_id[:16]}...")

    # === Step 2: Build Attestation Chain ===
    print("\n📋 Step 2: Create Attestations (verified interactions)\n")

    attestations = []

    # Orchestrator attests researcher's analysis
    a1 = Attestation.create(
        subject=researcher.agent_id,
        witness=orchestrator,
        scope="research",
        evidence="https://example.com/report-42",
    )
    attestations.append(a1)
    print(f"  ✅ orchestrator → researcher: 'research' (verified: {a1.verify(orchestrator.public_key)})")

    # Orchestrator attests coder's implementation
    a2 = Attestation.create(
        subject=coder.agent_id,
        witness=orchestrator,
        scope="code-review",
        evidence="https://github.com/org/repo/pull/99",
    )
    attestations.append(a2)
    print(f"  ✅ orchestrator → coder: 'code-review' (verified: {a2.verify(orchestrator.public_key)})")

    # Researcher attests coder's data handling
    a3 = Attestation.create(
        subject=coder.agent_id,
        witness=researcher,
        scope="data-handling",
        evidence="https://example.com/pipeline-audit",
    )
    attestations.append(a3)
    print(f"  ✅ researcher → coder: 'data-handling' (verified: {a3.verify(researcher.public_key)})")

    # Coder attests researcher (mutual trust)
    a4 = Attestation.create(
        subject=researcher.agent_id,
        witness=coder,
        scope="research",
        evidence="https://example.com/collab-results",
    )
    attestations.append(a4)
    print(f"  ✅ coder → researcher: 'research' (verified: {a4.verify(coder.public_key)})")

    # === Step 3: Compute Trust Scores ===
    print("\n📋 Step 3: Compute Trust Scores\n")

    chain = TrustChain(attestations)

    for name, agent in agents.items():
        for scope in ["research", "code-review", "data-handling"]:
            score = chain.trust_score(agent.agent_id, scope=scope)
            if score > 0:
                bar = "█" * int(score * 20)
                print(f"  {name:15s} [{scope:15s}] → {score:.2f} {bar}")

    # === Step 4: Verify Chain Integrity ===
    print("\n📋 Step 4: Verify Entire Chain\n")

    all_valid = all(
        a.verify(agents[name].public_key)
        for a, name in [
            (a1, "orchestrator"),
            (a2, "orchestrator"),
            (a3, "researcher"),
            (a4, "coder"),
        ]
    )
    print(f"  Chain integrity: {'✅ ALL VALID' if all_valid else '❌ INTEGRITY FAILURE'}")
    print(f"  Attestations: {len(attestations)}")
    print(f"  Agents: {len(agents)}")

    # === Step 5: Serialization (portable trust) ===
    print("\n📋 Step 5: Portable Trust — Serialize & Deserialize\n")

    serialized = a1.to_dict()
    restored = Attestation.from_dict(serialized)
    print(f"  Serialized attestation: {len(json.dumps(serialized))} bytes")
    print(f"  Restored & verified: {restored.verify(orchestrator.public_key)}")

    print("\n" + "=" * 60)
    print("✅ Demo complete — trust is cryptographic, not social.")
    print("   Learn more: https://github.com/gendolf-agent/isnad-ref-impl")
    print("=" * 60)


if __name__ == "__main__":
    main()
