"""Tests for RevocationRegistry — enterprise credential revocation."""

import json
import os
import tempfile
import pytest

from isnad import AgentIdentity, Attestation, TrustChain, RevocationEntry, RevocationRegistry


@pytest.fixture
def alice():
    return AgentIdentity.generate("alice") if hasattr(AgentIdentity, 'generate') else AgentIdentity()


@pytest.fixture
def bob():
    return AgentIdentity.generate("bob") if hasattr(AgentIdentity, 'generate') else AgentIdentity()


@pytest.fixture
def registry():
    return RevocationRegistry()


class TestRevocationEntry:
    def test_create_and_sign(self, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="compromised credentials",
            revoked_by=alice.agent_id,
        )
        entry.sign(alice)
        assert entry.signature is not None
        assert entry.verify(alice.public_key_hex)

    def test_verify_wrong_key(self, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="compromised",
            revoked_by=alice.agent_id,
        )
        entry.sign(alice)
        assert not entry.verify(bob.public_key_hex)

    def test_unsigned_entry_fails_verify(self, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="test",
            revoked_by=alice.agent_id,
        )
        assert not entry.verify(alice.public_key_hex)

    def test_scoped_revocation(self, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="bad code reviews",
            revoked_by=alice.agent_id,
            scope="code-review",
        )
        entry.sign(alice)
        assert entry.scope == "code-review"
        assert entry.verify(alice.public_key_hex)

    def test_serialization(self, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="compromised",
            revoked_by=alice.agent_id,
            scope="deployment",
        )
        entry.sign(alice)
        d = entry.to_dict()
        restored = RevocationEntry.from_dict(d)
        assert restored.target_id == entry.target_id
        assert restored.reason == entry.reason
        assert restored.scope == entry.scope
        assert restored.signature == entry.signature


class TestRevocationRegistry:
    def test_revoke_agent(self, registry, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="compromised",
            revoked_by=alice.agent_id,
        )
        registry.revoke(entry)
        assert registry.is_revoked(bob.agent_id)
        assert not registry.is_revoked(alice.agent_id)

    def test_scoped_revocation(self, registry, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="bad reviews",
            revoked_by=alice.agent_id,
            scope="code-review",
        )
        registry.revoke(entry)
        assert registry.is_revoked(bob.agent_id, scope="code-review")
        assert not registry.is_revoked(bob.agent_id, scope="deployment")

    def test_global_revocation_covers_all_scopes(self, registry, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="fully compromised",
            revoked_by=alice.agent_id,
            scope=None,  # global
        )
        registry.revoke(entry)
        assert registry.is_revoked(bob.agent_id, scope="code-review")
        assert registry.is_revoked(bob.agent_id, scope="deployment")
        assert registry.is_revoked(bob.agent_id)

    def test_get_revocations(self, registry, alice, bob):
        e1 = RevocationEntry(target_id=bob.agent_id, reason="r1", revoked_by=alice.agent_id)
        e2 = RevocationEntry(target_id=bob.agent_id, reason="r2", revoked_by=alice.agent_id, scope="x")
        registry.revoke(e1)
        registry.revoke(e2)
        entries = registry.get_revocations(bob.agent_id)
        assert len(entries) == 2

    def test_save_load(self, registry, alice, bob):
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="test",
            revoked_by=alice.agent_id,
        )
        entry.sign(alice)
        registry.revoke(entry)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            registry.save(path)
            loaded = RevocationRegistry.load(path)
            assert loaded.is_revoked(bob.agent_id)
            assert len(loaded.all_entries) == 1
        finally:
            os.unlink(path)


class TestTrustChainWithRevocation:
    def test_revoked_agent_gets_zero_trust(self, alice, bob):
        registry = RevocationRegistry()
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="compromised",
            revoked_by=alice.agent_id,
        )
        registry.revoke(entry)

        chain = TrustChain(revocation_registry=registry)
        att = Attestation(
            subject=bob.agent_id,
            witness=alice.agent_id,
            task="code-review",
            evidence="https://example.com",
        ).sign(alice)
        chain.add(att)
        assert chain.trust_score(bob.agent_id) == 0.0

    def test_revoked_attestation_not_added(self, alice, bob):
        att = Attestation(
            subject=bob.agent_id,
            witness=alice.agent_id,
            task="code-review",
            evidence="https://example.com",
        ).sign(alice)
        registry = RevocationRegistry()
        entry = RevocationEntry(
            target_id=att.attestation_id,
            reason="fraudulent",
            revoked_by=alice.agent_id,
        )
        registry.revoke(entry)

        chain = TrustChain(revocation_registry=registry)
        assert not chain.add(att)
        assert chain.trust_score(bob.agent_id) == 0.0

    def test_scoped_revocation_only_affects_scope(self, alice, bob):
        registry = RevocationRegistry()
        entry = RevocationEntry(
            target_id=bob.agent_id,
            reason="bad at reviews",
            revoked_by=alice.agent_id,
            scope="code-review",
        )
        registry.revoke(entry)

        chain = TrustChain(revocation_registry=registry)
        att = Attestation(
            subject=bob.agent_id,
            witness=alice.agent_id,
            task="deployment",
            evidence="https://example.com",
        ).sign(alice)
        chain.add(att)
        # Revoked for code-review, not deployment
        assert chain.trust_score(bob.agent_id, scope="code-review") == 0.0
        assert chain.trust_score(bob.agent_id, scope="deployment") > 0.0

    def test_chain_without_revocation_works(self, alice, bob):
        """Backward compat: TrustChain without registry works as before."""
        chain = TrustChain()
        att = Attestation(
            subject=bob.agent_id,
            witness=alice.agent_id,
            task="code-review",
            evidence="https://example.com",
        ).sign(alice)
        chain.add(att)
        assert chain.trust_score(bob.agent_id) > 0.0
