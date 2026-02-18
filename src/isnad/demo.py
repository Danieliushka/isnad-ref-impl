#!/usr/bin/env python3
"""
isnad offline demo — Showcases the Agent Trust Protocol without a running server.

Run: python -m isnad.demo
"""

from isnad.core import AgentIdentity, Attestation, TrustChain


def _header(text: str):
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}\n")


def run():
    print("🔐 Agent Trust Protocol (isnad) — Offline Demo")
    print("=" * 50)
    print("No server needed. Pure cryptographic trust.\n")

    # --- Step 1: Create agents ---
    _header("Step 1: Agent Identity — Ed25519 Keypairs")
    alice = AgentIdentity()
    bob = AgentIdentity()
    carol = AgentIdentity()

    agents = {"Alice": alice, "Bob": bob, "Carol": carol}
    for name, agent in agents.items():
        print(f"  {name}: {agent.agent_id}")
    print("\n  Each agent has a unique Ed25519 keypair.")
    print("  Identity is cryptographic — unforgeable, decentralized.")

    # --- Step 2: Attestations ---
    _header("Step 2: Signed Attestations — Verifiable Claims")
    chain = TrustChain()

    att1 = Attestation(
        witness=alice.agent_id,
        subject=bob.agent_id,
        task="code-review",
        evidence="API endpoint validation, 347 lines reviewed, PR #42",
    )
    att1.sign(alice)
    chain.add(att1)
    print(f"  ✅ Alice attests Bob: code review (347 lines)")
    print(f"     Signature: {att1.signature[:40]}...")

    att2 = Attestation(
        witness=bob.agent_id,
        subject=carol.agent_id,
        task="market-analysis",
        evidence="94% accuracy, 12 predictions, 11 correct",
    )
    att2.sign(bob)
    chain.add(att2)
    print(f"  ✅ Bob attests Carol: market analysis (94% accuracy)")

    att3 = Attestation(
        witness=carol.agent_id,
        subject=alice.agent_id,
        task="pipeline-orchestration",
        evidence="5 agents coordinated, 23 tasks completed, 99.7% uptime",
    )
    att3.sign(carol)
    chain.add(att3)
    print(f"  ✅ Carol attests Alice: pipeline orchestration")

    # Extra attestations for richer scores
    att4 = Attestation(
        witness=alice.agent_id,
        subject=carol.agent_id,
        task="data-cleaning",
        evidence="Processed 50K records, 99.2% accuracy",
    )
    att4.sign(alice)
    chain.add(att4)
    print(f"  ✅ Alice attests Carol: data cleaning")

    print(f"\n  Every attestation is signed by the witness's private key.")
    print("  Claims include structured evidence — not just 'trust me bro'.")

    # --- Step 3: Verification ---
    _header("Step 3: Cryptographic Verification")
    for i, (desc, att) in enumerate([
        ("Alice→Bob (code review)", att1),
        ("Bob→Carol (market analysis)", att2),
        ("Carol→Alice (orchestration)", att3),
        ("Alice→Carol (data cleaning)", att4),
    ], 1):
        valid = att.verify()
        status = "✅ VALID" if valid else "❌ INVALID"
        print(f"  {i}. {desc}: {status}")

    # Tamper test
    print("\n  🔧 Tampering test — swap signature from another attestation...")
    tampered = Attestation(
        witness=alice.agent_id,
        subject=bob.agent_id,
        task="FAKE-TASK-injected",
        evidence="This claim was never made",
    )
    tampered.signature = att1.signature  # stolen sig
    tampered.witness_pubkey = att1.witness_pubkey
    valid = tampered.verify()
    print(f"  Tampered attestation: {'✅ VALID (BUG!)' if valid else '❌ REJECTED — forgery detected'}")

    # --- Step 4: Trust Scores ---
    _header("Step 4: Trust Scores — Gradient, Not Binary")
    for name, agent in agents.items():
        score = chain.trust_score(agent.agent_id)
        bar_len = int(score * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {name:6s} [{bar}] {score:.3f}")

    print("\n  Scores computed from attestation evidence.")
    print("  They decay over time — old trust fades, new trust must be earned.")
    print("  Chain trust amplifies: Alice trusts Bob, Bob trusts Carol")
    print("  → Alice has indirect trust path to Carol.")

    # --- Step 5: Chain trust ---
    _header("Step 5: Chain Trust — Transitive Verification")
    ct = chain.chain_trust(alice.agent_id, carol.agent_id)
    print(f"  Alice → Carol (indirect): {ct:.3f}")
    ct2 = chain.chain_trust(bob.agent_id, alice.agent_id)
    print(f"  Bob → Alice (indirect):   {ct2:.3f}")
    print("\n  Trust propagates through chains with decay.")
    print("  Longer chains = weaker trust. Direct > indirect.")

    # --- Summary ---
    _header("Summary")
    print("  isnad provides:")
    print("  • Ed25519 agent identity (unforgeable)")
    print("  • Signed attestations with structured evidence")
    print("  • Cryptographic verification (tamper-proof)")
    print("  • Gradient trust scores with temporal decay")
    print("  • Chain trust — transitive, decentralized")
    print(f"\n  📊 4 attestations, {len(agents)} agents, zero servers")
    print("  📦 pip install isnad")
    print("  📖 https://github.com/gendolf-agent/isnad-ref-impl")
    print()


if __name__ == "__main__":
    run()
