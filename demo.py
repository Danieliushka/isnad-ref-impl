#!/usr/bin/env python3
"""Interactive demo of the Isnad trust framework."""

from datetime import datetime, timezone, timedelta
from isnad import AgentIdentity, Attestation, TrustChain
from trustscore.bridge import IsnadBridge
from trustscore.scorer import TrustScorer

# ─── Colors ────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RST = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"
WHITE = "\033[97m"

def header(text):
    w = 60
    print(f"\n{CYAN}{BOLD}{'═' * w}")
    print(f"  {text}")
    print(f"{'═' * w}{RST}\n")

def step(n, text):
    print(f"  {YELLOW}{BOLD}[{n}]{RST} {text}")

def kv(key, val, indent=6):
    print(f"{' ' * indent}{DIM}{key}:{RST} {val}")

def ok(text):
    print(f"  {GREEN}✓{RST} {text}")

def fail(text):
    print(f"  {RED}✗{RST} {text}")

# ─── Main ──────────────────────────────────────────────────────────

def main():
    header("ISNAD — Agent Trust Framework Demo")

    # 1. Create identities
    step(1, "Creating agent identities")
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()
    agents = {"Alice-Agent": alice, "Bob-Agent": bob, "Charlie-Agent": charlie}
    for name, a in agents.items():
        kv(name, f"{CYAN}{a.agent_id[:32]}…{RST}")
    print()

    # 2. Create attestations
    step(2, "Creating signed attestations")

    att1 = Attestation(
        subject=bob.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://github.com/acme/repo/pull/42",
    ).sign(alice)
    ok(f"Alice attests Bob completed {MAGENTA}code-review{RST}")

    att2 = Attestation(
        subject=charlie.agent_id,
        witness=bob.agent_id,
        task="service-deployment",
        evidence="https://deploy.acme.io/run/137",
    ).sign(bob)
    ok(f"Bob attests Charlie completed {MAGENTA}service-deployment{RST}")

    # Bonus: Alice also attests Charlie for testing
    att3 = Attestation(
        subject=charlie.agent_id,
        witness=alice.agent_id,
        task="integration-testing",
        evidence="https://ci.acme.io/build/891",
    ).sign(alice)
    ok(f"Alice attests Charlie completed {MAGENTA}integration-testing{RST}")
    print()

    # 3. Build trust chain
    step(3, "Building trust chain")
    chain = TrustChain()
    for att in [att1, att2, att3]:
        added = chain.add(att)
        status = f"{GREEN}accepted{RST}" if added else f"{RED}rejected{RST}"
        kv("attestation", f"{att.attestation_id[:16]}… → {status}")
    print()

    # 4. Trust scores (native isnad)
    step(4, "Trust scores (native Isnad chain)")
    for name, agent in agents.items():
        score = chain.trust_score(agent.agent_id)
        bar = _bar(score)
        print(f"      {name:16s} {bar} {WHITE}{score:.3f}{RST}")

    # Transitive trust
    print()
    ct = chain.chain_trust(alice.agent_id, charlie.agent_id)
    kv("Transitive trust", f"Alice → Charlie = {WHITE}{ct:.3f}{RST}")
    print()

    # 5. TrustScore (bridge + scorer)
    step(5, "TrustScore — multi-signal scoring via bridge")
    bridge = IsnadBridge(chain)
    interactions = bridge.to_interactions()
    endorsements = bridge.to_endorsements()

    scorer = TrustScorer(interactions=interactions, endorsements=endorsements)
    detail = scorer.compute_detailed()

    kv("Overall TrustScore", f"{BOLD}{WHITE}{detail['trust_score']:.4f}{RST}")
    kv("Interactions", detail["interaction_count"])
    kv("Endorsements", detail["endorsement_count"])
    print(f"      {DIM}Signals:{RST}")
    for sig, val in detail["signals"].items():
        bar = _bar(val)
        print(f"        {sig:24s} {bar} {val:.3f}")
    print()

    # 6. Agent profiles
    step(6, "Agent trust profiles")
    for name, agent in agents.items():
        profile = bridge.agent_trust_profile(agent.agent_id)
        print(f"      {BOLD}{name}{RST}")
        kv("Attestations", profile["attestation_count"], indent=8)
        kv("Unique witnesses", profile["unique_witnesses"], indent=8)
        kv("Raw score", f"{profile['raw_score']:.3f}", indent=8)
        kv("Weighted score", f"{profile['weighted_score']:.3f}", indent=8)
        kv("Skills", ", ".join(profile["skills"]) if profile["skills"] else "—", indent=8)
        print()

    # 7. Verify chain integrity
    step(7, "Verifying attestation signatures")
    all_ok = True
    for att in chain.attestations:
        valid = att.verify()
        all_ok = all_ok and valid
        fn = ok if valid else fail
        fn(f"{att.attestation_id[:16]}… sig={GREEN}valid{RST}" if valid
           else f"{att.attestation_id[:16]}… sig={RED}INVALID{RST}")

    print()
    if all_ok:
        print(f"  {GREEN}{BOLD}✓ All attestations verified — chain is intact.{RST}")
    else:
        print(f"  {RED}{BOLD}✗ Some attestations failed verification!{RST}")

    header("Demo complete")


def _bar(value, width=20):
    """Render a small horizontal bar."""
    filled = int(value * width)
    return f"{GREEN}{'█' * filled}{DIM}{'░' * (width - filled)}{RST}"


if __name__ == "__main__":
    main()
