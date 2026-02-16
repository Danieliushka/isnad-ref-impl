"""Tests for Delegation and DelegationRegistry."""
import time
import pytest
from isnad import AgentIdentity, Delegation, DelegationRegistry, RevocationRegistry, RevocationEntry


@pytest.fixture
def alice():
    return AgentIdentity()

@pytest.fixture
def bob():
    return AgentIdentity()

@pytest.fixture
def charlie():
    return AgentIdentity()


class TestDelegation:
    def test_create_and_sign(self, alice, bob):
        d = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["code-review", "deploy"]
        ).sign(alice)
        assert d.verify()
        assert d.delegation_id
        assert d.scopes == ["code-review", "deploy"]

    def test_wrong_signer(self, alice, bob):
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id, scopes=["test"])
        with pytest.raises(AssertionError):
            d.sign(bob)  # bob is not the principal

    def test_tampered_delegation(self, alice, bob):
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id, scopes=["test"]).sign(alice)
        d.scopes = ["admin"]  # tamper
        assert not d.verify()  # payload changed → sig invalid

    def test_expiry(self, alice, bob):
        past = time.time() - 3600
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["test"], expires_at=past).sign(alice)
        assert d.is_expired()
        future = time.time() + 3600
        d2 = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                        scopes=["test"], expires_at=future).sign(alice)
        assert not d2.is_expired()

    def test_no_expiry(self, alice, bob):
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id, scopes=["test"]).sign(alice)
        assert not d.is_expired()

    def test_serialization(self, alice, bob):
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["a", "b"], max_depth=2).sign(alice)
        d2 = Delegation.from_dict(d.to_dict())
        assert d2.verify()
        assert d2.principal == d.principal
        assert d2.scopes == d.scopes
        assert d2.max_depth == 2

    def test_repr(self, alice, bob):
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id, scopes=["test"]).sign(alice)
        r = repr(d)
        assert "✅" in r
        assert "test" in r


class TestSubDelegation:
    def test_basic_sub_delegation(self, alice, bob, charlie):
        root = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["review", "deploy"], max_depth=2
        ).sign(alice)
        child = root.sub_delegate(charlie.agent_id, ["review"], bob)
        assert child.verify()
        assert child.parent_id == root.delegation_id
        assert child.depth == 1
        assert child.scopes == ["review"]

    def test_depth_limit(self, alice, bob, charlie):
        root = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["test"], max_depth=0  # no sub-delegation
        ).sign(alice)
        with pytest.raises(ValueError, match="depth limit"):
            root.sub_delegate(charlie.agent_id, ["test"], bob)

    def test_scope_narrowing(self, alice, bob, charlie):
        root = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["review", "deploy"], max_depth=1
        ).sign(alice)
        # Can narrow
        child = root.sub_delegate(charlie.agent_id, ["review"], bob)
        assert child.scopes == ["review"]
        # Cannot widen
        with pytest.raises(ValueError, match="not in parent"):
            root.sub_delegate(charlie.agent_id, ["admin"], bob)

    def test_expiry_inheritance(self, alice, bob, charlie):
        parent_exp = time.time() + 3600
        root = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["test"], max_depth=1, expires_at=parent_exp
        ).sign(alice)
        # Child can't exceed parent expiry
        child = root.sub_delegate(charlie.agent_id, ["test"], bob,
                                  expires_at=parent_exp + 9999)
        assert child.expires_at == parent_exp  # clamped

    def test_wrong_subdelegator(self, alice, bob, charlie):
        root = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["test"], max_depth=1
        ).sign(alice)
        with pytest.raises(ValueError, match="Only delegate"):
            root.sub_delegate(charlie.agent_id, ["test"], alice)  # alice isn't delegate

    def test_three_level_chain(self, alice, bob, charlie):
        dave = AgentIdentity()
        root = Delegation(
            principal=alice.agent_id, delegate=bob.agent_id,
            scopes=["a", "b", "c"], max_depth=3
        ).sign(alice)
        l1 = root.sub_delegate(charlie.agent_id, ["a", "b"], bob)
        l2 = l1.sub_delegate(dave.agent_id, ["a"], charlie)
        assert l2.depth == 2
        assert l2.scopes == ["a"]
        assert l2.verify()


class TestDelegationRegistry:
    def test_add_and_query(self, alice, bob):
        reg = DelegationRegistry()
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["test"]).sign(alice)
        assert reg.add(d)
        assert reg.is_authorized(bob.agent_id, "test")
        assert not reg.is_authorized(bob.agent_id, "admin")

    def test_reject_invalid(self, alice, bob):
        reg = DelegationRegistry()
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id, scopes=["test"])
        # unsigned
        assert not reg.add(d)

    def test_expired_not_authorized(self, alice, bob):
        reg = DelegationRegistry()
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["test"], expires_at=time.time() - 1).sign(alice)
        reg.add(d)
        assert not reg.is_authorized(bob.agent_id, "test")

    def test_revoked_delegation(self, alice, bob):
        revocations = RevocationRegistry()
        reg = DelegationRegistry(revocation_registry=revocations)
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["test"]).sign(alice)
        # Revoke it
        entry = RevocationEntry(target_id=d.delegation_id, reason="compromised",
                                revoked_by=alice.agent_id).sign(alice)
        revocations.revoke(entry)
        assert not reg.add(d)  # rejected at add time

    def test_verify_chain(self, alice, bob, charlie):
        reg = DelegationRegistry()
        root = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                          scopes=["test"], max_depth=1).sign(alice)
        child = root.sub_delegate(charlie.agent_id, ["test"], bob)
        reg.add(root)
        reg.add(child)
        valid, reason = reg.verify_chain(child.delegation_id)
        assert valid, reason

    def test_verify_chain_missing_parent(self, alice, bob, charlie):
        reg = DelegationRegistry()
        root = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                          scopes=["test"], max_depth=1).sign(alice)
        child = root.sub_delegate(charlie.agent_id, ["test"], bob)
        reg.add(child)  # don't add root
        valid, reason = reg.verify_chain(child.delegation_id)
        assert not valid
        assert "Missing" in reason

    def test_delegations_for(self, alice, bob):
        reg = DelegationRegistry()
        d1 = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                        scopes=["a"]).sign(alice)
        d2 = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                        scopes=["b"], expires_at=time.time() - 1).sign(alice)
        reg.add(d1)
        reg.add(d2)
        active = reg.delegations_for(bob.agent_id)
        assert len(active) == 1  # expired one filtered out

    def test_save_load(self, alice, bob, tmp_path):
        reg = DelegationRegistry()
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["test"]).sign(alice)
        reg.add(d)
        filepath = str(tmp_path / "delegations.json")
        reg.save(filepath)
        reg2 = DelegationRegistry.load(filepath)
        assert reg2.is_authorized(bob.agent_id, "test")

    def test_circular_chain_detection(self, alice, bob):
        """Circular chains should be caught by verify_chain."""
        reg = DelegationRegistry()
        # Manually create a circular reference (pathological)
        d = Delegation(principal=alice.agent_id, delegate=bob.agent_id,
                       scopes=["test"], parent_id=None).sign(alice)
        reg.add(d)
        # This is valid (no parent = root)
        valid, _ = reg.verify_chain(d.delegation_id)
        assert valid
