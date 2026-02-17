"""Tests for isnad AuditTrail — tamper-evident logging."""

import json
import time
import pytest
from isnad.audit import AuditTrail, AuditEntry, AuditEventType


class TestAuditEntry:
    def test_compute_hash_deterministic(self):
        entry = AuditEntry(
            event_type="attestation.created",
            agent_id="agent-1",
            timestamp=1000.0,
            details={"task": "review"},
            prev_hash="genesis",
            sequence=0,
        )
        h1 = entry.compute_hash()
        h2 = entry.compute_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_hash_changes_with_content(self):
        e1 = AuditEntry("a.created", "agent-1", 1000.0, {}, prev_hash="genesis", sequence=0)
        e2 = AuditEntry("a.created", "agent-2", 1000.0, {}, prev_hash="genesis", sequence=0)
        assert e1.compute_hash() != e2.compute_hash()

    def test_roundtrip_dict(self):
        entry = AuditEntry("a.created", "agent-1", 1000.0, {"k": "v"}, "hash", "prev", 5)
        restored = AuditEntry.from_dict(entry.to_dict())
        assert restored.event_type == entry.event_type
        assert restored.agent_id == entry.agent_id
        assert restored.details == entry.details


class TestAuditTrail:
    def test_log_and_verify(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ATTESTATION_CREATED, "agent-1", {"task": "review"})
        trail.log(AuditEventType.ACCESS_GRANTED, "agent-1", {"resource": "/api"})
        trail.log(AuditEventType.ACCESS_DENIED, "agent-2", {"reason": "no attestation"})
        
        assert trail.size == 3
        ok, idx = trail.verify_integrity()
        assert ok is True
        assert idx is None

    def test_genesis_hash(self):
        trail = AuditTrail()
        entry = trail.log(AuditEventType.AGENT_REGISTERED, "agent-1")
        assert entry.prev_hash == "genesis"
        assert entry.sequence == 0

    def test_chain_linkage(self):
        trail = AuditTrail()
        e1 = trail.log(AuditEventType.ATTESTATION_CREATED, "a")
        e2 = trail.log(AuditEventType.ATTESTATION_VERIFIED, "a")
        assert e2.prev_hash == e1.entry_hash

    def test_tamper_detection(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ATTESTATION_CREATED, "agent-1")
        trail.log(AuditEventType.ACCESS_GRANTED, "agent-1")
        trail.log(AuditEventType.ACCESS_DENIED, "agent-2")
        
        # Tamper with middle entry
        trail._entries[1].details["resource"] = "/admin"
        
        ok, idx = trail.verify_integrity()
        assert ok is False
        assert idx == 1

    def test_tamper_breaks_chain(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ATTESTATION_CREATED, "a")
        trail.log(AuditEventType.ACCESS_GRANTED, "a")
        trail.log(AuditEventType.KEY_ROTATED, "a")
        
        # Tamper with first entry's hash (breaks chain at entry 1)
        trail._entries[0].entry_hash = "fake"
        
        ok, idx = trail.verify_integrity()
        assert ok is False

    def test_query_by_agent(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ACCESS_GRANTED, "agent-1")
        trail.log(AuditEventType.ACCESS_DENIED, "agent-2")
        trail.log(AuditEventType.KEY_ROTATED, "agent-1")
        
        results = trail.query(agent_id="agent-1")
        assert len(results) == 2
        assert all(e.agent_id == "agent-1" for e in results)

    def test_query_by_event_type(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ACCESS_GRANTED, "a")
        trail.log(AuditEventType.ACCESS_DENIED, "b")
        trail.log(AuditEventType.ACCESS_GRANTED, "c")
        
        results = trail.query(event_type=AuditEventType.ACCESS_GRANTED)
        assert len(results) == 2

    def test_query_limit(self):
        trail = AuditTrail()
        for i in range(10):
            trail.log(AuditEventType.ATTESTATION_CREATED, f"agent-{i}")
        
        results = trail.query(limit=3)
        assert len(results) == 3

    def test_export_import_roundtrip(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ATTESTATION_CREATED, "agent-1", {"task": "code_review"})
        trail.log(AuditEventType.ACCESS_GRANTED, "agent-1", {"resource": "/api/data"})
        trail.log(AuditEventType.KEY_ROTATED, "agent-1", {"new_key": "pk_..."})
        
        exported = trail.export_json()
        imported = AuditTrail.from_json(exported)
        
        assert imported.size == 3
        ok, _ = imported.verify_integrity()
        assert ok

    def test_import_tampered_fails(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ATTESTATION_CREATED, "agent-1")
        
        data = json.loads(trail.export_json())
        data[0]["details"]["injected"] = True  # tamper
        
        with pytest.raises(ValueError, match="corrupted"):
            AuditTrail.from_json(json.dumps(data))

    def test_summary(self):
        trail = AuditTrail()
        trail.log(AuditEventType.ACCESS_GRANTED, "agent-1")
        trail.log(AuditEventType.ACCESS_GRANTED, "agent-2")
        trail.log(AuditEventType.ACCESS_DENIED, "agent-3")
        
        s = trail.summary()
        assert s["total_entries"] == 3
        assert s["unique_agents"] == 3
        assert s["event_counts"]["access.granted"] == 2
        assert s["integrity_verified"] is True

    def test_all_event_types(self):
        """Ensure all event types can be logged."""
        trail = AuditTrail()
        for et in AuditEventType:
            trail.log(et, "agent-test", {"type": et.value})
        
        assert trail.size == len(AuditEventType)
        ok, _ = trail.verify_integrity()
        assert ok

    def test_empty_trail_integrity(self):
        trail = AuditTrail()
        ok, idx = trail.verify_integrity()
        assert ok is True

    def test_query_time_range(self):
        trail = AuditTrail()
        now = time.time()
        e1 = trail.log(AuditEventType.ACCESS_GRANTED, "a")
        e2 = trail.log(AuditEventType.ACCESS_DENIED, "b")
        
        results = trail.query(since=now - 1)
        assert len(results) == 2
        
        results = trail.query(since=now + 999)
        assert len(results) == 0
