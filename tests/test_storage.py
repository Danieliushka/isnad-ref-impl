"""Tests for isnad.storage — pluggable persistence backends."""

import json
import os
import tempfile
import threading

import pytest

from isnad.core import (
    AgentIdentity,
    Attestation,
    Delegation,
    RevocationEntry,
    TrustChain,
    RevocationRegistry,
    DelegationRegistry,
)
from isnad.storage import (
    MemoryBackend,
    SQLiteBackend,
    FileBackend,
    PersistentTrustChain,
    PersistentRevocationRegistry,
    PersistentDelegationRegistry,
    StorageBackend,
)


@pytest.fixture
def alice():
    return AgentIdentity()

@pytest.fixture
def bob():
    return AgentIdentity()


def signed_att(witness_identity, subject_id, task="test", evidence=""):
    att = Attestation(subject=subject_id, witness=witness_identity.agent_id,
                      task=task, evidence=evidence)
    att.sign(witness_identity)
    return att


def signed_deleg(principal_identity, delegate_id, scopes=None, **kw):
    d = Delegation(principal=principal_identity.agent_id, delegate=delegate_id,
                   scopes=scopes or ["*"], **kw)
    d.sign(principal_identity)
    return d


@pytest.fixture
def attestation(alice, bob):
    return signed_att(alice, bob.agent_id, "reliability")

@pytest.fixture
def delegation(alice, bob):
    return signed_deleg(alice, bob.agent_id, ["attestation"], max_depth=2)


def make_backends():
    yield "memory", lambda: MemoryBackend()
    def sqlite_factory():
        return SQLiteBackend(tempfile.mktemp(suffix=".db"))
    yield "sqlite", sqlite_factory
    def file_factory():
        return FileBackend(tempfile.mkdtemp())
    yield "file", file_factory


@pytest.fixture(params=[f[0] for f in make_backends()],
                ids=[f[0] for f in make_backends()])
def backend(request):
    factories = dict(make_backends())
    b = factories[request.param]()
    yield b
    b.close()


# ─── Backend Interface Tests ──────────────────────────────────────

class TestBackendInterface:

    def test_store_and_load_attestation(self, backend, attestation):
        backend.store_attestation(attestation)
        loaded = backend.load_attestations()
        assert len(loaded) == 1
        assert loaded[0]["task"] == "reliability"

    def test_store_multiple_attestations(self, backend, alice, bob):
        for i in range(5):
            att = signed_att(alice, bob.agent_id, f"skill_{i}")
            backend.store_attestation(att)
        assert backend.count("attestations") == 5

    def test_store_and_load_revocation(self, backend, alice):
        entry = RevocationEntry(target_id="att_123", reason="compromised",
                                revoked_by=alice.agent_id)
        backend.store_revocation(entry)
        loaded = backend.load_revocations()
        assert len(loaded) == 1
        assert loaded[0]["target_id"] == "att_123"
        assert loaded[0]["reason"] == "compromised"

    def test_store_and_load_delegation(self, backend, delegation):
        backend.store_delegation(delegation)
        loaded = backend.load_delegations()
        assert len(loaded) == 1
        assert loaded[0]["scopes"] == ["attestation"]
        assert loaded[0]["max_depth"] == 2

    def test_count(self, backend, attestation, delegation):
        assert backend.count("attestations") == 0
        backend.store_attestation(attestation)
        assert backend.count("attestations") == 1
        backend.store_delegation(delegation)
        assert backend.count("delegations") == 1

    def test_count_unknown_collection(self, backend):
        assert backend.count("nonexistent") == 0

    def test_delete_by_agent(self, backend, alice, bob):
        att = signed_att(alice, bob.agent_id)
        backend.store_attestation(att)
        deleg = signed_deleg(alice, bob.agent_id)
        backend.store_delegation(deleg)
        count = backend.delete_by_agent(alice.agent_id)
        assert count >= 1
        assert backend.count("attestations") == 0

    def test_delete_preserves_unrelated(self, backend, alice, bob):
        charlie = AgentIdentity()
        att1 = signed_att(alice, bob.agent_id)
        att2 = signed_att(charlie, charlie.agent_id, "self")
        backend.store_attestation(att1)
        backend.store_attestation(att2)
        backend.delete_by_agent(alice.agent_id)
        remaining = backend.load_attestations()
        assert len(remaining) == 1
        assert remaining[0]["witness"] == charlie.agent_id

    def test_empty_load(self, backend):
        assert backend.load_attestations() == []
        assert backend.load_revocations() == []
        assert backend.load_delegations() == []

    def test_context_manager(self, backend):
        with backend as b:
            assert isinstance(b, StorageBackend)


# ─── SQLite-Specific Tests ─────────────────────────────────────────

class TestSQLiteBackend:

    @pytest.fixture
    def db(self):
        tmp = tempfile.mktemp(suffix=".db")
        backend = SQLiteBackend(tmp)
        yield backend
        backend.close()
        if os.path.exists(tmp):
            os.unlink(tmp)

    def test_persistence_across_instances(self, alice, bob):
        tmp = tempfile.mktemp(suffix=".db")
        try:
            b1 = SQLiteBackend(tmp)
            att = signed_att(alice, bob.agent_id, "persistent")
            b1.store_attestation(att)
            b1.close()

            b2 = SQLiteBackend(tmp)
            loaded = b2.load_attestations()
            assert len(loaded) == 1
            assert loaded[0]["task"] == "persistent"
            b2.close()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_query_attestations(self, db, alice, bob):
        for i in range(10):
            if i % 2 == 0:
                att = signed_att(alice, bob.agent_id, "skill")
            else:
                att = signed_att(bob, alice.agent_id, "skill")
            db.store_attestation(att)

        results = db.query_attestations(subject=bob.agent_id)
        assert all(r["subject"] == bob.agent_id for r in results)

        limited = db.query_attestations(limit=3)
        assert len(limited) == 3

    def test_query_by_witness(self, db, alice, bob):
        att = signed_att(alice, bob.agent_id)
        db.store_attestation(att)
        results = db.query_attestations(witness=alice.agent_id)
        assert len(results) == 1

    def test_thread_safety(self, db, alice, bob):
        errors = []
        def writer(n):
            try:
                for i in range(20):
                    att = signed_att(alice, bob.agent_id, f"thread_{n}_{i}")
                    db.store_attestation(att)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert db.count("attestations") == 80

    def test_wal_mode(self):
        tmp = tempfile.mktemp(suffix=".db")
        try:
            b = SQLiteBackend(tmp, wal_mode=True)
            conn = b._get_conn()
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            b.close()
        finally:
            for ext in ("", "-wal", "-shm"):
                p = tmp + ext
                if os.path.exists(p):
                    os.unlink(p)


# ─── File Backend Tests ────────────────────────────────────────────

class TestFileBackend:

    @pytest.fixture
    def fb(self):
        return FileBackend(tempfile.mkdtemp())

    def test_creates_directory(self):
        tmp = os.path.join(tempfile.mkdtemp(), "sub", "dir")
        FileBackend(tmp)
        assert os.path.isdir(tmp)

    def test_jsonl_format(self, fb, attestation):
        fb.store_attestation(attestation)
        path = fb._file("attestations")
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["task"] == "reliability"

    def test_persistence_across_instances(self, alice, bob):
        tmp = tempfile.mkdtemp()
        fb1 = FileBackend(tmp)
        att = signed_att(alice, bob.agent_id, "persistent")
        fb1.store_attestation(att)

        fb2 = FileBackend(tmp)
        loaded = fb2.load_attestations()
        assert len(loaded) == 1
        assert loaded[0]["task"] == "persistent"


# ─── Persistent Wrapper Tests ─────────────────────────────────────

class TestPersistentTrustChain:

    def test_add_persists(self, alice, bob):
        backend = MemoryBackend()
        chain = PersistentTrustChain(backend)
        att = signed_att(alice, bob.agent_id)
        chain.add(att)
        assert backend.count("attestations") == 1
        assert len(chain.attestations) == 1

    def test_hydrate_from_backend(self, alice, bob):
        backend = MemoryBackend()
        att = signed_att(alice, bob.agent_id, "preexisting")
        backend.store_attestation(att)
        chain = PersistentTrustChain(backend)
        assert len(chain.attestations) == 1
        assert chain.attestations[0].task == "preexisting"

    def test_sqlite_round_trip(self, alice, bob):
        tmp = tempfile.mktemp(suffix=".db")
        try:
            b1 = SQLiteBackend(tmp)
            c1 = PersistentTrustChain(b1)
            att = signed_att(alice, bob.agent_id, "durable")
            c1.add(att)
            b1.close()

            b2 = SQLiteBackend(tmp)
            c2 = PersistentTrustChain(b2)
            assert len(c2.attestations) == 1
            assert c2.attestations[0].task == "durable"
            b2.close()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_trust_score_with_persistence(self, alice, bob):
        backend = MemoryBackend()
        chain = PersistentTrustChain(backend)
        for i in range(3):
            att = signed_att(alice, bob.agent_id, f"task_{i}")
            chain.add(att)
        score = chain.trust_score(bob.agent_id)
        assert score > 0

    def test_revoked_not_added(self, alice, bob):
        backend = MemoryBackend()
        rev_reg = RevocationRegistry()
        chain = PersistentTrustChain(backend, revocation_registry=rev_reg)
        att = signed_att(alice, bob.agent_id)
        entry = RevocationEntry(target_id=att.attestation_id, reason="bad",
                                revoked_by=alice.agent_id)
        rev_reg.revoke(entry)
        result = chain.add(att)
        assert result is False
        assert backend.count("attestations") == 0


class TestPersistentRevocationRegistry:

    def test_revoke_persists(self, alice):
        backend = MemoryBackend()
        reg = PersistentRevocationRegistry(backend)
        entry = RevocationEntry(target_id="target_123", reason="test",
                                revoked_by=alice.agent_id)
        reg.revoke(entry)
        assert backend.count("revocations") == 1
        assert reg.is_revoked("target_123")

    def test_hydrate(self, alice):
        backend = MemoryBackend()
        entry = RevocationEntry(target_id="att_x", reason="old",
                                revoked_by=alice.agent_id)
        backend.store_revocation(entry)
        reg = PersistentRevocationRegistry(backend)
        assert reg.is_revoked("att_x")


class TestPersistentDelegationRegistry:

    def test_add_persists(self, alice, bob, delegation):
        backend = MemoryBackend()
        reg = PersistentDelegationRegistry(backend)
        reg.add(delegation)
        assert backend.count("delegations") == 1

    def test_hydrate(self, alice, bob):
        backend = MemoryBackend()
        deleg = signed_deleg(alice, bob.agent_id, ["test"])
        backend.store_delegation(deleg)
        reg = PersistentDelegationRegistry(backend)
        assert reg.get(deleg.delegation_id) is not None


# ─── Integration Tests ─────────────────────────────────────────────

class TestFullStack:

    def test_full_workflow_sqlite(self, alice, bob):
        tmp = tempfile.mktemp(suffix=".db")
        try:
            backend = SQLiteBackend(tmp)
            rev_reg = PersistentRevocationRegistry(backend)
            chain = PersistentTrustChain(backend, revocation_registry=rev_reg)
            deleg_reg = PersistentDelegationRegistry(backend, revocation_registry=rev_reg)

            for task in ["reliability", "speed", "accuracy"]:
                att = signed_att(alice, bob.agent_id, task)
                chain.add(att)

            deleg = signed_deleg(alice, bob.agent_id, ["attestation"], max_depth=1)
            deleg_reg.add(deleg)

            score = chain.trust_score(bob.agent_id)
            assert score > 0

            att_id = chain.attestations[0].attestation_id
            entry = RevocationEntry(target_id=att_id, reason="test revocation",
                                    revoked_by=alice.agent_id)
            rev_reg.revoke(entry)
            assert rev_reg.is_revoked(att_id)

            assert backend.count("attestations") == 3
            assert backend.count("revocations") == 1
            assert backend.count("delegations") == 1
            backend.close()

            # Reopen and verify persistence
            backend2 = SQLiteBackend(tmp)
            chain2 = PersistentTrustChain(backend2)
            assert len(chain2.attestations) == 3
            rev_reg2 = PersistentRevocationRegistry(backend2)
            assert rev_reg2.is_revoked(att_id)
            backend2.close()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_gdpr_deletion_flow(self, alice, bob):
        backend = MemoryBackend()
        chain = PersistentTrustChain(backend)
        att = signed_att(alice, bob.agent_id)
        chain.add(att)
        deleted = backend.delete_by_agent(alice.agent_id)
        assert deleted >= 1
        assert backend.count("attestations") == 0
