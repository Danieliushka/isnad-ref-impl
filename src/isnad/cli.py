#!/usr/bin/env python3
"""
isnad CLI — Offline command-line interface for the Agent Trust Protocol.

Works directly with core modules (no server required).

Commands:
    attest   - Create a signed attestation
    verify   - Verify an attestation signature
    chain    - Show trust chain for an agent
    score    - Calculate trust score
    revoke   - Revoke an attestation
    delegate - Manage delegations
    stats    - Network statistics
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional


def _output(data: dict, args: argparse.Namespace, human_fn=None):
    """Output data as JSON or pretty-printed."""
    if getattr(args, 'json', False):
        print(json.dumps(data, indent=2, default=str))
    elif human_fn:
        human_fn(data)
    else:
        print(json.dumps(data, indent=2, default=str))


def _load_identity(keyfile: str):
    """Load agent identity from keyfile."""
    from isnad.core import AgentIdentity
    return AgentIdentity.load(keyfile)


def _load_chain(chainfile: str):
    """Load trust chain from file."""
    from isnad.core import TrustChain
    return TrustChain.load(chainfile)


# ─── Commands ──────────────────────────────────────────────────────

def cmd_attest(args):
    """Create a signed attestation."""
    from isnad.core import AgentIdentity, Attestation

    witness = AgentIdentity.load(args.keyfile)
    att = Attestation(
        subject=args.subject,
        witness=witness.agent_id,
        task=args.task,
        evidence=args.evidence or "",
    )
    att.sign(witness)

    result = att.to_dict()

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)

    def human(d):
        print(f"✅ Attestation created")
        print(f"   ID:       {d['attestation_id']}")
        print(f"   Witness:  {d['witness']}")
        print(f"   Subject:  {d['subject']}")
        print(f"   Task:     {d['task']}")
        print(f"   Time:     {d['timestamp']}")
        if args.output:
            print(f"   Saved to: {args.output}")

    _output(result, args, human)
    return result


def cmd_verify(args):
    """Verify an attestation from a JSON file or stdin."""
    from isnad.core import Attestation
    from isnad.revocation import RevocationList

    if args.file == '-':
        data = json.load(sys.stdin)
    else:
        with open(args.file) as f:
            data = json.load(f)

    att = Attestation.from_dict(data)
    sig_valid = att.verify()

    revoked = False
    if args.revocation_list:
        with open(args.revocation_list) as f:
            rl_data = f.read()
        rl = RevocationList.from_json(rl_data)
        revoked = rl.is_revoked(att.attestation_id)

    result = {
        "attestation_id": att.attestation_id,
        "signature_valid": sig_valid,
        "revoked": revoked,
        "valid": sig_valid and not revoked,
        "witness": att.witness,
        "subject": att.subject,
        "task": att.task,
    }

    def human(d):
        if d['valid']:
            print(f"✅ VALID: {d['attestation_id']}")
        else:
            print(f"❌ INVALID: {d['attestation_id']}")
            if not d['signature_valid']:
                print("   Reason: signature verification failed")
            if d['revoked']:
                print("   Reason: attestation has been revoked")
        print(f"   Witness: {d['witness']}")
        print(f"   Subject: {d['subject']}")
        print(f"   Task:    {d['task']}")

    _output(result, args, human)
    return result


def cmd_chain(args):
    """Show trust chain for an agent."""
    from isnad.core import TrustChain

    chain = TrustChain.load(args.chainfile)
    attestations = chain._by_subject.get(args.agent_id, [])

    chain_data = []
    for att in attestations:
        chain_data.append({
            "attestation_id": att.attestation_id,
            "witness": att.witness,
            "task": att.task,
            "evidence": att.evidence,
            "timestamp": att.timestamp,
            "valid": att.verify(),
        })

    # Also show transitive trust if --from is specified
    transitive = None
    if args.source:
        transitive = chain.chain_trust(args.source, args.agent_id)

    result = {
        "agent_id": args.agent_id,
        "attestation_count": len(chain_data),
        "attestations": chain_data,
    }
    if transitive is not None:
        result["transitive_trust_from"] = args.source
        result["transitive_trust"] = transitive

    def human(d):
        print(f"🔗 Trust chain for {d['agent_id']}: {d['attestation_count']} attestation(s)")
        for i, a in enumerate(d['attestations']):
            status = "✅" if a['valid'] else "❌"
            print(f"   [{i+1}] {status} {a['witness']} → {a['task']}")
            if a['evidence']:
                print(f"       evidence: {a['evidence']}")
        if 'transitive_trust' in d:
            print(f"\n   Transitive trust from {d['transitive_trust_from']}: {d['transitive_trust']:.4f}")

    _output(result, args, human)
    return result


def cmd_score(args):
    """Calculate trust score for an agent."""
    from isnad.core import TrustChain

    chain = TrustChain.load(args.chainfile)
    score = chain.trust_score(args.agent_id, scope=args.scope)

    attestations = chain._by_subject.get(args.agent_id, [])
    witnesses = list({a.witness for a in attestations})

    result = {
        "agent_id": args.agent_id,
        "trust_score": round(score, 4),
        "scope": args.scope,
        "attestation_count": len(attestations),
        "unique_witnesses": len(witnesses),
        "witnesses": witnesses,
    }

    def human(d):
        print(f"📊 Trust Score for {d['agent_id']}")
        print(f"   Score:        {d['trust_score']}")
        if d['scope']:
            print(f"   Scope:        {d['scope']}")
        print(f"   Attestations: {d['attestation_count']}")
        print(f"   Witnesses:    {d['unique_witnesses']}")

    _output(result, args, human)
    return result


def cmd_revoke(args):
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
        print(f"❌ Unknown reason: {args.reason}", file=sys.stderr)
        sys.exit(1)

    # Load existing list or create new
    if args.revocation_list:
        try:
            with open(args.revocation_list) as f:
                rl = RevocationList.from_json(f.read())
        except FileNotFoundError:
            rl = RevocationList()
    else:
        rl = RevocationList()

    record = rl.revoke(args.attestation_id, reason=reason, revoked_by=args.revoked_by or "cli")

    # Save if output specified
    outfile = args.output or args.revocation_list
    if outfile:
        with open(outfile, 'w') as f:
            f.write(rl.to_json())

    result = record.to_dict()

    def human(d):
        print(f"🚫 Attestation revoked")
        print(f"   ID:     {d['attestation_id']}")
        print(f"   Reason: {d['reason']}")
        print(f"   By:     {d['revoked_by']}")
        if outfile:
            print(f"   Saved:  {outfile}")

    _output(result, args, human)
    return result


def cmd_delegate(args):
    """Manage delegations."""
    from isnad.core import AgentIdentity
    from isnad.delegation import Delegation, DelegationRegistry
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder

    subcmd = args.delegate_command

    if subcmd == "create":
        principal = AgentIdentity.load(args.keyfile)
        sk = principal.signing_key

        deleg = Delegation(
            delegate_key_hex=args.delegate_key,
            delegator_key_hex=principal.public_key_hex,
            scope=args.scope,
            expires_at=args.expires,
            max_depth=args.max_depth,
        )

        registry = DelegationRegistry()
        if args.registry:
            try:
                registry.load(args.registry)
            except FileNotFoundError:
                pass

        deleg = registry.add(deleg, sk)

        if args.registry:
            registry.save(args.registry)

        result = deleg.to_dict()

        def human(d):
            print(f"✅ Delegation created")
            print(f"   Hash:      {d['content_hash']}")
            print(f"   Delegator: {d['delegator_key_hex'][:16]}...")
            print(f"   Delegate:  {d['delegate_key_hex'][:16]}...")
            print(f"   Scope:     {d.get('scope', 'all')}")
            print(f"   Max depth: {d['max_depth']}")

        _output(result, args, human)
        return result

    elif subcmd == "verify":
        registry = DelegationRegistry()
        registry.load(args.registry)
        valid, reason = registry.verify_chain(args.delegation_hash)

        result = {
            "delegation_hash": args.delegation_hash,
            "valid": valid,
            "reason": reason,
        }

        def human(d):
            status = "✅ VALID" if d['valid'] else "❌ INVALID"
            print(f"{status}: {d['delegation_hash']}")
            print(f"   Reason: {d['reason']}")

        _output(result, args, human)
        return result

    elif subcmd == "list":
        registry = DelegationRegistry()
        registry.load(args.registry)
        delegations = registry.get_delegations_for(args.delegate_key, scope=args.scope)

        items = [d.to_dict() for d in delegations]
        result = {"delegate": args.delegate_key, "delegations": items}

        def human(d):
            print(f"📋 Delegations for {d['delegate'][:16]}...")
            for i, item in enumerate(d['delegations']):
                exp = f" (expires {item.get('expires_at', 'never')})" if item.get('expires_at') else ""
                print(f"   [{i+1}] scope={item.get('scope', 'all')}{exp} depth={item['current_depth']}/{item['max_depth']}")

        _output(result, args, human)
        return result


def cmd_stats(args):
    """Network statistics using analytics module."""
    from isnad.core import TrustChain
    from isnad.analytics import TrustGraph, TrustAnalytics

    chain = TrustChain.load(args.chainfile)

    # Build graph from chain
    graph = TrustGraph()
    for att in chain.attestations:
        graph.add_edge(att.witness, att.subject, score=1.0)

    analytics = TrustAnalytics(graph)
    stats = analytics.network_stats()
    pr = analytics.pagerank()
    communities = analytics.communities()

    # Top agents by pagerank
    top_agents = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:args.top]

    result = {
        "network": {
            "agents": stats.num_agents,
            "edges": stats.num_edges,
            "density": round(stats.density, 4),
            "components": stats.num_components,
            "largest_component": stats.largest_component_size,
            "communities": stats.num_communities,
            "diameter": stats.diameter,
            "reciprocity": round(stats.reciprocity, 4),
            "avg_clustering": round(stats.avg_clustering, 4),
        },
        "top_agents": [
            {"agent_id": a, "pagerank": round(s, 6)} for a, s in top_agents
        ],
        "communities": [
            {"id": i, "size": len(c), "members": sorted(c)}
            for i, c in enumerate(communities)
        ],
    }

    def human(d):
        n = d['network']
        print(f"📊 Network Statistics")
        print(f"   Agents:          {n['agents']}")
        print(f"   Edges:           {n['edges']}")
        print(f"   Density:         {n['density']}")
        print(f"   Components:      {n['components']}")
        print(f"   Largest:         {n['largest_component']}")
        print(f"   Communities:     {n['communities']}")
        print(f"   Diameter:        {n['diameter']}")
        print(f"   Reciprocity:     {n['reciprocity']}")
        print(f"   Avg clustering:  {n['avg_clustering']}")
        if d['top_agents']:
            print(f"\n   Top agents by PageRank:")
            for ta in d['top_agents']:
                print(f"     {ta['agent_id'][:24]}... PR={ta['pagerank']}")
        if d['communities']:
            print(f"\n   Communities:")
            for c in d['communities']:
                print(f"     [{c['id']}] {c['size']} members")

    _output(result, args, human)
    return result


# ─── Parser ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isnad",
        description="isnad — Agent Trust Protocol CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # attest
    p = sub.add_parser("attest", help="Create a signed attestation")
    p.add_argument("subject", help="Subject agent ID")
    p.add_argument("task", help="Task description")
    p.add_argument("-k", "--keyfile", required=True, help="Witness identity keyfile")
    p.add_argument("-e", "--evidence", default="", help="Evidence URI")
    p.add_argument("-o", "--output", help="Save attestation to file")

    # verify
    p = sub.add_parser("verify", help="Verify an attestation")
    p.add_argument("file", help="Attestation JSON file (- for stdin)")
    p.add_argument("-r", "--revocation-list", help="Revocation list file to check against")

    # chain
    p = sub.add_parser("chain", help="Show trust chain for an agent")
    p.add_argument("agent_id", help="Agent ID")
    p.add_argument("-c", "--chainfile", required=True, help="Chain JSON file")
    p.add_argument("-f", "--source", help="Compute transitive trust from this agent")

    # score
    p = sub.add_parser("score", help="Calculate trust score")
    p.add_argument("agent_id", help="Agent ID")
    p.add_argument("-c", "--chainfile", required=True, help="Chain JSON file")
    p.add_argument("-s", "--scope", help="Filter by scope/task type")

    # revoke
    p = sub.add_parser("revoke", help="Revoke an attestation")
    p.add_argument("attestation_id", help="Attestation ID to revoke")
    p.add_argument("--reason", default="privilege_withdrawn",
                   choices=["key_compromise", "superseded", "ceased_operation", "privilege_withdrawn"])
    p.add_argument("--revoked-by", default="", help="ID of revoking agent")
    p.add_argument("-r", "--revocation-list", help="Existing revocation list file")
    p.add_argument("-o", "--output", help="Output revocation list file")

    # delegate
    p = sub.add_parser("delegate", help="Manage delegations")
    dsub = p.add_subparsers(dest="delegate_command", help="Delegation subcommands")

    dp = dsub.add_parser("create", help="Create a delegation")
    dp.add_argument("delegate_key", help="Delegate's public key hex")
    dp.add_argument("-k", "--keyfile", required=True, help="Principal identity keyfile")
    dp.add_argument("-s", "--scope", help="Scope constraint")
    dp.add_argument("-e", "--expires", help="Expiry ISO timestamp")
    dp.add_argument("-d", "--max-depth", type=int, default=1, help="Max sub-delegation depth")
    dp.add_argument("-r", "--registry", help="Registry file to save to")

    dp = dsub.add_parser("verify", help="Verify a delegation chain")
    dp.add_argument("delegation_hash", help="Delegation hash to verify")
    dp.add_argument("-r", "--registry", required=True, help="Registry file")

    dp = dsub.add_parser("list", help="List delegations for an agent")
    dp.add_argument("delegate_key", help="Delegate's public key hex")
    dp.add_argument("-r", "--registry", required=True, help="Registry file")
    dp.add_argument("-s", "--scope", help="Filter by scope")

    # stats
    p = sub.add_parser("stats", help="Network statistics")
    p.add_argument("-c", "--chainfile", required=True, help="Chain JSON file")
    p.add_argument("-t", "--top", type=int, default=10, help="Top N agents to show")

    return parser


def main(argv: Optional[list[str]] = None) -> Optional[dict]:
    """CLI entry point. Returns result dict for testing."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "attest": cmd_attest,
        "verify": cmd_verify,
        "chain": cmd_chain,
        "score": cmd_score,
        "revoke": cmd_revoke,
        "delegate": cmd_delegate,
        "stats": cmd_stats,
    }

    try:
        return commands[args.command](args)
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
