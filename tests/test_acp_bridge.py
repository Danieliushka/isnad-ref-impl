"""Tests for isnad.acp_bridge — Virtuals ACP trust bridge."""

import time
import pytest
from isnad.acp_bridge import (
    ACPAgentProfile,
    ACPTrustSignal,
    ACPTrustReport,
    ACPRiskLevel,
    ACPJobVerifier,
    analyze_job_history,
    analyze_offering_quality,
    analyze_wallet_activity,
    analyze_recency,
    generate_trust_report,
)
import json
from isnad.core import AgentIdentity


# ── ACPAgentProfile ──────────────────────────────────────────────

class TestACPAgentProfile:
    def test_empty_profile(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="TestBot")
        assert p.completion_rate == 0.0
        assert p.wallet_hash  # non-empty
        assert len(p.wallet_hash) == 16

    def test_completion_rate(self):
        p = ACPAgentProfile(
            wallet_address="0xabc",
            agent_name="TestBot",
            completed_jobs=8,
            failed_jobs=2,
        )
        assert p.completion_rate == 0.8

    def test_completion_rate_all_failed(self):
        p = ACPAgentProfile(
            wallet_address="0xabc",
            agent_name="TestBot",
            completed_jobs=0,
            failed_jobs=5,
        )
        assert p.completion_rate == 0.0

    def test_wallet_hash_deterministic(self):
        p1 = ACPAgentProfile(wallet_address="0xABC", agent_name="A")
        p2 = ACPAgentProfile(wallet_address="0xabc", agent_name="B")
        assert p1.wallet_hash == p2.wallet_hash  # case-insensitive

    def test_to_dict(self):
        p = ACPAgentProfile(
            wallet_address="0xabc",
            agent_name="TestBot",
            completed_jobs=10,
            failed_jobs=0,
        )
        d = p.to_dict()
        assert d["completion_rate"] == 1.0
        assert "wallet_hash" in d


# ── ACPTrustSignal ───────────────────────────────────────────────

class TestACPTrustSignal:
    def test_weighted_value(self):
        s = ACPTrustSignal(
            signal_type="test",
            value=0.8,
            confidence=0.5,
            evidence="test",
        )
        assert s.weighted_value() == 0.4

    def test_zero_confidence(self):
        s = ACPTrustSignal(
            signal_type="test",
            value=1.0,
            confidence=0.0,
            evidence="test",
        )
        assert s.weighted_value() == 0.0


# ── ACPTrustReport ───────────────────────────────────────────────

class TestACPTrustReport:
    def test_compute_score_no_signals(self):
        profile = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        report = ACPTrustReport(agent_profile=profile, signals=[])
        assert report.compute_score() == 0.0
        assert report.risk_level == ACPRiskLevel.UNKNOWN

    def test_compute_score_single_signal(self):
        profile = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        signal = ACPTrustSignal("test", value=0.9, confidence=1.0, evidence="good")
        report = ACPTrustReport(agent_profile=profile, signals=[signal])
        score = report.compute_score()
        assert score == 90.0
        assert report.risk_level == ACPRiskLevel.LOW

    def test_compute_score_mixed_signals(self):
        profile = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        signals = [
            ACPTrustSignal("a", value=1.0, confidence=0.9, evidence="great"),
            ACPTrustSignal("b", value=0.2, confidence=0.1, evidence="bad"),
        ]
        report = ACPTrustReport(agent_profile=profile, signals=signals)
        score = report.compute_score()
        # (1.0*0.9 + 0.2*0.1) / (0.9 + 0.1) = 0.92 / 1.0 = 92.0
        assert score == 92.0
        assert report.risk_level == ACPRiskLevel.LOW

    def test_risk_classification(self):
        assert ACPTrustReport._classify_risk(85) == ACPRiskLevel.LOW
        assert ACPTrustReport._classify_risk(70) == ACPRiskLevel.MEDIUM
        assert ACPTrustReport._classify_risk(50) == ACPRiskLevel.HIGH
        assert ACPTrustReport._classify_risk(10) == ACPRiskLevel.CRITICAL

    def test_to_json(self):
        profile = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        report = ACPTrustReport(agent_profile=profile, signals=[])
        j = report.to_json()
        assert '"agent"' in j
        assert '"risk_level"' in j

    def test_zero_confidence_signals(self):
        profile = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        signals = [
            ACPTrustSignal("a", value=0.5, confidence=0.0, evidence="no confidence"),
        ]
        report = ACPTrustReport(agent_profile=profile, signals=signals)
        score = report.compute_score()
        assert score == 0.0
        assert report.risk_level == ACPRiskLevel.UNKNOWN


# ── Signal Analyzers ─────────────────────────────────────────────

class TestAnalyzeJobHistory:
    def test_no_history(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_job_history(p)
        assert s.signal_type == "job_history"
        assert s.confidence == 0.1
        assert s.value == 0.0

    def test_small_sample(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            completed_jobs=3, failed_jobs=1,
        )
        s = analyze_job_history(p)
        assert s.confidence == 0.3
        assert s.value == 0.75

    def test_large_sample_perfect(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            completed_jobs=150, failed_jobs=0,
            total_revenue_usdc=500.0,
        )
        s = analyze_job_history(p)
        assert s.confidence == 0.95
        assert s.value == 1.0
        assert "$500.00" in s.evidence

    def test_medium_sample(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            completed_jobs=10, failed_jobs=5,
        )
        s = analyze_job_history(p)
        assert s.confidence == 0.6
        assert abs(s.value - 0.6667) < 0.01


class TestAnalyzeOfferingQuality:
    def test_no_offerings(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_offering_quality(p)
        assert s.value == 0.1

    def test_few_with_description(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            offerings_count=2, description="I do things",
        )
        s = analyze_offering_quality(p)
        assert s.value == 0.4

    def test_many_without_description(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            offerings_count=8,
        )
        s = analyze_offering_quality(p)
        assert s.value == 0.7


class TestAnalyzeWalletActivity:
    def test_no_data(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_wallet_activity(p)
        assert s.confidence == 0.1

    def test_new_wallet(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_wallet_activity(p, wallet_age_days=0.5)
        assert s.value == 0.1
        assert "very new" in s.evidence

    def test_old_active_wallet(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_wallet_activity(p, wallet_age_days=120, transaction_count=200)
        assert s.value > 0.9
        assert s.confidence == 0.7

    def test_empty_wallet(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_wallet_activity(p, transaction_count=0)
        assert s.value == 0.05


class TestAnalyzeRecency:
    def test_no_timestamp(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        s = analyze_recency(p)
        assert s.confidence == 0.2

    def test_very_recent(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            last_active=time.time() - 60,  # 1 minute ago
        )
        s = analyze_recency(p)
        assert s.value == 1.0

    def test_week_old(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            last_active=time.time() - 86400 * 5,  # 5 days ago
        )
        s = analyze_recency(p)
        assert s.value == 0.7

    def test_abandoned(self):
        p = ACPAgentProfile(
            wallet_address="0xabc", agent_name="Bot",
            last_active=time.time() - 86400 * 60,  # 60 days ago
        )
        s = analyze_recency(p)
        assert s.value == 0.1


# ── Full Report Generation ───────────────────────────────────────

class TestGenerateTrustReport:
    def test_new_agent(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="NewBot")
        report = generate_trust_report(p)
        assert report.overall_score < 30
        assert report.risk_level in (ACPRiskLevel.HIGH, ACPRiskLevel.CRITICAL)
        assert len(report.signals) == 4

    def test_established_agent(self):
        p = ACPAgentProfile(
            wallet_address="0xabc",
            agent_name="ProBot",
            description="Professional trading agent",
            offerings_count=6,
            completed_jobs=80,
            failed_jobs=2,
            total_revenue_usdc=1200.0,
            last_active=time.time() - 300,
        )
        report = generate_trust_report(p, wallet_age_days=90, transaction_count=500)
        assert report.overall_score > 80
        assert report.risk_level == ACPRiskLevel.LOW

    def test_suspicious_agent(self):
        p = ACPAgentProfile(
            wallet_address="0xabc",
            agent_name="SketchBot",
            completed_jobs=1,
            failed_jobs=4,
            last_active=time.time() - 86400 * 45,
        )
        report = generate_trust_report(p, wallet_age_days=0.5, transaction_count=2)
        assert report.overall_score < 40
        assert report.risk_level in (ACPRiskLevel.HIGH, ACPRiskLevel.CRITICAL)

    def test_report_serialization(self):
        p = ACPAgentProfile(wallet_address="0xabc", agent_name="Bot")
        report = generate_trust_report(p)
        d = report.to_dict()
        assert "signals" in d
        assert len(d["signals"]) == 4
        assert "overall_score" in d


# ── ACPJobVerifier ───────────────────────────────────────────────

class TestACPJobVerifier:
    @pytest.fixture
    def identity(self):
        return AgentIdentity()

    @pytest.fixture
    def verifier(self, identity):
        return ACPJobVerifier(identity)

    def test_acceptance_attestation(self, verifier):
        att = verifier.create_acceptance_attestation(
            job_id="job-123",
            buyer_wallet="0xBuyer",
            offering_name="deep_research",
            fee_usdc=1.0,
        )
        assert att is not None
        assert att.subject == "job-123"
        assert "acp.job.accept" in att.task
        assert att.signature is not None
        evidence = json.loads(att.evidence)
        assert evidence["buyer_wallet"] == "0xbuyer"  # lowercased

    def test_completion_attestation(self, verifier):
        att = verifier.create_completion_attestation(
            job_id="job-123",
            deliverable_hash="abc123",
            quality_score=0.95,
        )
        assert "acp.job.complete" in att.task
        evidence = json.loads(att.evidence)
        assert evidence["quality_score"] == 0.95

    def test_completion_attestation_clamps_quality(self, verifier):
        att = verifier.create_completion_attestation(
            job_id="job-123",
            deliverable_hash="abc123",
            quality_score=1.5,  # over max
        )
        evidence = json.loads(att.evidence)
        assert evidence["quality_score"] == 1.0

    def test_dispute_attestation(self, verifier):
        att = verifier.create_dispute_attestation(
            job_id="job-456",
            reason="Deliverable did not match specification",
            evidence_hash="evidence_sha256",
        )
        assert "acp.job.dispute" in att.task
        evidence = json.loads(att.evidence)
        assert "evidence_hash" in evidence

    def test_dispute_without_evidence(self, verifier):
        att = verifier.create_dispute_attestation(
            job_id="job-456",
            reason="Non-responsive seller",
        )
        evidence = json.loads(att.evidence)
        assert "evidence_hash" not in evidence
