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
from isnad.client import IsnadClient, IsnadError

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


def cmd_audit(client: IsnadClient, args):
    """Generate compliance audit report for an agent."""
    print(f"📋 Compliance Audit Report — {args.agent_id}\n")
    print(f"{'='*60}")
    
    # Get chain
    chain = client.get_chain(args.agent_id)
    attestations = chain.get("attestations", chain.get("chain", []))
    
    # Get score
    score = client.trust_score(args.agent_id)
    ts = score.get("trust_score", score.get("score", "N/A"))
    level = score.get("level", "unknown")
    
    print(f"Agent:        {args.agent_id}")
    print(f"Trust Score:  {ts}")
    print(f"Trust Level:  {level}")
    print(f"Attestations: {len(attestations)}")
    print(f"{'='*60}\n")
    
    # Verify each attestation
    valid_count = 0
    invalid_count = 0
    witnesses = set()
    tasks = {}
    
    for att in attestations:
        att_id = att.get("attestation_id", att.get("id", "unknown"))
        try:
            v = client.verify_attestation(att_id)
            is_valid = v.get("valid", False)
        except Exception:
            is_valid = False
        
        if is_valid:
            valid_count += 1
            status = "✅"
        else:
            invalid_count += 1
            status = "❌"
        
        witness = att.get("witness_id", "?")
        task = att.get("task", "?")
        outcome = att.get("outcome", "?")
        witnesses.add(witness)
        tasks[task] = tasks.get(task, 0) + 1
        
        print(f"  {status} [{att_id[:12]}...] {witness[:12]}... → {task} ({outcome})")
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Valid:      {valid_count}/{len(attestations)}")
    print(f"  Invalid:    {invalid_count}/{len(attestations)}")
    print(f"  Witnesses:  {len(witnesses)} unique")
    print(f"  Tasks:      {', '.join(f'{k}({v})' for k,v in tasks.items())}")
    
    integrity = "PASS" if invalid_count == 0 and len(attestations) > 0 else "FAIL" if invalid_count > 0 else "INSUFFICIENT DATA"
    print(f"  Integrity:  {integrity}")
    print(f"{'='*60}")
    
    if args.output:
        import json as _json
        report = {
            "agent_id": args.agent_id,
            "trust_score": ts,
            "level": level,
            "total_attestations": len(attestations),
            "valid": valid_count,
            "invalid": invalid_count,
            "unique_witnesses": len(witnesses),
            "tasks": tasks,
            "integrity": integrity,
        }
        with open(args.output, "w") as f:
            _json.dump(report, f, indent=2)
        print(f"\n📄 Report saved to {args.output}")
    
    return {"integrity": integrity, "valid": valid_count, "invalid": invalid_count}


def cmd_export(client: IsnadClient, args):
    """Export agent data as JSON for integration."""
    chain = client.get_chain(args.agent_id)
    score = client.trust_score(args.agent_id)
    
    export = {
        "version": "isnad/1.0",
        "agent_id": args.agent_id,
        "trust_score": score,
        "chain": chain,
    }
    
    output = json.dumps(export, indent=2)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"📦 Exported to {args.output}")
    else:
        print(output)
    
    return export


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
    
    p_audit = sub.add_parser("audit", help="Generate compliance audit report")
    p_audit.add_argument("agent_id", help="Agent ID to audit")
    p_audit.add_argument("-o", "--output", help="Save report to JSON file")
    
    p_export = sub.add_parser("export", help="Export agent data as JSON")
    p_export.add_argument("agent_id", help="Agent ID")
    p_export.add_argument("-o", "--output", help="Output file (stdout if omitted)")
    
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
        "audit": cmd_audit,
        "export": cmd_export,
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
