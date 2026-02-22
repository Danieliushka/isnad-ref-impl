"""Tests for isnad.metrics — network health, security posture, trust distribution."""

import pytest
from datetime import datetime, timezone, timedelta

from isnad.core import (
    AgentIdentity, Attestation, TrustChain,
    RevocationEntry, RevocationRegistry,
)
from isnad.metrics import NetworkHealthMetrics, SecurityPosture, TrustDistribution


# ─── Helpers ───────────────────────────────────────────────────────

def _make_agents(n: int) -> list[AgentIdentity]:
    return [AgentIdentity() for _ in range(n)]


def _attest(witness: AgentIdentity, subject: AgentIdentity,
            task: str = "code-review", ts: str | None = None) -> Attestation:
    att = Attestation(
        subject=subject.agent_id,
        witness=witness.agent_id,
        task=task,
        timestamp=ts,
    )
    att.sign(witness)
    return att


def _build_chain(attestations: list[Attestation]) -> TrustChain:
    chain = TrustChain()
    for a in attestations:
        chain.add(a)
    return chain


# ─── NetworkHealthMetrics ──────────────────────────────────────────

class TestNetworkHealthMetrics:

    def test_empty_chain(self):
        chain = TrustChain()
        m = NetworkHealthMetrics(chain)
        assert m.coverage_ratio == 0.0
        assert m.avg_chain_length == 0.0
        assert m.orphan_ratio == 0.0
        assert m.witness_diversity == 0.0

    def test_single_attestation(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        m = NetworkHealthMetrics(chain)
        # b is subject → covered; a is witness-only → orphan
        assert m.coverage_ratio == 0.5
        assert m.orphan_ratio == 0.5

    def test_full_coverage(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b), _attest(b, a)])
        m = NetworkHealthMetrics(chain)
        assert m.coverage_ratio == 1.0
        assert m.orphan_ratio == 0.0

    def test_avg_chain_length(self):
        a, b, c = _make_agents(3)
        # b gets 2 attestations, c gets 1, a gets 0
        chain = _build_chain([
            _attest(a, b), _attest(c, b), _attest(a, c),
        ])
        m = NetworkHealthMetrics(chain)
        # depths: a=0, b=2, c=1 → avg = 1.0
        assert m.avg_chain_length == 1.0

    def test_witness_diversity_single_witness(self):
        a, b = _make_agents(2)
        chain = _build_chain([
            _attest(a, b, task="t1"), _attest(a, b, task="t2"),
        ])
        m = NetworkHealthMetrics(chain)
        # Only b is subject, has 1 unique witness (a)
        assert m.witness_diversity == 1.0

    def test_witness_diversity_multiple(self):
        a, b, c = _make_agents(3)
        chain = _build_chain([_attest(a, c), _attest(b, c)])
        m = NetworkHealthMetrics(chain)
        # c has 2 unique witnesses → diversity for c = 2
        # avg over subjects with attestations (only c) = 2.0
        assert m.witness_diversity == 2.0

    def test_explicit_agent_ids(self):
        a, b = _make_agents(2)
        extra = AgentIdentity()
        chain = _build_chain([_attest(a, b)])
        ids = {a.agent_id, b.agent_id, extra.agent_id}
        m = NetworkHealthMetrics(chain, agent_ids=ids)
        assert m.coverage_ratio == pytest.approx(1 / 3)
        assert m.orphan_ratio == pytest.approx(2 / 3)

    def test_to_dict(self):
        chain = TrustChain()
        m = NetworkHealthMetrics(chain)
        d = m.to_dict()
        assert "coverage_ratio" in d
        assert "total_agents" in d
        assert "total_attestations" in d

    def test_orphan_ratio_all_orphans(self):
        """With explicit agent_ids but empty chain, all are orphans."""
        chain = TrustChain()
        ids = {"a", "b", "c"}
        m = NetworkHealthMetrics(chain, agent_ids=ids)
        assert m.orphan_ratio == 1.0
        assert m.coverage_ratio == 0.0

    def test_large_network(self):
        agents = _make_agents(10)
        atts = []
        for i in range(9):
            atts.append(_attest(agents[i], agents[i + 1]))
        chain = _build_chain(atts)
        m = NetworkHealthMetrics(chain)
        # agents[0] is never a subject → orphan
        assert m.coverage_ratio == 0.9
        assert m.orphan_ratio == 0.1


# ─── SecurityPosture ──────────────────────────────────────────────

class TestSecurityPosture:

    def test_empty(self):
        chain = TrustChain()
        sp = SecurityPosture(chain)
        assert sp.identity_strength == 0.0
        assert sp.freshness == 0.0
        assert sp.revocation_coverage == 1.0  # no compromised = perfect
        assert sp.anomaly_rate == 0.0

    def test_identity_strength(self):
        a, b, c = _make_agents(3)
        chain = _build_chain([_attest(a, b)])
        ids = {a.agent_id, b.agent_id, c.agent_id}
        anchors = {a.agent_id: 2, b.agent_id: 1, c.agent_id: 3}
        sp = SecurityPosture(chain, agent_ids=ids, bootstrap_anchors=anchors)
        # a(2) and c(3) are multi-factor → 2/3
        assert sp.identity_strength == pytest.approx(2 / 3)

    def test_identity_strength_none(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        sp = SecurityPosture(chain, bootstrap_anchors={})
        assert sp.identity_strength == 0.0

    def test_freshness_all_fresh(self):
        a, b = _make_agents(2)
        now = datetime.now(timezone.utc)
        epoch_start = (now - timedelta(hours=1)).isoformat()
        att = _attest(a, b)  # timestamp is "now"
        chain = _build_chain([att])
        sp = SecurityPosture(chain, current_epoch_start=epoch_start)
        assert sp.freshness == 1.0

    def test_freshness_none_fresh(self):
        a, b = _make_agents(2)
        old_ts = "2020-01-01T00:00:00+00:00"
        att = _attest(a, b, ts=old_ts)
        chain = _build_chain([att])
        epoch_start = "2025-01-01T00:00:00+00:00"
        sp = SecurityPosture(chain, current_epoch_start=epoch_start)
        assert sp.freshness == 0.0

    def test_freshness_no_epoch(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        sp = SecurityPosture(chain)
        assert sp.freshness == 0.0

    def test_revocation_coverage_all_revoked(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        reg = RevocationRegistry()
        entry = RevocationEntry(
            target_id=a.agent_id, reason="compromised",
            revoked_by=b.agent_id
        )
        reg.revoke(entry)
        sp = SecurityPosture(
            chain, compromised_ids={a.agent_id}, revocations=reg
        )
        assert sp.revocation_coverage == 1.0

    def test_revocation_coverage_partial(self):
        a, b, c = _make_agents(3)
        chain = _build_chain([_attest(a, b)])
        reg = RevocationRegistry()
        entry = RevocationEntry(
            target_id=a.agent_id, reason="compromised",
            revoked_by=b.agent_id
        )
        reg.revoke(entry)
        sp = SecurityPosture(
            chain,
            compromised_ids={a.agent_id, c.agent_id},
            revocations=reg,
        )
        assert sp.revocation_coverage == 0.5

    def test_revocation_no_registry(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        sp = SecurityPosture(chain, compromised_ids={a.agent_id})
        assert sp.revocation_coverage == 0.0

    def test_anomaly_rate(self):
        a, b, c = _make_agents(3)
        chain = _build_chain([_attest(a, b)])
        ids = {a.agent_id, b.agent_id, c.agent_id}
        scores = {a.agent_id: 0.8, b.agent_id: 0.3, c.agent_id: 0.6}
        sp = SecurityPosture(
            chain, agent_ids=ids,
            anomaly_scores=scores, anomaly_threshold=0.5,
        )
        # a(0.8) and c(0.6) > 0.5 → 2/3
        assert sp.anomaly_rate == pytest.approx(2 / 3)

    def test_anomaly_rate_no_scores(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        sp = SecurityPosture(chain)
        assert sp.anomaly_rate == 0.0

    def test_overall_score_perfect(self):
        a, b = _make_agents(2)
        now = datetime.now(timezone.utc)
        epoch_start = (now - timedelta(hours=1)).isoformat()
        chain = _build_chain([_attest(a, b)])
        ids = {a.agent_id, b.agent_id}
        anchors = {a.agent_id: 2, b.agent_id: 2}
        sp = SecurityPosture(
            chain, agent_ids=ids,
            bootstrap_anchors=anchors,
            current_epoch_start=epoch_start,
        )
        # identity=1.0, freshness=1.0, revocation=1.0, anomaly=0.0
        assert sp.overall_score == pytest.approx(1.0)

    def test_overall_score_zero(self):
        chain = TrustChain()
        ids = {"x"}
        sp = SecurityPosture(
            chain, agent_ids=ids,
            compromised_ids={"x"},
            anomaly_scores={"x": 1.0}, anomaly_threshold=0.5,
        )
        # identity=0, freshness=0, revocation=0, anomaly_rate=1→(1-1)=0
        assert sp.overall_score == 0.0

    def test_to_dict(self):
        chain = TrustChain()
        sp = SecurityPosture(chain)
        d = sp.to_dict()
        assert "overall_score" in d
        assert "freshness" in d


# ─── TrustDistribution ────────────────────────────────────────────

class TestTrustDistribution:

    def test_empty(self):
        chain = TrustChain()
        td = TrustDistribution(chain)
        assert td.mean_trust_score == 0.0
        assert td.median_trust_score == 0.0
        assert td.std_dev == 0.0
        assert td.scope_coverage == 0

    def test_scores_computed(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        td = TrustDistribution(chain)
        assert len(td.scores) == 2  # a and b
        assert any(s > 0 for s in td.scores)

    def test_mean_and_median(self):
        a, b, c = _make_agents(3)
        chain = _build_chain([_attest(a, b), _attest(a, c)])
        td = TrustDistribution(chain)
        assert td.mean_trust_score >= 0.0
        assert td.median_trust_score >= 0.0

    def test_std_dev_single_agent(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        td = TrustDistribution(chain, agent_ids={b.agent_id})
        assert td.std_dev == 0.0  # single score → no deviation

    def test_histogram_default_bins(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        td = TrustDistribution(chain)
        h = td.trust_histogram()
        assert len(h) == 10
        assert sum(h) == len(td.scores)

    def test_histogram_custom_bins(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        td = TrustDistribution(chain)
        h = td.trust_histogram(bins=5)
        assert len(h) == 5
        assert sum(h) == len(td.scores)

    def test_histogram_invalid_bins(self):
        chain = TrustChain()
        td = TrustDistribution(chain)
        with pytest.raises(ValueError):
            td.trust_histogram(bins=0)

    def test_scope_coverage(self):
        a, b = _make_agents(2)
        chain = _build_chain([
            _attest(a, b, task="code-review"),
            _attest(a, b, task="data-analysis"),
            _attest(a, b, task="code-review"),  # dup
        ])
        td = TrustDistribution(chain)
        assert td.scope_coverage == 2

    def test_scope_coverage_empty(self):
        chain = TrustChain()
        td = TrustDistribution(chain)
        assert td.scope_coverage == 0

    def test_scoped_distribution(self):
        a, b = _make_agents(2)
        chain = _build_chain([
            _attest(a, b, task="code-review"),
            _attest(a, b, task="data-analysis"),
        ])
        td = TrustDistribution(chain, scope="code")
        # Scores filtered by scope
        assert td.mean_trust_score >= 0.0

    def test_to_dict(self):
        a, b = _make_agents(2)
        chain = _build_chain([_attest(a, b)])
        td = TrustDistribution(chain)
        d = td.to_dict()
        assert "histogram" in d
        assert "agent_count" in d
        assert d["agent_count"] == 2

    def test_histogram_score_at_1(self):
        """Agents with score exactly 1.0 go into last bin."""
        a, b, c, d, e, f = _make_agents(6)
        # Give b many attestations from different witnesses to max trust
        chain = _build_chain([
            _attest(a, b), _attest(c, b), _attest(d, b),
            _attest(e, b), _attest(f, b),
        ])
        td = TrustDistribution(chain, agent_ids={b.agent_id})
        h = td.trust_histogram(bins=10)
        assert sum(h) == 1
        # Score should be 1.0 → last bin
        assert h[-1] == 1

    def test_large_distribution(self):
        agents = _make_agents(20)
        atts = []
        for i in range(19):
            atts.append(_attest(agents[i], agents[i + 1]))
        chain = _build_chain(atts)
        td = TrustDistribution(chain)
        assert len(td.scores) == 20
        assert td.scope_coverage == 1  # all "code-review"
        h = td.trust_histogram()
        assert sum(h) == 20
