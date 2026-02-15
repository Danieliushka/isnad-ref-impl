#!/usr/bin/env python3
"""
isnad CLI — Command-line interface for the Agent Trust Protocol.

Usage:
    python cli.py keygen                          # Generate agent keys
    python cli.py attest <witness> <subject> <task> [--outcome good|bad]
    python cli.py verify <attestation_id>
    python cli.py score <agent_id>
    python cli.py chain <agent_id>                # Full attestation chain
    python cli.py demo                            # Run interactive demo
"""

import argparse
import json
import sys
from isnad_client import IsnadClient, IsnadError

DEFAULT_URL = "http://localhost:8420"


def cmd_keygen(client: IsnadClient, args):
    """Generate a new agent keypair."""
    result = client.generate_keys()
    print(f"🔑 Agent ID:    {result['agent_id']}")
    print(f"📝 Public Key:  {result['public_key'][:32]}...")
    print(f"🔐 Private Key: {result['private_key'][:16]}... (keep secret!)")
    return result


def cmd_attest(client: IsnadClient, args):
    """Create an attestation."""
    att = client.create_attestation(
        witness_id=args.witness,
        subject_id=args.subject,
        task=args.task,
        outcome=args.outcome or "positive",
    )
    print(f"✅ Attestation created:")
    print(f"   ID:      {att['attestation_id']}")
    print(f"   Witness: {args.witness}")
    print(f"   Subject: {args.subject}")
    print(f"   Task:    {args.task}")
    print(f"   Outcome: {args.outcome or 'positive'}")
    return att


def cmd_verify(client: IsnadClient, args):
    """Verify an attestation."""
    result = client.verify_attestation(args.attestation_id)
    status = "✅ VALID" if result.get("valid") else "❌ INVALID"
    print(f"{status}: {args.attestation_id}")
    if not result.get("valid"):
        print(f"   Reason: {result.get('reason', 'unknown')}")
    return result


def cmd_score(client: IsnadClient, args):
    """Get trust score for an agent."""
    score = client.trust_score(args.agent_id)
    ts = score.get("trust_score", score.get("score", "N/A"))
    level = score.get("level", "unknown")
    print(f"📊 Trust Score for {args.agent_id}:")
    print(f"   Score: {ts}")
    print(f"   Level: {level}")
    detectors = score.get("detectors", {})
    if detectors:
        print(f"   Detectors:")
        for name, val in detectors.items():
            print(f"     {name}: {val}")
    return score


def cmd_chain(client: IsnadClient, args):
    """Get attestation chain for an agent."""
    chain = client.get_chain(args.agent_id)
    attestations = chain.get("attestations", chain.get("chain", []))
    print(f"🔗 Chain for {args.agent_id}: {len(attestations)} attestations")
    for i, att in enumerate(attestations):
        print(f"   [{i+1}] {att.get('witness_id', '?')} → {att.get('task', '?')} ({att.get('outcome', '?')})")
    return chain


def cmd_demo(client: IsnadClient, args):
    """Run an interactive demo of the trust protocol."""
    print("🎭 Agent Trust Protocol — Interactive Demo\n")
    
    # Step 1: Generate two agents
    print("Step 1: Creating two agents...")
    alice = client.generate_keys()
    bob = client.generate_keys()
    print(f"   Alice: {alice['agent_id'][:16]}...")
    print(f"   Bob:   {bob['agent_id'][:16]}...")
    
    # Step 2: Alice attests Bob
    print("\nStep 2: Alice attests Bob did good code review...")
    att1 = client.create_attestation(
        witness_id=alice["agent_id"],
        subject_id=bob["agent_id"],
        task="code-review",
        outcome="positive",
    )
    print(f"   ✅ Attestation: {att1['attestation_id'][:16]}...")
    
    # Step 3: Verify
    print("\nStep 3: Verifying attestation...")
    v = client.verify_attestation(att1["attestation_id"])
    print(f"   {'✅ Valid' if v.get('valid') else '❌ Invalid'}")
    
    # Step 4: Check Bob's score
    print("\nStep 4: Bob's trust score...")
    score = client.trust_score(bob["agent_id"])
    ts = score.get("trust_score", score.get("score", "N/A"))
    print(f"   📊 Score: {ts}")
    
    # Step 5: Bob attests Alice back (cross-verification)
    print("\nStep 5: Bob attests Alice (cross-verification)...")
    att2 = client.create_attestation(
        witness_id=bob["agent_id"],
        subject_id=alice["agent_id"],
        task="data-analysis",
        outcome="positive",
    )
    print(f"   ✅ Cross-attestation: {att2['attestation_id'][:16]}...")
    
    # Final scores
    print("\n📊 Final Trust Scores:")
    for name, agent in [("Alice", alice), ("Bob", bob)]:
        s = client.trust_score(agent["agent_id"])
        print(f"   {name}: {s.get('trust_score', s.get('score', 'N/A'))}")
    
    print("\n🎉 Demo complete! Both agents now have verifiable trust chains.")


def main():
    parser = argparse.ArgumentParser(
        description="isnad CLI — Agent Trust Protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Sandbox API URL")
    
    sub = parser.add_subparsers(dest="command", help="Command")
    
    sub.add_parser("keygen", help="Generate agent keys")
    
    p_attest = sub.add_parser("attest", help="Create attestation")
    p_attest.add_argument("witness", help="Witness agent ID")
    p_attest.add_argument("subject", help="Subject agent ID")
    p_attest.add_argument("task", help="Task description")
    p_attest.add_argument("--outcome", choices=["positive", "negative"], default="positive")
    
    p_verify = sub.add_parser("verify", help="Verify attestation")
    p_verify.add_argument("attestation_id", help="Attestation ID")
    
    p_score = sub.add_parser("score", help="Get trust score")
    p_score.add_argument("agent_id", help="Agent ID")
    
    p_chain = sub.add_parser("chain", help="Get attestation chain")
    p_chain.add_argument("agent_id", help="Agent ID")
    
    sub.add_parser("demo", help="Run interactive demo")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    client = IsnadClient(args.url)
    
    commands = {
        "keygen": cmd_keygen,
        "attest": cmd_attest,
        "verify": cmd_verify,
        "score": cmd_score,
        "chain": cmd_chain,
        "demo": cmd_demo,
    }
    
    try:
        commands[args.command](client, args)
    except IsnadError as e:
        print(f"❌ API Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
