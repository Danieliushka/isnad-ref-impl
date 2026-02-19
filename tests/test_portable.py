"""Tests for isnad.portable — Portable Trust Chain Export/Import."""

import json
import pytest
from isnad.core import TrustChain, Attestation, AgentIdentity, RevocationRegistry
from isnad.portable import (
    export_chain, bundle_to_json, bundle_from_json,
    verify_bundle, TrustBundle, PortableAttestation, IPTB_VERSION,
)


def _make_signed_attestation(subject: AgentIdentity, witness: AgentIdentity, task: str) -> Attestation:
    att = Attestation(
        subject=subject.agent_id,
        witness=witness.agent_id,
        task=task,
        evidence="test://evidence",
        witness_pubkey=witness.public_key_hex,
    )
    att.sign(witness)
    return att


@pytest.fixture
def setup_chain():
    """Create a trust chain with attestations."""
    rev_reg = RevocationRegistry()
    chain = TrustChain(revocation_registry=rev_reg)
    alice = AgentIdentity()
    bob = AgentIdentity()
    carol = AgentIdentity()

    chain.add(_make_signed_attestation(alice, bob, "code_review"))
    chain.add(_make_signed_attestation(alice, carol, "security_audit"))
    chain.add(_make_signed_attestation(bob, alice, "documentation"))

    return chain, rev_reg, alice, bob, carol


def test_export_basic(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id, alice.public_key_hex, rev_reg)

    assert bundle.version == IPTB_VERSION
    assert bundle.agent_id == alice.agent_id
    assert bundle.agent_pubkey == alice.public_key_hex
    assert len(bundle.attestations) == 2
    assert bundle.trust_score is not None
    assert bundle.bundle_hash != ""


def test_export_only_subject_attestations(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id)
    tasks = {a.task for a in bundle.attestations}
    assert "code_review" in tasks
    assert "security_audit" in tasks
    assert "documentation" not in tasks


def test_bundle_integrity(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id)

    assert bundle.verify_integrity() is True

    # Tamper attestation task (in hash)
    original_task = bundle.attestations[0].task
    bundle.attestations[0].task = "tampered"
    assert bundle.verify_integrity() is False
    bundle.attestations[0].task = original_task


def test_json_roundtrip(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id, alice.public_key_hex, rev_reg)

    json_str = bundle_to_json(bundle)
    restored = bundle_from_json(json_str)

    assert restored.agent_id == bundle.agent_id
    assert restored.agent_pubkey == bundle.agent_pubkey
    assert restored.version == bundle.version
    assert len(restored.attestations) == len(bundle.attestations)
    assert restored.bundle_hash == bundle.bundle_hash
    assert restored.verify_integrity() is True


def test_verify_bundle(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id, rev_reg=rev_reg)

    result = verify_bundle(bundle)
    assert result["integrity"] is True
    assert result["version_ok"] is True
    assert result["attestation_count"] == 2
    assert result["revocation_count"] == 0
    assert result["effective_attestations"] == 2


def test_empty_chain():
    chain = TrustChain()
    agent = AgentIdentity()
    bundle = export_chain(chain, agent.agent_id)

    assert len(bundle.attestations) == 0
    assert bundle.verify_integrity() is True
    result = verify_bundle(bundle)
    assert result["attestation_count"] == 0
    assert result["effective_attestations"] == 0


def test_metadata(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    meta = {"platform": "ugig.net", "exported_by": "gendolf"}
    bundle = export_chain(chain, alice.agent_id, metadata=meta)

    assert bundle.metadata["platform"] == "ugig.net"
    json_str = bundle_to_json(bundle)
    restored = bundle_from_json(json_str)
    assert restored.metadata["platform"] == "ugig.net"


def test_bundle_seal_idempotent(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id)
    h1 = bundle.bundle_hash
    bundle.seal()
    assert bundle.bundle_hash == h1


def test_portable_attestation_fields(setup_chain):
    chain, rev_reg, alice, bob, carol = setup_chain
    bundle = export_chain(chain, alice.agent_id)
    att = bundle.attestations[0]
    assert att.subject == alice.agent_id
    assert att.witness_pubkey != ""
    assert att.signature != ""
    assert att.attestation_id != ""
