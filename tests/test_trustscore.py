"""Comprehensive tests for the isnad→TrustScore bridge module."""

import math
import pytest
from datetime import datetime, timezone, timedelta

from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.trustscore.bridge import IsnadBridge, InteractionRecord, EndorsementRecord
from isnad.trustscore.scorer import TrustScorer


# ─── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def agents():
    return {name: AgentIdentity() for name in ["alice", "bob", "charlie", "dave"]}


@pytest.fixture
def signed_attestation(agents):
    att = Attestation(
        subject=agents["bob"].agent_id,
        witness=agents["alice"].agent_id,
        task="code-review",
        evidence="https://github.com/example/pr/1",
    ).sign(agents["alice"])
    return att


@pytest.fixture
def chain_with_attestations(agents):
    chain = TrustChain()
    atts = [
        Attestation(subject=agents["bob"].agent_id, witness=agents["alice"].agent_id,
                     task="code-review", evidence="https://example.com/pr/1").sign(agents["alice"]),
        Attestation(subject=agents["bob"].agent_id, witness=agents["charlie"].agent_id,
                     task="data-analysis", evidence="https://example.com/report").sign(agents["charlie"]),
        Attestation(subject=agents["charlie"].agent_id, witness=agents["alice"].agent_id,
                     task="code-review", evidence="https://example.com/pr/2").sign(agents["alice"]),
        Attestation(subject=agents["charlie"].agent_id, witness=agents["bob"].agent_id,
                     task="testing", evidence="").sign(agents["bob"]),
    ]
    for a in atts:
        chain.add(a)
    return chain


# ─── Bridge: Conversion Tests ─────────────────────────────────────

class TestBridgeConversion:
    def test_attestation_to_interaction(self, chain_with_attestations):
        bridge = IsnadBridge(chain_with_attestations)
        interactions = bridge.to_interactions()
        assert len(interactions) == 4
        ir = interactions[0]
        assert isinstance(ir, InteractionRecord)
        assert ir.outcome == "verified"
        assert ir.interaction_type == "code-review"
        assert "witness" in ir.context

    def test_attestation_to_endorsement(self, chain_with_attestations):
        bridge = IsnadBridge(chain_with_attestations)
        endorsements = bridge.to_endorsements()
        assert len(endorsements) == 4
        er = endorsements[0]
        assert isinstance(er, EndorsementRecord)
        assert er.confidence == 1.0
        assert er.skill_area == "code-review"
        assert len(er.evidence_hash) == 16

    def test_unverified_attestation(self, agents):
        att = Attestation(subject=agents["bob"].agent_id, witness=agents["alice"].agent_id,
                          task="test", evidence="")
        # Not signed → unverified
        chain = TrustChain()
        # Force-add without verification
        chain.attestations.append(att)
        bridge = IsnadBridge(chain)
        ir = bridge.attestation_to_interaction(att)
        assert ir.outcome == "unverified"
        er = bridge.attestation_to_endorsement(att)
        assert er.confidence == 0.0

    def test_empty_evidence_hash(self, agents):
        att = Attestation(subject=agents["bob"].agent_id, witness=agents["alice"].agent_id,
                          task="test", evidence="").sign(agents["alice"])
        chain = TrustChain()
        chain.add(att)
        bridge = IsnadBridge(chain)
        er = bridge.to_endorsements()[0]
        assert er.evidence_hash == ""

    def test_to_dict(self, signed_attestation):
        chain = TrustChain()
        chain.add(signed_attestation)
        bridge = IsnadBridge(chain)
        ir = bridge.to_interactions()[0]
        d = ir.to_dict()
        assert d["agent_id"] == signed_attestation.subject
        er = bridge.to_endorsements()[0]
        d2 = er.to_dict()
        assert d2["endorser_id"] == signed_attestation.witness


# ─── Bridge: Trust Decay ──────────────────────────────────────────

class TestTrustDecay:
    def test_no_decay_at_zero_days(self):
        assert IsnadBridge.trust_decay(1.0, 0.0) == 1.0

    def test_half_at_half_life(self):
        result = IsnadBridge.trust_decay(1.0, 30.0, half_life=30.0)
        assert abs(result - 0.5) < 1e-9

    def test_quarter_at_two_half_lives(self):
        result = IsnadBridge.trust_decay(1.0, 60.0, half_life=30.0)
        assert abs(result - 0.25) < 1e-9

    def test_base_score_scaling(self):
        result = IsnadBridge.trust_decay(0.8, 30.0, half_life=30.0)
        assert abs(result - 0.4) < 1e-9

    def test_custom_half_life(self):
        result = IsnadBridge.trust_decay(1.0, 10.0, half_life=10.0)
        assert abs(result - 0.5) < 1e-9


# ─── Bridge: Reinforcement Multiplier ─────────────────────────────

class TestReinforcementMultiplier:
    def test_zero_consecutive(self):
        assert IsnadBridge.reinforcement_multiplier(0) == 1.0

    def test_five_consecutive(self):
        assert IsnadBridge.reinforcement_multiplier(5) == 1.5

    def test_cap_at_two(self):
        assert IsnadBridge.reinforcement_multiplier(10) == 2.0
        assert IsnadBridge.reinforcement_multiplier(100) == 2.0


# ─── Bridge: Agent Profile ────────────────────────────────────────

class TestAgentProfile:
    def test_profile_basic(self, chain_with_attestations, agents):
        bridge = IsnadBridge(chain_with_attestations)
        profile = bridge.agent_trust_profile(agents["bob"].agent_id)
        assert profile["agent_id"] == agents["bob"].agent_id
        assert profile["attestation_count"] == 2
        assert profile["unique_witnesses"] == 2
        assert profile["raw_score"] > 0
        assert 0.0 <= profile["weighted_score"] <= 1.0

    def test_profile_unknown_agent(self, chain_with_attestations):
        bridge = IsnadBridge(chain_with_attestations)
        profile = bridge.agent_trust_profile("agent:nonexistent")
        assert profile["raw_score"] == 0.0
        assert profile["weighted_score"] == 0.0
        assert profile["attestation_count"] == 0

    def test_profile_with_old_reference(self, chain_with_attestations, agents):
        bridge = IsnadBridge(chain_with_attestations)
        future = datetime.now(timezone.utc) + timedelta(days=60)
        profile = bridge.agent_trust_profile(agents["bob"].agent_id, reference_time=future)
        assert profile["days_since_last"] >= 59.0
        assert profile["weighted_score"] < profile["raw_score"]  # decay applied

    def test_profile_skills(self, chain_with_attestations, agents):
        bridge = IsnadBridge(chain_with_attestations)
        profile = bridge.agent_trust_profile(agents["charlie"].agent_id)
        assert "code-review" in profile["skills"]
        assert "testing" in profile["skills"]


# ─── Bridge: Agent Comparison ─────────────────────────────────────

class TestAgentComparison:
    def test_compare(self, chain_with_attestations, agents):
        bridge = IsnadBridge(chain_with_attestations)
        result = bridge.compare_agents(agents["bob"].agent_id, agents["charlie"].agent_id)
        assert "agent_a" in result
        assert "agent_b" in result
        assert "score_difference" in result
        assert result["higher_trust"] in [agents["bob"].agent_id, agents["charlie"].agent_id, "equal"]

    def test_compare_unknown(self, chain_with_attestations, agents):
        bridge = IsnadBridge(chain_with_attestations)
        result = bridge.compare_agents(agents["bob"].agent_id, "agent:ghost")
        assert result["higher_trust"] == agents["bob"].agent_id


# ─── Scorer Tests ─────────────────────────────────────────────────

class TestScorer:
    def test_empty_scorer(self):
        scorer = TrustScorer()
        assert scorer.compute() == 0.0

    def test_basic_score(self, chain_with_attestations):
        bridge = IsnadBridge(chain_with_attestations)
        scorer = TrustScorer(
            interactions=bridge.to_interactions(),
            endorsements=bridge.to_endorsements(),
        )
        score = scorer.compute()
        assert 0.0 <= score <= 1.0

    def test_detailed_output(self, chain_with_attestations):
        bridge = IsnadBridge(chain_with_attestations)
        scorer = TrustScorer(
            interactions=bridge.to_interactions(),
            endorsements=bridge.to_endorsements(),
        )
        detail = scorer.compute_detailed()
        assert "trust_score" in detail
        assert "signals" in detail
        assert set(detail["signals"].keys()) == {"relationship_graph", "activity_rhythm",
                                                   "topic_drift", "writing_fingerprint"}
        assert detail["interaction_count"] == 4
        assert detail["endorsement_count"] == 4

    def test_weights_sum_to_one(self):
        total = sum(TrustScorer.WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_high_quality_endorsements(self):
        endorsements = [
            EndorsementRecord(f"endorser_{i}", "target", "code", 1.0, f"hash{i}")
            for i in range(8)
        ]
        interactions = [
            InteractionRecord("target", "code", "verified",
                              (datetime.now(timezone.utc) + timedelta(hours=i)).isoformat(),
                              {"evidence": "http://example.com"})
            for i in range(8)
        ]
        scorer = TrustScorer(interactions=interactions, endorsements=endorsements)
        score = scorer.compute()
        assert score > 0.5  # Good agent should score well

    def test_relationship_graph_diversity(self):
        # Single endorser
        e1 = [EndorsementRecord("same", "target", "code", 1.0, "h") for _ in range(5)]
        s1 = TrustScorer(endorsements=e1)
        # Multiple endorsers
        e2 = [EndorsementRecord(f"e{i}", "target", "code", 1.0, "h") for i in range(5)]
        s2 = TrustScorer(endorsements=e2)
        assert s2._relationship_graph_score() > s1._relationship_graph_score()

    def test_activity_rhythm_regular(self):
        base = datetime.now(timezone.utc)
        interactions = [
            InteractionRecord("a", "task", "ok", (base + timedelta(hours=i * 24)).isoformat(), {})
            for i in range(5)
        ]
        scorer = TrustScorer(interactions=interactions)
        assert scorer._activity_rhythm_score() > 0.8  # Very regular

    def test_activity_rhythm_single(self):
        ir = InteractionRecord("a", "task", "ok", datetime.now(timezone.utc).isoformat(), {})
        scorer = TrustScorer(interactions=[ir])
        assert scorer._activity_rhythm_score() == 0.5

    def test_topic_drift_focused(self):
        interactions = [InteractionRecord("a", "code-review", "ok", "", {}) for _ in range(10)]
        endorsements = [EndorsementRecord("e", "a", "code-review", 1.0, "h") for _ in range(5)]
        scorer = TrustScorer(interactions=interactions, endorsements=endorsements)
        assert scorer._topic_drift_score() == 1.0  # Single topic = max focus

    def test_writing_fingerprint_all_evidence(self):
        interactions = [
            InteractionRecord("a", "t", "ok", "", {"evidence": "http://x.com"})
            for _ in range(5)
        ]
        endorsements = [EndorsementRecord("e", "a", "s", 1.0, "hash") for _ in range(5)]
        scorer = TrustScorer(interactions=interactions, endorsements=endorsements)
        assert scorer._writing_fingerprint_score() == 1.0

    def test_writing_fingerprint_no_evidence(self):
        interactions = [InteractionRecord("a", "t", "ok", "", {}) for _ in range(5)]
        endorsements = [EndorsementRecord("e", "a", "s", 1.0, "") for _ in range(5)]
        scorer = TrustScorer(interactions=interactions, endorsements=endorsements)
        assert scorer._writing_fingerprint_score() == 0.0


# ─── Integration ───────────────────────────────────────────────────

class TestIntegration:
    def test_full_pipeline(self):
        """End-to-end: create agents → attest → bridge → score."""
        alice = AgentIdentity()
        bob = AgentIdentity()
        charlie = AgentIdentity()

        chain = TrustChain()
        for i in range(5):
            att = Attestation(
                subject=bob.agent_id, witness=alice.agent_id,
                task="code-review", evidence=f"https://example.com/pr/{i}",
                timestamp=(datetime.now(timezone.utc) + timedelta(days=i)).isoformat(),
            ).sign(alice)
            chain.add(att)

        att2 = Attestation(
            subject=bob.agent_id, witness=charlie.agent_id,
            task="testing", evidence="https://example.com/test",
        ).sign(charlie)
        chain.add(att2)

        bridge = IsnadBridge(chain)
        interactions = bridge.to_interactions()
        endorsements = bridge.to_endorsements()

        assert len(interactions) == 6
        assert len(endorsements) == 6

        profile = bridge.agent_trust_profile(bob.agent_id)
        assert profile["attestation_count"] == 6
        assert profile["reinforcement_multiplier"] == min(1 + 0.1 * 6, 2.0)

        scorer = TrustScorer(interactions=interactions, endorsements=endorsements)
        result = scorer.compute_detailed()
        assert 0.0 <= result["trust_score"] <= 1.0
        assert result["trust_score"] > 0  # Should have some trust
