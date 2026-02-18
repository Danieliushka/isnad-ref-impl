"""Tests for isnad.revocation — RevocationList, RevocationCheck, RevocationReason."""

import json
import time
import pytest

from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.revocation import (
    RevocationReason, RevocationRecord, RevocationList, RevocationCheck,
)


@pytest.fixture
def alice():
    return AgentIdentity()

@pytest.fixture
def bob():
    return AgentIdentity()

@pytest.fixture
def charlie():
    return AgentIdentity()

@pytest.fixture
def rlist():
    return RevocationList()


# ─── RevocationReason ──────────────────────────────────────────────

class TestRevocationReason:
    def test_enum_values(self):
        assert RevocationReason.KEY_COMPROMISE.value == "key_compromise"
        assert RevocationReason.SUPERSEDED.value == "superseded"
        assert RevocationReason.CEASED_OPERATION.value == "ceased_operation"
        assert RevocationReason.PRIVILEGE_WITHDRAWN.value == "privilege_withdrawn"

    def test_enum_from_value(self):
        assert RevocationReason("key_compromise") is RevocationReason.KEY_COMPROMISE


# ─── RevocationRecord ─────────────────────────────────────────────

class TestRevocationRecord:
    def test_create(self):
        r = RevocationRecord("abc123", RevocationReason.KEY_COMPROMISE, revoked_by="admin")
        assert r.attestation_id == "abc123"
        assert r.reason == RevocationReason.KEY_COMPROMISE
        assert r.revoked_by == "admin"
        assert r.timestamp > 0

    def test_serialization_roundtrip(self):
        r = RevocationRecord("abc123", RevocationReason.SUPERSEDED, timestamp=1000.0, revoked_by="x")
        d = r.to_dict()
        r2 = RevocationRecord.from_dict(d)
        assert r2.attestation_id == r.attestation_id
        assert r2.reason == r.reason
        assert r2.timestamp == r.timestamp
        assert r2.revoked_by == r.revoked_by


# ─── RevocationList ───────────────────────────────────────────────

class TestRevocationList:
    def test_empty_list(self, rlist):
        assert rlist.count == 0
        assert len(rlist) == 0
        assert not rlist.is_revoked("anything")
        assert rlist.get("anything") is None
        assert rlist.revoked_ids == set()

    def test_add_revocation(self, rlist):
        rlist.revoke("att1", RevocationReason.KEY_COMPROMISE)
        assert rlist.is_revoked("att1")
        assert rlist.count == 1
        assert "att1" in rlist

    def test_remove_revocation(self, rlist):
        rlist.revoke("att1", RevocationReason.KEY_COMPROMISE)
        assert rlist.unrevoke("att1")
        assert not rlist.is_revoked("att1")
        assert rlist.count == 0

    def test_remove_nonexistent(self, rlist):
        assert not rlist.unrevoke("nope")

    def test_double_revoke_idempotent(self, rlist):
        r1 = rlist.revoke("att1", RevocationReason.KEY_COMPROMISE, timestamp=100.0)
        r2 = rlist.revoke("att1", RevocationReason.SUPERSEDED, timestamp=200.0)
        assert rlist.count == 1
        # Keeps first entry
        assert r1 is r2
        assert rlist.get("att1").reason == RevocationReason.KEY_COMPROMISE
        assert rlist.get("att1").timestamp == 100.0

    def test_multiple_revocations(self, rlist):
        rlist.revoke("a", RevocationReason.KEY_COMPROMISE)
        rlist.revoke("b", RevocationReason.SUPERSEDED)
        rlist.revoke("c", RevocationReason.CEASED_OPERATION)
        assert rlist.count == 3
        assert rlist.revoked_ids == {"a", "b", "c"}

    def test_json_roundtrip(self, rlist):
        rlist.revoke("a", RevocationReason.KEY_COMPROMISE, revoked_by="admin")
        rlist.revoke("b", RevocationReason.SUPERSEDED)
        j = rlist.to_json()
        rlist2 = RevocationList.from_json(j)
        assert rlist2.count == 2
        assert rlist2.is_revoked("a")
        assert rlist2.is_revoked("b")
        assert rlist2.get("a").reason == RevocationReason.KEY_COMPROMISE
        assert rlist2.get("a").revoked_by == "admin"

    def test_dict_roundtrip(self, rlist):
        rlist.revoke("x", RevocationReason.PRIVILEGE_WITHDRAWN)
        d = rlist.to_dict()
        rlist2 = RevocationList.from_dict(d)
        assert rlist2.is_revoked("x")
        assert rlist2.get("x").reason == RevocationReason.PRIVILEGE_WITHDRAWN

    def test_empty_json_roundtrip(self):
        rl = RevocationList()
        j = rl.to_json()
        rl2 = RevocationList.from_json(j)
        assert rl2.count == 0

    def test_repr(self, rlist):
        assert "0 entries" in repr(rlist)
        rlist.revoke("a", RevocationReason.KEY_COMPROMISE)
        assert "1 entries" in repr(rlist)

    def test_all_records(self, rlist):
        rlist.revoke("a", RevocationReason.KEY_COMPROMISE)
        rlist.revoke("b", RevocationReason.SUPERSEDED)
        records = rlist.all_records
        assert len(records) == 2
        ids = {r.attestation_id for r in records}
        assert ids == {"a", "b"}


# ─── RevocationCheck ──────────────────────────────────────────────

class TestRevocationCheck:
    def _make_chain(self, alice, bob, tasks=None):
        """Helper: build a chain with attestations from alice witnessing bob."""
        chain = TrustChain()
        tasks = tasks or ["code-review"]
        for task in tasks:
            att = Attestation(
                subject=bob.agent_id,
                witness=alice.agent_id,
                task=task,
                evidence="https://example.com",
            ).sign(alice)
            chain.add(att)
        return chain

    def test_check_clean_chain(self, alice, bob):
        chain = self._make_chain(alice, bob)
        rl = RevocationList()
        checker = RevocationCheck(rl)
        valid, revoked = checker.check_chain(chain)
        assert valid
        assert revoked == []

    def test_check_chain_with_revoked(self, alice, bob):
        chain = self._make_chain(alice, bob)
        att_id = chain.attestations[0].attestation_id
        rl = RevocationList()
        rl.revoke(att_id, RevocationReason.KEY_COMPROMISE)
        checker = RevocationCheck(rl)
        valid, revoked = checker.check_chain(chain)
        assert not valid
        assert att_id in revoked

    def test_check_single_attestation(self, alice, bob):
        att = Attestation(
            subject=bob.agent_id, witness=alice.agent_id,
            task="test", evidence="",
        ).sign(alice)
        rl = RevocationList()
        checker = RevocationCheck(rl)
        assert checker.check_attestation(att)
        rl.revoke(att.attestation_id, RevocationReason.SUPERSEDED)
        assert not checker.check_attestation(att)

    def test_trust_score_zero_when_revoked(self, alice, bob):
        chain = self._make_chain(alice, bob)
        att_id = chain.attestations[0].attestation_id
        rl = RevocationList()
        rl.revoke(att_id, RevocationReason.KEY_COMPROMISE)
        checker = RevocationCheck(rl)
        assert checker.trust_score(chain, bob.agent_id) == 0.0

    def test_trust_score_normal_when_not_revoked(self, alice, bob):
        chain = self._make_chain(alice, bob)
        rl = RevocationList()
        checker = RevocationCheck(rl)
        score = checker.trust_score(chain, bob.agent_id)
        assert score > 0.0

    def test_trust_score_unknown_agent(self, alice, bob):
        chain = self._make_chain(alice, bob)
        rl = RevocationList()
        checker = RevocationCheck(rl)
        assert checker.trust_score(chain, "agent:unknown") == 0.0

    def test_check_chain_partial_revocation(self, alice, bob):
        """Only one of two attestations revoked."""
        chain = self._make_chain(alice, bob, tasks=["task-a", "task-b"])
        att_id = chain.attestations[0].attestation_id
        rl = RevocationList()
        rl.revoke(att_id, RevocationReason.PRIVILEGE_WITHDRAWN)
        checker = RevocationCheck(rl)
        valid, revoked = checker.check_chain(chain)
        assert not valid
        assert len(revoked) == 1
