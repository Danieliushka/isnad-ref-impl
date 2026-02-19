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


def cmd_health(client: IsnadClient, args):
    """Check sandbox server health and connectivity."""
    try:
        info = client.health()
        print("✅ isnad sandbox is healthy")
        for k, v in info.items():
            print(f"   {k}: {v}")
    except Exception as e:
        print(f"❌ Cannot reach sandbox at {client.base_url}")
        print(f"   Error: {e}")
        sys.exit(1)
    return info


def cmd_revoke(client: IsnadClient, args):
    """Revoke an attestation."""
    from isnad.revocation import RevocationReason, RevocationList

    reason_map = {
        "key_compromise": RevocationReason.KEY_COMPROMISE,
        "superseded": RevocationReason.SUPERSEDED,
        "ceased_operation": RevocationReason.CEASED_OPERATION,
        "privilege_withdrawn": RevocationReason.PRIVILEGE_WITHDRAWN,
    }
    reason = reason_map.get(args.reason)
    if not reason:
        print(f"❌ Unknown reason: {args.reason}")
        print(f"   Valid: {', '.join(reason_map.keys())}")
        sys.exit(1)

    rl = RevocationList()
    record = rl.revoke(args.attestation_id, reason=reason, revoked_by=args.revoked_by or "cli-user")
    print(f"🚫 Attestation revoked:")
    print(f"   ID:     {record.attestation_id}")
    print(f"   Reason: {record.reason.value}")
    print(f"   By:     {record.revoked_by}")
    print(f"   Time:   {record.timestamp}")
    return record


def cmd_compare(client: IsnadClient, args):
    """Compare trust scores of two agents side-by-side."""
    score_a = client.trust_score(args.agent_a)
    score_b = client.trust_score(args.agent_b)

    name_a = args.agent_a[:12]
    name_b = args.agent_b[:12]

    print(f"📊 Trust Score Comparison")
    print(f"{'─' * 50}")
    print(f"   Agent A ({name_a}...): {score_a.get('trust_score', 'N/A')}")
    print(f"   Agent B ({name_b}...): {score_b.get('trust_score', 'N/A')}")

    sa = score_a.get('trust_score', 0)
    sb = score_b.get('trust_score', 0)
    if isinstance(sa, (int, float)) and isinstance(sb, (int, float)):
        diff = abs(sa - sb)
        leader = "A" if sa > sb else "B" if sb > sa else "tie"
        if leader == "tie":
            print(f"   Result: Equal trust scores")
        else:
            print(f"   Result: Agent {leader} leads by {diff:.2f}")
    return {"agent_a": score_a, "agent_b": score_b}


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


def cmd_batch_verify(client: IsnadClient, args):
    """Batch verify attestations from a JSON file."""
    with open(args.file, "r") as f:
        data = json.load(f)

    attestations = data if isinstance(data, list) else data.get("attestations", [data])
    
    results = {"total": len(attestations), "valid": 0, "invalid": 0, "errors": []}
    
    for i, att in enumerate(attestations):
        att_id = att.get("id") or att.get("attestation_id")
        if not att_id:
            results["errors"].append({"index": i, "error": "missing attestation id"})
            results["invalid"] += 1
            continue
        try:
            result = client.verify_attestation(att_id)
            if result.get("valid"):
                results["valid"] += 1
            else:
                results["invalid"] += 1
                results["errors"].append({"index": i, "id": att_id, "error": "verification failed"})
        except IsnadError as e:
            results["invalid"] += 1
            results["errors"].append({"index": i, "id": att_id, "error": str(e)})
    
    print(f"📊 Batch Verification Results:")
    print(f"   Total:   {results['total']}")
    print(f"   ✅ Valid:  {results['valid']}")
    print(f"   ❌ Invalid: {results['invalid']}")
    
    if results["errors"] and args.verbose:
        print(f"\n   Errors:")
        for err in results["errors"]:
            print(f"   [{err.get('index')}] {err.get('id', 'N/A')}: {err['error']}")
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n📦 Report saved to {args.output}")
    
    return results


def cmd_import(client: IsnadClient, args):
    """Import agent trust data from an isnad export file."""
    with open(args.file, "r") as f:
        data = json.load(f)
    
    version = data.get("version", "unknown")
    if not version.startswith("isnad/"):
        print(f"⚠️  Warning: unknown format version '{version}'", file=sys.stderr)
    
    agent_id = data.get("agent_id")
    chain = data.get("chain", {})
    attestations = chain.get("attestations", [])
    
    print(f"📥 Importing trust data for agent {agent_id}")
    print(f"   Format: {version}")
    print(f"   Attestations: {len(attestations)}")
    
    imported = 0
    skipped = 0
    
    for att in attestations:
        try:
            # Re-create attestation in local sandbox
            client.create_attestation(
                witness_id=att.get("witness", att.get("witness_id", "")),
                subject_id=att.get("subject", att.get("subject_id", agent_id)),
                task=att.get("task", att.get("scope", "imported")),
                evidence=att.get("evidence", ""),
            )
            imported += 1
        except IsnadError:
            skipped += 1
    
    print(f"\n   ✅ Imported: {imported}")
    if skipped:
        print(f"   ⏭️  Skipped:  {skipped}")
    
    return {"imported": imported, "skipped": skipped}


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
    
    sub.add_parser("health", help="Check sandbox health")

    p_revoke = sub.add_parser("revoke", help="Revoke an attestation")
    p_revoke.add_argument("attestation_id", help="Attestation ID to revoke")
    p_revoke.add_argument("--reason", default="privilege_withdrawn",
                          choices=["key_compromise", "superseded", "ceased_operation", "privilege_withdrawn"],
                          help="Revocation reason")
    p_revoke.add_argument("--revoked-by", default="", help="ID of revoking agent")

    p_compare = sub.add_parser("compare", help="Compare trust scores of two agents")
    p_compare.add_argument("agent_a", help="First agent ID")
    p_compare.add_argument("agent_b", help="Second agent ID")

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
    
    p_batch = sub.add_parser("batch-verify", help="Batch verify attestations from JSON file")
    p_batch.add_argument("file", help="JSON file with attestations")
    p_batch.add_argument("-o", "--output", help="Save report to JSON file")
    p_batch.add_argument("-v", "--verbose", action="store_true", help="Show error details")
    
    p_import = sub.add_parser("import", help="Import trust data from isnad export file")
    p_import.add_argument("file", help="isnad export JSON file")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    client = IsnadClient(args.url)
    
    commands = {
        "health": cmd_health,
        "keygen": cmd_keygen,
        "attest": cmd_attest,
        "verify": cmd_verify,
        "score": cmd_score,
        "chain": cmd_chain,
        "demo": cmd_demo,
        "audit": cmd_audit,
        "export": cmd_export,
        "batch-verify": cmd_batch_verify,
        "import": cmd_import,
        "revoke": cmd_revoke,
        "compare": cmd_compare,
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
