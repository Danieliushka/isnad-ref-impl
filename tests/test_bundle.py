"""Tests for TrustChain bundle export/import (isnad-bundle/v1)."""

import json
import pytest
from isnad.core import AgentIdentity, Attestation, TrustChain


def _make_chain():
    """Create a small trust chain with 3 agents and attestations."""
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()

    chain = TrustChain()
    a1 = Attestation(
        witness=alice.agent_id, subject=bob.agent_id,
        task="code-review", evidence="https://example.com/pr/1"
    ).sign(alice)
    a2 = Attestation(
        witness=bob.agent_id, subject=charlie.agent_id,
        task="deployment", evidence="https://example.com/deploy/1"
    ).sign(bob)
    chain.add(a1)
    chain.add(a2)
    return chain, alice, bob, charlie


class TestBundleExport:
    def test_unsigned_export(self):
        chain, *_ = _make_chain()
        bundle = chain.export_bundle()

        assert bundle["version"] == "isnad-bundle/v1"
        assert bundle["stats"]["count"] == 2
        assert bundle["stats"]["subjects"] == 2
        assert bundle["stats"]["witnesses"] == 2
        assert len(bundle["attestations"]) == 2
        assert "signature" not in bundle
        assert "created_at" in bundle

    def test_signed_export(self):
        chain, alice, *_ = _make_chain()
        bundle = chain.export_bundle(signer=alice)

        assert "signature" in bundle
        assert bundle["signed_by"] == alice.agent_id
        assert bundle["signer_pubkey"] == alice.public_key_hex

    def test_export_with_metadata(self):
        chain, *_ = _make_chain()
        meta = {"source": "test", "purpose": "interop"}
        bundle = chain.export_bundle(metadata=meta)

        assert bundle["metadata"] == meta

    def test_empty_chain_export(self):
        chain = TrustChain()
        bundle = chain.export_bundle()

        assert bundle["stats"]["count"] == 0
        assert bundle["attestations"] == []


class TestBundleImport:
    def test_roundtrip_unsigned(self):
        chain, *_ = _make_chain()
        bundle = chain.export_bundle()

        restored = TrustChain.from_bundle(bundle, verify_signature=False)
        assert len(restored.attestations) == 2

    def test_roundtrip_signed(self):
        chain, alice, *_ = _make_chain()
        bundle = chain.export_bundle(signer=alice)

        restored = TrustChain.from_bundle(bundle)
        assert len(restored.attestations) == 2

    def test_tampered_bundle_rejected(self):
        chain, alice, *_ = _make_chain()
        bundle = chain.export_bundle(signer=alice)

        # Tamper with attestation data
        bundle["attestations"][0]["task"] = "hacked"

        with pytest.raises(ValueError, match="signature verification failed"):
            TrustChain.from_bundle(bundle)

    def test_invalid_version_rejected(self):
        bundle = {"version": "isnad-bundle/v99", "attestations": []}

        with pytest.raises(ValueError, match="Unsupported bundle version"):
            TrustChain.from_bundle(bundle)

    def test_missing_version_rejected(self):
        bundle = {"attestations": []}

        with pytest.raises(ValueError, match="Unsupported bundle version"):
            TrustChain.from_bundle(bundle)

    def test_skip_signature_verification(self):
        chain, alice, *_ = _make_chain()
        bundle = chain.export_bundle(signer=alice)
        bundle["attestations"][0]["task"] = "hacked"

        # Should NOT raise when verify_signature=False
        # But tampered attestation fails internal sig check → filtered out
        restored = TrustChain.from_bundle(bundle, verify_signature=False)
        assert len(restored.attestations) == 1  # only untampered one survives

    def test_scores_preserved(self):
        chain, _, bob, charlie = _make_chain()
        original_bob_score = chain.trust_score(bob.agent_id)
        original_charlie_score = chain.trust_score(charlie.agent_id)

        bundle = chain.export_bundle()
        restored = TrustChain.from_bundle(bundle, verify_signature=False)

        assert restored.trust_score(bob.agent_id) == original_bob_score
        assert restored.trust_score(charlie.agent_id) == original_charlie_score

    def test_json_serializable(self):
        chain, alice, *_ = _make_chain()
        bundle = chain.export_bundle(signer=alice, metadata={"test": True})

        # Must be JSON-serializable
        json_str = json.dumps(bundle)
        parsed = json.loads(json_str)
        restored = TrustChain.from_bundle(parsed)
        assert len(restored.attestations) == 2
