"""Tests for isnad.compliance — GDPR & data protection compliance."""
import time
import pytest
from isnad.compliance import (
    ComplianceManager, ConsentManager, DataAnonymizer,
    RetentionEnforcer, RetentionPolicy, DataBasis, ErasureScope,
)


class TestConsentManager:
    def test_grant_and_check(self):
        cm = ConsentManager()
        cm.grant("agent-1", "trust_processing")
        assert cm.has_consent("agent-1", "trust_processing")

    def test_no_consent(self):
        cm = ConsentManager()
        assert not cm.has_consent("agent-1", "trust_processing")

    def test_revoke(self):
        cm = ConsentManager()
        cm.grant("agent-1", "trust_processing")
        count = cm.revoke("agent-1", "trust_processing")
        assert count == 1
        assert not cm.has_consent("agent-1", "trust_processing")

    def test_revoke_all(self):
        cm = ConsentManager()
        cm.grant("agent-1", "trust_processing")
        cm.grant("agent-1", "discovery")
        count = cm.revoke("agent-1")
        assert count == 2

    def test_expired_consent(self):
        cm = ConsentManager()
        r = cm.grant("agent-1", "trust_processing", expires_in=0.01)
        time.sleep(0.02)
        assert not cm.has_consent("agent-1", "trust_processing")

    def test_scope_check(self):
        cm = ConsentManager()
        cm.grant("agent-1", "trust_processing", scope=["attestation"])
        assert cm.has_consent("agent-1", "trust_processing", "attestation")
        assert not cm.has_consent("agent-1", "trust_processing", "discovery")

    def test_get_consents(self):
        cm = ConsentManager()
        cm.grant("agent-1", "p1")
        cm.grant("agent-1", "p2")
        cm.revoke("agent-1", "p1")
        valid = cm.get_consents("agent-1")
        assert len(valid) == 1
        assert valid[0].purpose == "p2"

    def test_cleanup_expired(self):
        cm = ConsentManager()
        cm.grant("agent-1", "p1", expires_in=0.01)
        cm.grant("agent-1", "p2")
        time.sleep(0.02)
        removed = cm.cleanup_expired()
        assert removed == 1
        assert len(cm.get_consents("agent-1")) == 1

    def test_multiple_bases(self):
        cm = ConsentManager()
        cm.grant("agent-1", "trust", DataBasis.CONTRACT)
        cm.grant("agent-2", "trust", DataBasis.LEGITIMATE_INTEREST)
        assert cm.has_consent("agent-1", "trust")
        assert cm.has_consent("agent-2", "trust")


class TestDataAnonymizer:
    def test_pseudonymize_consistent(self):
        da = DataAnonymizer(salt="test")
        p1 = da.pseudonymize("agent-1")
        p2 = da.pseudonymize("agent-1")
        assert p1 == p2
        assert p1.startswith("anon-")

    def test_pseudonymize_different(self):
        da = DataAnonymizer(salt="test")
        p1 = da.pseudonymize("agent-1")
        p2 = da.pseudonymize("agent-2")
        assert p1 != p2

    def test_anonymize_attestation(self):
        da = DataAnonymizer(salt="test")
        att = {"signer": "alice", "subject": "bob", "claim": "trusted"}
        anon = da.anonymize_attestation(att)
        assert anon["signer"] != "alice"
        assert anon["subject"] != "bob"
        assert anon["claim"] == "trusted"  # Non-identity field preserved

    def test_anonymize_chain(self):
        da = DataAnonymizer(salt="test")
        chain = [
            {"signer": "alice", "subject": "bob"},
            {"signer": "bob", "subject": "carol"},
        ]
        anon = da.anonymize_chain(chain)
        assert len(anon) == 2
        # bob pseudonym consistent across chain
        assert anon[0]["subject"] == anon[1]["signer"]

    def test_original_unchanged(self):
        da = DataAnonymizer(salt="test")
        att = {"signer": "alice", "subject": "bob"}
        da.anonymize_attestation(att)
        assert att["signer"] == "alice"  # Original not mutated


class TestRetentionEnforcer:
    def test_no_policy_no_expiry(self):
        re = RetentionEnforcer()
        re.register_data("item-1", time.time() - 999999)
        assert re.get_expired() == []

    def test_expired_detection(self):
        re = RetentionEnforcer()
        re.add_policy(RetentionPolicy("short", max_age_seconds=0.01))
        re.register_data("item-1", time.time() - 1)
        expired = re.get_expired()
        assert "item-1" in expired

    def test_not_expired(self):
        re = RetentionEnforcer()
        re.add_policy(RetentionPolicy("long", max_age_seconds=9999))
        re.register_data("item-1")
        assert re.get_expired() == []

    def test_enforce_delete(self):
        re = RetentionEnforcer()
        re.add_policy(RetentionPolicy("short", max_age_seconds=0.01))
        re.register_data("item-1", time.time() - 1)
        deleted, anonymized = re.enforce()
        assert "item-1" in deleted
        assert anonymized == []

    def test_enforce_anonymize(self):
        re = RetentionEnforcer()
        re.add_policy(RetentionPolicy("short", max_age_seconds=0.01, auto_anonymize=True))
        re.register_data("item-1", time.time() - 1)
        deleted, anonymized = re.enforce()
        assert deleted == []
        assert "item-1" in anonymized

    def test_strictest_policy_wins(self):
        re = RetentionEnforcer()
        re.add_policy(RetentionPolicy("long", max_age_seconds=9999))
        re.add_policy(RetentionPolicy("short", max_age_seconds=0.01))
        re.register_data("item-1", time.time() - 1)
        expired = re.get_expired()
        assert "item-1" in expired


class TestComplianceManager:
    def test_grant_and_store(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        stored = cm.store_attestation("agent-1", {"id": "att-1", "signer": "agent-1", "claim": "ok"})
        assert stored

    def test_store_rejected_without_consent(self):
        cm = ComplianceManager()
        stored = cm.store_attestation("agent-1", {"id": "att-1"})
        assert not stored

    def test_erasure_full(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.store_attestation("agent-1", {"id": "att-1"})
        cm.store_attestation("agent-1", {"id": "att-2"})
        req = cm.request_erasure("agent-1", ErasureScope.FULL)
        assert req.items_erased == 2
        assert req.completed_at is not None
        assert "agent-1" not in cm._trust_data

    def test_erasure_attestations_only(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.store_attestation("agent-1", {"id": "att-1"})
        req = cm.request_erasure("agent-1", ErasureScope.ATTESTATIONS_ONLY)
        assert req.items_erased == 1
        # Consent still exists (not revoked)
        assert len(cm.consent.get_all_consents("agent-1")) > 0

    def test_erasure_deidentify(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.store_attestation("agent-1", {"signer": "agent-1", "claim": "ok"})
        req = cm.request_erasure("agent-1", ErasureScope.DEIDENTIFY)
        assert req.items_anonymized == 1
        assert "agent-1" not in cm._trust_data
        # Data moved to pseudonym key
        pseudo = cm.anonymizer.pseudonymize("agent-1")
        assert pseudo in cm._trust_data

    def test_data_portability(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.store_attestation("agent-1", {"id": "att-1"})
        export = cm.export_agent_data("agent-1")
        assert export["agent_id"] == "agent-1"
        assert len(export["attestations"]) == 1
        assert len(export["consents"]) == 1

    def test_audit_trail(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.store_attestation("agent-1", {"id": "att-1"})
        trail = cm.get_audit_trail("agent-1")
        types = [e.event_type for e in trail]
        assert "consent_granted" in types
        assert "attestation_stored" in types

    def test_audit_trail_filtering(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.grant_consent("agent-2", "trust_processing")
        trail = cm.get_audit_trail(agent_id="agent-1")
        assert all(e.agent_id == "agent-1" for e in trail)

    def test_compliance_summary(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.store_attestation("agent-1", {"id": "att-1"})
        summary = cm.compliance_summary()
        assert summary["agents_tracked"] == 1
        assert summary["attestations_stored"] == 1

    def test_enforce_retention(self):
        cm = ComplianceManager()
        result = cm.enforce_retention()
        assert "data_deleted" in result
        assert "consents_expired" in result

    def test_revoke_consent_audit(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.revoke_consent("agent-1")
        trail = cm.get_audit_trail(event_type="consent_revoked")
        assert len(trail) == 1

    def test_erasure_request_tracking(self):
        cm = ComplianceManager()
        cm.grant_consent("agent-1", "trust_processing")
        cm.request_erasure("agent-1")
        requests = cm.get_erasure_requests("agent-1")
        assert len(requests) == 1
        assert requests[0].completed_at is not None

    def test_full_lifecycle(self):
        """Consent → store → use → erasure → verify clean."""
        cm = ComplianceManager()
        # 1. Consent
        cm.grant_consent("agent-1", "trust_processing", basis=DataBasis.CONSENT)
        assert cm.check_consent("agent-1", "trust_processing")
        # 2. Store data
        assert cm.store_attestation("agent-1", {"signer": "agent-1", "claim": "reliable"})
        # 3. Export (portability)
        export = cm.export_agent_data("agent-1")
        assert len(export["attestations"]) == 1
        # 4. Erasure
        req = cm.request_erasure("agent-1", ErasureScope.FULL, reason="user request")
        assert req.items_erased == 1
        # 5. Verify clean
        assert "agent-1" not in cm._trust_data
        assert not cm.check_consent("agent-1", "trust_processing")
        # 6. Audit trail complete
        trail = cm.get_audit_trail("agent-1")
        assert len(trail) >= 4  # grant, store, erasure_requested, erasure_completed
