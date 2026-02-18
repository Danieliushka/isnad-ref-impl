"""Tests for isnad.batch — batch verification."""

import pytest
from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.batch import verify_batch, verify_chain_batch, BatchReport


@pytest.fixture
def agents():
    return [AgentIdentity() for _ in range(5)]


@pytest.fixture
def valid_attestations(agents):
    """Create 10 valid signed attestations."""
    atts = []
    for i in range(10):
        subject = agents[i % 5]
        witness = agents[(i + 1) % 5]
        att = Attestation(
            subject=subject.agent_id,
            witness=witness.agent_id,
            task=f"task_{i}",
            evidence={"score": 0.9},
        ).sign(witness)
        atts.append(att)
    return atts


class TestVerifyBatch:
    def test_all_valid(self, valid_attestations):
        report = verify_batch(valid_attestations)
        assert report.total == 10
        assert report.passed == 10
        assert report.failed == 0
        assert report.pass_rate == 1.0
        assert report.elapsed_ms > 0

    def test_with_invalid(self, valid_attestations, agents):
        # Tamper with one attestation
        valid_attestations[3].signature = "deadbeef" * 16
        report = verify_batch(valid_attestations)
        assert report.total == 10
        assert report.passed == 9
        assert report.failed == 1
        assert len(report.failed_results) == 1
        assert report.failed_results[0].attestation_id == valid_attestations[3].attestation_id

    def test_fail_fast(self, valid_attestations):
        valid_attestations[2].signature = "deadbeef" * 16
        report = verify_batch(valid_attestations, fail_fast=True)
        # Should stop after first failure (index 2 = 3rd item)
        assert report.total == 10
        assert len(report.results) == 3
        assert report.failed == 1
        assert report.passed == 2

    def test_empty_batch(self):
        report = verify_batch([])
        assert report.total == 0
        assert report.pass_rate == 0.0

    def test_unsigned_attestation(self, agents):
        att = Attestation(
            subject=agents[0].agent_id,
            witness=agents[1].agent_id,
            task="unsigned",
        )
        report = verify_batch([att])
        assert report.failed == 1
        assert report.passed == 0

    def test_summary(self, valid_attestations):
        valid_attestations[0].signature = "bad" * 20
        report = verify_batch(valid_attestations)
        s = report.summary()
        assert s["total"] == 10
        assert s["passed"] == 9
        assert s["failed"] == 1
        assert len(s["failures"]) == 1
        assert "pass_rate" in s


class TestVerifyChainBatch:
    def test_valid_chains(self, agents):
        chains = []
        for i in range(3):
            chain = TrustChain()
            for j in range(3):
                w = agents[(i + j + 1) % 5]
                att = Attestation(
                    subject=agents[i].agent_id,
                    witness=w.agent_id,
                    task=f"chain_{i}_task_{j}",
                    evidence={"ok": True},
                ).sign(w)
                chain.add(att)
            chains.append(chain)

        report = verify_chain_batch(chains)
        assert report.total == 3
        assert report.passed == 3
        assert report.failed == 0

    def test_mixed_chains(self, agents):
        good_chain = TrustChain()
        att = Attestation(
            subject=agents[0].agent_id,
            witness=agents[1].agent_id,
            task="good",
        ).sign(agents[1])
        good_chain.add(att)

        bad_chain = TrustChain()
        bad_att = Attestation(
            subject=agents[2].agent_id,
            witness=agents[3].agent_id,
            task="bad",
        ).sign(agents[3])
        bad_chain.add(bad_att)
        # Tamper after adding (add() verifies on entry)
        bad_chain.attestations[0].signature = "tampered" * 8

        report = verify_chain_batch([good_chain, bad_chain])
        assert report.passed == 1
        assert report.failed == 1
