#!/usr/bin/env python3
"""Tests for isnad MCP tool definitions and handlers."""

import json
import pytest
from nacl.encoding import HexEncoder

from mcp_tools import ISNAD_MCP_TOOLS, handle_mcp_call, get_mcp_manifest
from isnad import AgentIdentity, Attestation, TrustChain


def _make_att(witness, subject_id, task="test", evidence=""):
    att = Attestation(subject=subject_id, witness=witness.agent_id,
                      task=task, evidence=evidence)
    att.sign(witness)
    return att


class TestManifest:
    def test_structure(self):
        m = get_mcp_manifest()
        assert m["name"] == "isnad-trust-protocol"
        assert len(m["tools"]) == 6

    def test_tools_have_fields(self):
        for t in ISNAD_MCP_TOOLS:
            assert "name" in t and "description" in t and "inputSchema" in t


class TestCreateIdentity:
    def test_creates(self):
        r = handle_mcp_call("isnad_create_identity", {})
        assert len(r["public_key_hex"]) == 64
        assert "signing_key_hex" in r

    def test_unique(self):
        r1 = handle_mcp_call("isnad_create_identity", {})
        r2 = handle_mcp_call("isnad_create_identity", {})
        assert r1["public_key_hex"] != r2["public_key_hex"]


class TestAttest:
    def setup_method(self):
        self.w = AgentIdentity()
        self.s = AgentIdentity()
        self.w_hex = self.w.signing_key.encode(encoder=HexEncoder).decode()

    def test_creates(self):
        r = handle_mcp_call("isnad_attest", {
            "witness_key_hex": self.w_hex,
            "subject_id": self.s.agent_id,
            "task": "code_review"
        })
        assert r["signature_valid"] is True
        assert r["attestation"]["task"] == "code_review"

    def test_with_evidence(self):
        r = handle_mcp_call("isnad_attest", {
            "witness_key_hex": self.w_hex,
            "subject_id": self.s.agent_id,
            "task": "analysis",
            "evidence": "https://example.com/proof"
        })
        assert r["attestation"]["evidence"] == "https://example.com/proof"

    def test_roundtrip(self):
        r1 = handle_mcp_call("isnad_attest", {
            "witness_key_hex": self.w_hex,
            "subject_id": self.s.agent_id,
            "task": "delegation"
        })
        r2 = handle_mcp_call("isnad_verify_attestation", {
            "attestation_json": r1["attestation_json"]
        })
        assert r2["valid"] is True


class TestVerify:
    def test_valid(self):
        w = AgentIdentity()
        s = AgentIdentity()
        att = _make_att(w, s.agent_id)
        r = handle_mcp_call("isnad_verify_attestation", {
            "attestation_json": json.dumps(att.to_dict())
        })
        assert r["valid"] is True

    def test_tampered(self):
        w = AgentIdentity()
        s = AgentIdentity()
        att = _make_att(w, s.agent_id)
        d = att.to_dict()
        d["task"] = "tampered"
        r = handle_mcp_call("isnad_verify_attestation", {
            "attestation_json": json.dumps(d)
        })
        assert r["valid"] is False


class TestTrustScore:
    def test_with_attestations(self):
        w1, w2, s = AgentIdentity(), AgentIdentity(), AgentIdentity()
        atts = [_make_att(w, s.agent_id).to_dict() for w in [w1, w2]]
        r = handle_mcp_call("isnad_trust_score", {
            "agent_id": s.agent_id,
            "attestations_json": json.dumps(atts)
        })
        assert r["trust_score"] > 0
        assert r["attestations_loaded"] == 2

    def test_zero(self):
        s = AgentIdentity()
        r = handle_mcp_call("isnad_trust_score", {
            "agent_id": s.agent_id,
            "attestations_json": "[]"
        })
        assert r["trust_score"] == 0


class TestChainTrust:
    def test_direct(self):
        a, b = AgentIdentity(), AgentIdentity()
        att = _make_att(a, b.agent_id, "delegation")
        r = handle_mcp_call("isnad_chain_trust", {
            "source_id": a.agent_id,
            "target_id": b.agent_id,
            "attestations_json": json.dumps([att.to_dict()])
        })
        assert r["transitive_trust"] > 0

    def test_no_path(self):
        a, b = AgentIdentity(), AgentIdentity()
        r = handle_mcp_call("isnad_chain_trust", {
            "source_id": a.agent_id,
            "target_id": b.agent_id,
            "attestations_json": "[]"
        })
        assert r["transitive_trust"] == 0


class TestInspect:
    def test_inspect(self):
        w, s = AgentIdentity(), AgentIdentity()
        att = _make_att(w, s.agent_id, "review")
        r = handle_mcp_call("isnad_inspect", {
            "agent_id": s.agent_id,
            "attestations_json": json.dumps([att.to_dict()])
        })
        assert r["total_attestations"] == 1
        assert r["unique_witnesses"] == 1


class TestUnknown:
    def test_raises(self):
        with pytest.raises(ValueError):
            handle_mcp_call("nope", {})
