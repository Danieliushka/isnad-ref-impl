#!/usr/bin/env python3
"""
isnad MCP Tool Definitions — Model Context Protocol integration.

Exposes isnad operations as MCP-compatible tool schemas for AI agents.
"""

import json
import time as _time
from typing import Any

from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

from isnad import AgentIdentity, Attestation, TrustChain

ISNAD_MCP_TOOLS = [
    {
        "name": "isnad_create_identity",
        "description": "Create a new Ed25519 agent identity keypair for isnad participation.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "isnad_attest",
        "description": "Create a signed attestation: witness attests that subject completed a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "witness_key_hex": {"type": "string", "description": "Hex signing key of witness"},
                "subject_id": {"type": "string", "description": "Agent ID (pubkey hex) of the subject"},
                "task": {"type": "string", "description": "Task description"},
                "evidence": {"type": "string", "description": "URI to evidence/proof (optional)"}
            },
            "required": ["witness_key_hex", "subject_id", "task"]
        }
    },
    {
        "name": "isnad_verify_attestation",
        "description": "Verify a single attestation's cryptographic signature.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "attestation_json": {"type": "string", "description": "JSON attestation to verify"}
            },
            "required": ["attestation_json"]
        }
    },
    {
        "name": "isnad_trust_score",
        "description": "Compute trust score (0-1) for an agent from attestations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent pubkey hex"},
                "attestations_json": {"type": "string", "description": "JSON array of attestations"},
                "scope": {"type": "string", "description": "Optional task scope filter"}
            },
            "required": ["agent_id", "attestations_json"]
        }
    },
    {
        "name": "isnad_chain_trust",
        "description": "Compute transitive trust between two agents via attestation chains (BFS with decay).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "Source agent pubkey hex"},
                "target_id": {"type": "string", "description": "Target agent pubkey hex"},
                "attestations_json": {"type": "string", "description": "JSON array of attestations"},
                "max_hops": {"type": "integer", "description": "Max chain depth (default 5)"}
            },
            "required": ["source_id", "target_id", "attestations_json"]
        }
    },
    {
        "name": "isnad_inspect",
        "description": "Inspect attestations for an agent: witnesses, tasks, trust lineage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent pubkey hex"},
                "attestations_json": {"type": "string", "description": "JSON array of attestations"}
            },
            "required": ["agent_id", "attestations_json"]
        }
    }
]


def handle_mcp_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Handle an MCP tool call."""
    handlers = {
        "isnad_create_identity": _handle_create_identity,
        "isnad_attest": _handle_attest,
        "isnad_verify_attestation": _handle_verify,
        "isnad_trust_score": _handle_trust_score,
        "isnad_chain_trust": _handle_chain_trust,
        "isnad_inspect": _handle_inspect,
    }
    handler = handlers.get(tool_name)
    if not handler:
        raise ValueError(f"Unknown tool: {tool_name}")
    return handler(arguments)


def _handle_create_identity(_args: dict) -> dict:
    identity = AgentIdentity()
    return {
        "agent_id": identity.agent_id,
        "public_key_hex": identity.public_key_hex,
        "signing_key_hex": identity.signing_key.encode(encoder=HexEncoder).decode(),
        "warning": "Store signing_key_hex securely. Never share it."
    }


def _handle_attest(args: dict) -> dict:
    witness_key = SigningKey(args["witness_key_hex"], encoder=HexEncoder)
    witness = AgentIdentity(signing_key=witness_key)

    att = Attestation(
        subject=args["subject_id"],
        witness=witness.agent_id,
        task=args["task"],
        evidence=args.get("evidence", "")
    )
    att.sign(witness)

    return {
        "attestation": att.to_dict(),
        "attestation_json": json.dumps(att.to_dict()),
        "signature_valid": att.verify()
    }


def _handle_verify(args: dict) -> dict:
    data = json.loads(args["attestation_json"])
    att = Attestation.from_dict(data)
    valid = att.verify()
    return {
        "valid": valid,
        "attestation_id": att.attestation_id,
        "witness": att.witness[:16] + "...",
        "subject": att.subject[:16] + "...",
        "task": att.task
    }


def _handle_trust_score(args: dict) -> dict:
    attestations = json.loads(args["attestations_json"])
    chain = TrustChain()
    loaded = 0
    for d in attestations:
        att = Attestation.from_dict(d)
        if chain.add(att):
            loaded += 1

    score = chain.trust_score(args["agent_id"], scope=args.get("scope"))
    return {
        "trust_score": round(score, 4),
        "attestations_loaded": loaded,
        "attestations_total": len(attestations),
        "scope": args.get("scope", "all")
    }


def _handle_chain_trust(args: dict) -> dict:
    attestations = json.loads(args["attestations_json"])
    chain = TrustChain()
    for d in attestations:
        chain.add(Attestation.from_dict(d))

    trust = chain.chain_trust(args["source_id"], args["target_id"],
                               max_hops=args.get("max_hops", 5))
    return {
        "transitive_trust": round(trust, 4),
        "source": args["source_id"][:16] + "...",
        "target": args["target_id"][:16] + "...",
        "max_hops": args.get("max_hops", 5)
    }


def _handle_inspect(args: dict) -> dict:
    attestations_data = json.loads(args["attestations_json"])
    agent = args["agent_id"]

    relevant = [a for a in attestations_data if a.get("subject") == agent]
    witnesses = list(set(a.get("witness", "?")[:16] for a in relevant))

    summary = []
    for a in relevant:
        summary.append({
            "witness": a.get("witness", "?")[:16] + "...",
            "task": a.get("task", "?"),
            "timestamp": a.get("timestamp", "?"),
            "evidence": a.get("evidence", "")[:100]
        })

    return {
        "agent": agent[:16] + "...",
        "total_attestations": len(relevant),
        "unique_witnesses": len(witnesses),
        "witnesses": witnesses,
        "attestations": summary
    }


def get_mcp_manifest() -> dict:
    """MCP server manifest for tool registration."""
    return {
        "name": "isnad-trust-protocol",
        "version": "0.1.0",
        "description": "Cryptographic provenance chains and trust scoring for AI agents.",
        "tools": ISNAD_MCP_TOOLS
    }


if __name__ == "__main__":
    print(json.dumps(get_mcp_manifest(), indent=2))
