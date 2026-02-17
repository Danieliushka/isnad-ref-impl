"""Tests for KeyRotation — credential rotation with chain-of-custody."""

import json
import pytest

from isnad.core import AgentIdentity, KeyRotation


class TestKeyRotation:
    """Basic rotation lifecycle."""

    def test_create_and_verify(self):
        old = AgentIdentity()
        new_id, rotation = old.rotate()
        assert rotation.verify()
        assert rotation.old_pubkey == old.public_key_hex
        assert rotation.new_pubkey == new_id.public_key_hex

    def test_different_agent_ids(self):
        old = AgentIdentity()
        new_id, rotation = old.rotate()
        # New key → new agent_id
        assert rotation.old_agent_id != rotation.new_agent_id
        assert rotation.old_agent_id == old.agent_id
        assert rotation.new_agent_id == new_id.agent_id

    def test_tampered_signature_fails(self):
        old = AgentIdentity()
        _, rotation = old.rotate()
        rotation.signature = "00" * 64
        assert not rotation.verify()

    def test_tampered_new_pubkey_fails(self):
        old = AgentIdentity()
        _, rotation = old.rotate()
        # Swap in a random key
        rotation.new_pubkey = AgentIdentity().public_key_hex
        assert not rotation.verify()

    def test_serialisation_roundtrip(self):
        old = AgentIdentity()
        _, rotation = old.rotate()
        d = rotation.to_dict()
        assert d["type"] == "key_rotation"
        restored = KeyRotation.from_dict(d)
        assert restored.verify()
        assert restored.old_pubkey == rotation.old_pubkey
        assert restored.new_pubkey == rotation.new_pubkey

    def test_json_roundtrip(self):
        old = AgentIdentity()
        _, rotation = old.rotate()
        blob = json.dumps(rotation.to_dict())
        restored = KeyRotation.from_dict(json.loads(blob))
        assert restored.verify()

    def test_chain_rotation(self):
        """Rotate twice: A → B → C. Both rotations valid."""
        a = AgentIdentity()
        b, rot_ab = a.rotate()
        c, rot_bc = b.rotate()
        assert rot_ab.verify()
        assert rot_bc.verify()
        # Chain: A's key → B's key → C's key
        assert rot_ab.new_pubkey == rot_bc.old_pubkey

    def test_rotation_has_timestamp(self):
        old = AgentIdentity()
        _, rotation = old.rotate()
        assert rotation.timestamp  # non-empty
        assert "T" in rotation.timestamp  # ISO format

    def test_new_identity_can_sign(self):
        """After rotation, new identity works for attestations."""
        old = AgentIdentity()
        new_id, _ = old.rotate()
        # New key can sign arbitrary data
        sig = new_id.sign(b"hello")
        assert len(sig) == 64
