#!/usr/bin/env python3
"""
Multi-Agent Trust Network — isnad SDK Example

Demonstrates a realistic 3-agent scenario:
1. Three agents generate identities
2. They attest each other's work on different tasks
3. Build a trust network with varied scopes
4. Query reputation and trust scores

Usage:
    python examples/multi_agent_flow.py [sandbox_url]
"""

import sys
sys.path.insert(0, ".")
from isnad_client import IsnadClient

SANDBOX = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8420"


def main():
    with IsnadClient(SANDBOX) as c:
        print("=" * 50)
        print("🌐 isnad Multi-Agent Trust Network Demo")
        print(f"🔗 Sandbox: {SANDBOX}")
        print("=" * 50)

        # --- 1. Create agents ---
        agents = {}
        for name in ["alice", "bob", "charlie"]:
            keys = c.generate_keys()
            agents[name] = keys["agent_id"]
            print(f"\n🔑 {name}: {keys['agent_id'][:16]}...")

        # --- 2. Attestations (simulating real work) ---
        print("\n--- Creating attestations ---")

        tasks = [
            ("alice", "bob", "code-review", "Reviewed auth module, found 2 bugs"),
            ("bob", "alice", "code-review", "Reviewed API endpoint, clean code"),
            ("alice", "charlie", "data-analysis", "Accurate market report"),
            ("charlie", "alice", "deployment", "Smooth prod deploy, zero downtime"),
            ("bob", "charlie", "testing", "Comprehensive test suite, 95% coverage"),
            ("charlie", "bob", "documentation", "Clear API docs with examples"),
        ]

        for witness, subject, task, evidence in tasks:
            att = c.create_attestation(
                witness_id=agents[witness],
                subject_id=agents[subject],
                task=task,
                evidence=evidence,
            )
            print(f"  ✅ {witness} → {subject} ({task})")

        # --- 3. Trust scores ---
        print("\n--- Trust Scores ---")
        for name, aid in agents.items():
            score = c.trust_score(aid)
            print(f"  📊 {name}: {score['trust_score']:.2f} "
                  f"(attestations: {score.get('attestation_count', '?')})")

        # --- 4. Scoped scores ---
        print("\n--- Scoped Scores (code-review) ---")
        for name, aid in agents.items():
            score = c.trust_score(aid, scope="code-review")
            print(f"  🔍 {name} [code-review]: {score['trust_score']:.2f}")

        # --- 5. Reputation ---
        print("\n--- Full Reputation ---")
        for name, aid in agents.items():
            rep = c.reputation(aid)
            peers = rep.get("peers", [])
            peer_names = []
            for p in peers:
                pid = p.get("agent_id") if isinstance(p, dict) else p
                for n, a in agents.items():
                    if a == pid:
                        peer_names.append(n)
            print(f"  👤 {name}: score={rep['trust_score']:.2f}, "
                  f"received={rep['attestations_received']}, "
                  f"given={rep['attestations_given']}, "
                  f"peers={peer_names}")

        # --- 6. Batch verify ---
        print("\n--- Batch Verification ---")
        chain = c.get_chain(agents["alice"])
        atts = chain.get("attestations", [])
        if atts:
            result = c.batch_verify(atts)
            print(f"  ✅ Verified {result.get('total', len(atts))} attestations, "
                  f"valid: {result.get('valid', '?')}")

        print("\n" + "=" * 50)
        print("✅ Demo complete! All agents verified in trust network.")
        print("=" * 50)


if __name__ == "__main__":
    main()
