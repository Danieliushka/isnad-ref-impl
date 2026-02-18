"""Tests for isnad.trust_report module."""

import pytest
from datetime import datetime, timezone, timedelta

from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.trust_report import (
    generate_trust_report,
    _detect_warnings,
    LOW_TRUST_THRESHOLD,
    TAMPER_WARNING,
    EXPIRED_WARNING,
    LOW_TRUST_WARNING,
)


# ─── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def identities():
    """Create three agent identities."""
    alice = AgentIdentity()
    bob = AgentIdentity()
    carol = AgentIdentity()
    return alice, bob, carol


@pytest.fixture
def basic_chain(identities):
    """Chain with two valid attestations."""
    alice, bob, carol = identities
    chain = TrustChain()

    a1 = Attestation(
        subject=alice.agent_id,
        witness=bob.agent_id,
        task="Code review",
        evidence="https://example.com/pr/1",
    ).sign(bob)

    a2 = Attestation(
        subject=alice.agent_id,
        witness=carol.agent_id,
        task="Deployment",
        evidence="https://example.com/deploy/1",
    ).sign(carol)

    chain.add(a1)
    chain.add(a2)
    return chain, (alice, bob, carol), (a1, a2)


# ─── Report Generation ────────────────────────────────────────────

class TestGenerateTrustReport:
    def test_basic_report_structure(self, basic_chain):
        chain, (alice, bob, carol), _ = basic_chain
        report = generate_trust_report(chain, chain_name="Test Chain", description="A test")

        assert "# Trust Report: Test Chain" in report
        assert "**Total Attestations:** 2" in report
        assert "**Unique Subjects:** 1" in report
        assert "**Unique Witnesses:** 2" in report
        assert "**Description:** A test" in report
        assert "## Attestations" in report
        assert "## Overall Chain Score" in report
        assert "## Warnings" in report

    def test_empty_chain(self):
        chain = TrustChain()
        report = generate_trust_report(chain, chain_name="Empty")

        assert "**Total Attestations:** 0" in report
        assert "_No attestations in chain._" in report
        assert "_No subjects to score._" in report
        assert "✅ No warnings detected." in report

    def test_attestation_details_shown(self, basic_chain):
        chain, (alice, bob, carol), (a1, a2) = basic_chain
        report = generate_trust_report(chain)

        assert "Code review" in report
        assert "Deployment" in report
        assert alice.agent_id in report
        assert bob.agent_id in report
        assert carol.agent_id in report
        assert "✅ Valid" in report

    def test_overall_score_table(self, basic_chain):
        chain, (alice, _, _), _ = basic_chain
        report = generate_trust_report(chain)

        assert "**Average Trust Score:**" in report
        assert alice.agent_id in report
        # Two unique witnesses → score = 0.2 + 0.2 = 0.4
        assert "0.40" in report

    def test_no_warnings_for_valid_chain(self, basic_chain):
        chain, _, _ = basic_chain
        report = generate_trust_report(chain)
        assert "✅ No warnings detected." in report

    def test_report_with_custom_now(self, basic_chain):
        chain, _, _ = basic_chain
        custom_now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        report = generate_trust_report(chain, now=custom_now)
        assert "2030-01-01" in report


# ─── Warning Detection ────────────────────────────────────────────

class TestWarnings:
    def test_tamper_detected(self, identities):
        alice, bob, _ = identities
        att = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="Tampered task",
        ).sign(bob)
        # Tamper with the task
        att.task = "Modified task"

        chain = TrustChain()
        # Can't add tampered attestation via chain.add, so test warning detection directly
        warnings = _detect_warnings(att, chain)
        types = [w["type"] for w in warnings]
        assert TAMPER_WARNING in types

    def test_expired_attestation(self, identities):
        alice, bob, _ = identities
        old_time = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        att = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="Old task",
            timestamp=old_time,
        ).sign(bob)

        chain = TrustChain()
        chain.add(att)
        warnings = _detect_warnings(att, chain, expiry_seconds=86400 * 365)
        types = [w["type"] for w in warnings]
        assert EXPIRED_WARNING in types

    def test_low_trust_warning(self, identities):
        alice, bob, _ = identities
        chain = TrustChain()
        # One attestation → score 0.2 < 0.3 threshold
        att = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="Single task",
        ).sign(bob)
        chain.add(att)

        warnings = _detect_warnings(att, chain)
        types = [w["type"] for w in warnings]
        assert LOW_TRUST_WARNING in types

    def test_no_warnings_for_healthy(self, identities):
        alice, bob, carol = identities
        chain = TrustChain()
        # Add enough attestations from different witnesses to exceed threshold
        for identity in [bob, carol]:
            att = Attestation(
                subject=alice.agent_id,
                witness=identity.agent_id,
                task="Good work",
            ).sign(identity)
            chain.add(att)

        # Score = 0.4 > 0.3, not expired, valid sig
        att = chain.attestations[0]
        warnings = _detect_warnings(att, chain)
        assert len(warnings) == 0

    def test_expired_warning_in_report(self, identities):
        alice, bob, carol = identities
        old_time = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        chain = TrustChain()

        att1 = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="Ancient task",
            timestamp=old_time,
        ).sign(bob)
        att2 = Attestation(
            subject=alice.agent_id,
            witness=carol.agent_id,
            task="Recent task",
        ).sign(carol)
        chain.add(att1)
        chain.add(att2)

        report = generate_trust_report(chain, expiry_seconds=86400 * 365)
        assert "expired" in report
        assert "**Total Warnings:**" in report

    def test_tamper_warning_in_report(self, identities):
        """Tampered attestations can't be added to chain, but we can build a report
        from a chain that has them injected directly."""
        alice, bob, carol = identities
        chain = TrustChain()

        good = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="Good task",
        ).sign(bob)
        chain.add(good)

        # Inject tampered attestation directly
        tampered = Attestation(
            subject=alice.agent_id,
            witness=carol.agent_id,
            task="Bad task",
        ).sign(carol)
        tampered.task = "Altered"
        chain.attestations.append(tampered)

        report = generate_trust_report(chain)
        assert "tamper_detected" in report
        assert "❌ Invalid" in report


# ─── Edge Cases ────────────────────────────────────────────────────

class TestEdgeCases:
    def test_multiple_subjects(self, identities):
        alice, bob, carol = identities
        chain = TrustChain()

        a1 = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="Task A",
        ).sign(bob)
        a2 = Attestation(
            subject=bob.agent_id,
            witness=carol.agent_id,
            task="Task B",
        ).sign(carol)
        chain.add(a1)
        chain.add(a2)

        report = generate_trust_report(chain)
        assert "**Unique Subjects:** 2" in report
        assert alice.agent_id in report
        assert bob.agent_id in report

    def test_no_evidence(self, identities):
        alice, bob, _ = identities
        chain = TrustChain()
        att = Attestation(
            subject=alice.agent_id,
            witness=bob.agent_id,
            task="No evidence task",
        ).sign(bob)
        chain.add(att)

        report = generate_trust_report(chain)
        # Evidence row should not appear
        assert "**Evidence**" not in report

    def test_report_returns_string(self, basic_chain):
        chain, _, _ = basic_chain
        report = generate_trust_report(chain)
        assert isinstance(report, str)
        assert len(report) > 100
