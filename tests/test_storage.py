"""Tests for isnad.storage — pluggable persistence backends."""

import os
import tempfile
import threading

import pytest

from isnad.core import AgentIdentity, Attestation, RevocationEntry, RevocationRegistry, TrustChain
from isnad.storage import (
    FileBackend,
    MemoryBackend,
    PersistentRevocationRegistry,
    PersistentTrustChain,
    SQLiteBackend,
    StorageBackend,
)


# ─── Helpers ───────────────────────────────────────────────────────

def make_attestation(witness_id: AgentIdentity, subject_id: AgentIdentity, task: str = "code-review"):
    att = Attestation(
        subject=subject_id.agent_id,
        witness=witness_id.agent_id,
        task=task,
        evidence="https://example.com",
    )
    att.sign(witness_id)
    return att


@pytest.fixture
def alice():
    return AgentIdentity()

@pytest.fixture
def bob():
    return AgentIdentity()

@pytest.fixture
def memory():
    return MemoryBackend()

@pytest.fixture
def sqlite_backend(tmp_path):
    db = SQLiteBackend(str(tmp_path / "test.db"))
    yield db
    db.close()

@pytest.fixture
def file_backend(tmp_path):
    return FileBackend(str(tmp_path / "data"), namespace="test")


# ─── StorageBackend interface (parametrized) ───────────────────────

ALL_BACKENDS = ["memory", "sqlite_backend", "file_backend"]


@pytest.fixture
def backend(request):
    return request.getfixturevalue(request.param)


@pytest.mark.parametrize("backend", ALL_BACKENDS, indirect=True)
class TestBackendInterface:
    """Test the common interface across all backends."""

    def test_save_load(self, backend):
        backend.save("k1", {"a": 1})
        assert backend.load("k1") == {"a": 1}

    def test_load_missing(self, backend):
        assert backend.load("nonexistent") is None

    def test_exists(self, backend):
        assert not backend.exists("k1")
        backend.save("k1", {"a": 1})
        assert backend.exists("k1")

    def test_delete(self, backend):
        backend.save("k1", {"a": 1})
        assert backend.delete("k1")
        assert not backend.exists("k1")

    def test_delete_missing(self, backend):
        assert not backend.delete("nope")

    def test_list_keys(self, backend):
        backend.save("att:1", {"x": 1})
        backend.save("att:2", {"x": 2})
        backend.save("rev:1", {"x": 3})
        assert sorted(backend.list_keys("att:")) == ["att:1", "att:2"]
        assert backend.list_keys("rev:") == ["rev:1"]
        assert len(backend.list_keys()) == 3

    def test_save_many(self, backend):
        backend.save_many({"a": {"v": 1}, "b": {"v": 2}})
        assert backend.load("a") == {"v": 1}
        assert backend.load("b") == {"v": 2}

    def test_load_many(self, backend):
        backend.save("x", {"v": 1})
        result = backend.load_many(["x", "missing"])
        assert result["x"] == {"v": 1}
        assert result["missing"] is None

    def test_delete_many(self, backend):
        backend.save("a", {"v": 1})
        backend.save("b", {"v": 2})
        assert backend.delete_many(["a", "b", "c"]) == 2
        assert not backend.exists("a")

    def test_overwrite(self, backend):
        backend.save("k", {"v": 1})
        backend.save("k", {"v": 2})
        assert backend.load("k") == {"v": 2}

    def test_delete_by_agent(self, backend, alice):
        backend.save("a1", {"subject": alice.agent_id, "task": "x"})
        backend.save("a2", {"subject": "other", "task": "y"})
        deleted = backend.delete_by_agent(alice.agent_id)
        assert deleted >= 1
        assert not backend.exists("a1")
        assert backend.exists("a2")


# ─── SQLite-specific ───────────────────────────────────────────────

class TestSQLiteSpecific:
    def test_query_by_agent(self, sqlite_backend, alice):
        sqlite_backend.save("a1", {"subject": alice.agent_id, "task": "review"})
        sqlite_backend.save("a2", {"subject": "other", "task": "build"})
        results = sqlite_backend.query_by_agent(alice.agent_id)
        assert len(results) == 1
        assert results[0]["task"] == "review"

    def test_thread_safety(self, sqlite_backend):
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    sqlite_backend.save(f"t{n}_{i}", {"v": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(sqlite_backend.list_keys()) == 80

    def test_wal_mode(self, sqlite_backend):
        row = sqlite_backend._conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_gdpr_deep_scan(self, sqlite_backend, alice, bob):
        # witness field also references agent
        sqlite_backend.save("a1", {"witness": alice.agent_id, "subject": bob.agent_id})
        deleted = sqlite_backend.delete_by_agent(alice.agent_id)
        assert deleted >= 1
        assert not sqlite_backend.exists("a1")


# ─── File-specific ─────────────────────────────────────────────────

class TestFileSpecific:
    def test_append_only(self, file_backend):
        file_backend.save("k1", {"v": 1})
        file_backend.save("k2", {"v": 2})
        # File should have 2 lines
        with open(file_backend._filepath) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_delete_appends_marker(self, file_backend):
        file_backend.save("k1", {"v": 1})
        file_backend.delete("k1")
        with open(file_backend._filepath) as f:
            lines = f.readlines()
        assert len(lines) == 2  # original + delete marker

    def test_thread_safety(self, file_backend):
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    file_backend.save(f"t{n}_{i}", {"v": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(file_backend.list_keys()) == 40


# ─── PersistentTrustChain ─────────────────────────────────────────

class TestPersistentTrustChain:
    def test_add_persists(self, memory, alice, bob):
        chain = PersistentTrustChain(memory)
        att = make_attestation(alice, bob)
        assert chain.add(att)
        key = f"attestation:{att.attestation_id}"
        assert memory.exists(key)

    def test_hydrate_on_init(self, memory, alice, bob):
        chain1 = PersistentTrustChain(memory)
        att = make_attestation(alice, bob)
        chain1.add(att)

        chain2 = PersistentTrustChain(memory)
        assert len(chain2.attestations) == 1
        assert chain2.attestations[0].attestation_id == att.attestation_id

    def test_trust_score(self, memory, alice, bob):
        chain = PersistentTrustChain(memory)
        att = make_attestation(alice, bob)
        chain.add(att)
        score = chain.trust_score(bob.agent_id)
        assert score > 0

    def test_invalid_attestation_rejected(self, memory, alice, bob):
        chain = PersistentTrustChain(memory)
        att = Attestation(subject=bob.agent_id, witness=alice.agent_id, task="x")
        # Not signed
        assert not chain.add(att)
        assert len(chain.attestations) == 0

    def test_with_revocations(self, memory, alice, bob):
        reg = RevocationRegistry()
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="compromised", revoked_by=alice.agent_id
        )
        reg.revoke(entry)
        chain = PersistentTrustChain(memory, revocation_registry=reg)
        assert chain.trust_score(bob.agent_id) == 0.0

    def test_with_sqlite(self, sqlite_backend, alice, bob):
        chain = PersistentTrustChain(sqlite_backend)
        att = make_attestation(alice, bob)
        chain.add(att)
        # Hydrate new instance
        chain2 = PersistentTrustChain(sqlite_backend)
        assert len(chain2.attestations) == 1

    def test_with_file_backend(self, file_backend, alice, bob):
        chain = PersistentTrustChain(file_backend)
        att = make_attestation(alice, bob)
        chain.add(att)
        chain2 = PersistentTrustChain(file_backend)
        assert len(chain2.attestations) == 1

    def test_chain_trust(self, memory, alice, bob):
        chain = PersistentTrustChain(memory)
        att = make_attestation(alice, bob)
        chain.add(att)
        assert chain.chain_trust(alice.agent_id, bob.agent_id) > 0

    def test_backend_property(self, memory):
        chain = PersistentTrustChain(memory)
        assert chain.backend is memory


# ─── PersistentRevocationRegistry ──────────────────────────────────

class TestPersistentRevocationRegistry:
    def test_revoke_persists(self, memory, alice, bob):
        reg = PersistentRevocationRegistry(memory)
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="bad", revoked_by=alice.agent_id
        )
        reg.revoke(entry)
        assert reg.is_revoked(bob.agent_id)
        assert len(memory.list_keys("revocation:")) == 1

    def test_hydrate_on_init(self, memory, alice, bob):
        reg1 = PersistentRevocationRegistry(memory)
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="bad", revoked_by=alice.agent_id
        )
        reg1.revoke(entry)

        reg2 = PersistentRevocationRegistry(memory)
        assert reg2.is_revoked(bob.agent_id)

    def test_not_revoked(self, memory, alice, bob):
        reg = PersistentRevocationRegistry(memory)
        assert not reg.is_revoked(bob.agent_id)

    def test_scoped_revocation(self, memory, alice, bob):
        reg = PersistentRevocationRegistry(memory)
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="bad", revoked_by=alice.agent_id, scope="finance"
        )
        reg.revoke(entry)
        assert reg.is_revoked(bob.agent_id, scope="finance")
        assert not reg.is_revoked(bob.agent_id, scope="code")

    def test_get_revocations(self, memory, alice, bob):
        reg = PersistentRevocationRegistry(memory)
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="bad", revoked_by=alice.agent_id
        )
        reg.revoke(entry)
        entries = reg.get_revocations(bob.agent_id)
        assert len(entries) == 1

    def test_all_entries(self, memory, alice, bob):
        reg = PersistentRevocationRegistry(memory)
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="bad", revoked_by=alice.agent_id
        )
        reg.revoke(entry)
        assert len(reg.all_entries) == 1

    def test_with_sqlite(self, sqlite_backend, alice, bob):
        reg = PersistentRevocationRegistry(sqlite_backend)
        entry = RevocationEntry(
            target_id=bob.agent_id, reason="bad", revoked_by=alice.agent_id
        )
        reg.revoke(entry)
        reg2 = PersistentRevocationRegistry(sqlite_backend)
        assert reg2.is_revoked(bob.agent_id)

    def test_backend_property(self, memory):
        reg = PersistentRevocationRegistry(memory)
        assert reg.backend is memory


# ─── GDPR Integration ─────────────────────────────────────────────

class TestGDPR:
    def test_memory_gdpr(self, memory, alice, bob):
        att = make_attestation(alice, bob)
        memory.save(f"att:{att.attestation_id}", att.to_dict())
        memory.save("other", {"subject": "someone_else"})
        deleted = memory.delete_by_agent(bob.agent_id)
        assert deleted == 1
        assert memory.exists("other")

    def test_sqlite_gdpr(self, sqlite_backend, alice, bob):
        att = make_attestation(alice, bob)
        sqlite_backend.save(f"att:{att.attestation_id}", att.to_dict())
        deleted = sqlite_backend.delete_by_agent(bob.agent_id)
        assert deleted >= 1

    def test_file_gdpr(self, file_backend, alice, bob):
        att = make_attestation(alice, bob)
        file_backend.save(f"att:{att.attestation_id}", att.to_dict())
        deleted = file_backend.delete_by_agent(bob.agent_id)
        assert deleted == 1
        assert not file_backend.exists(f"att:{att.attestation_id}")
