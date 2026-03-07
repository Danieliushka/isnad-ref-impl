"""Tests for intent-commit schema (L0-L3)."""

import pytest
from src.intent.models import (
    IntentLevel,
    IntentScope,
    IntentCommitRequest,
    IntentRevealRequest,
    IntentCommitment,
    compute_commitment_hash,
    generate_nonce,
    verify_reveal,
)
from src.intent.validator import validate_commit, validate_reveal, IntentValidationError


class TestHashFunctions:
    def test_compute_commitment_hash_deterministic(self):
        h1 = compute_commitment_hash("review PR", "nonce1", "2026-03-07T15:00:00Z")
        h2 = compute_commitment_hash("review PR", "nonce1", "2026-03-07T15:00:00Z")
        assert h1 == h2

    def test_compute_commitment_hash_different_inputs(self):
        h1 = compute_commitment_hash("review PR", "nonce1", "2026-03-07T15:00:00Z")
        h2 = compute_commitment_hash("review PR", "nonce2", "2026-03-07T15:00:00Z")
        assert h1 != h2

    def test_verify_reveal_success(self):
        intent = "deploy contract"
        nonce = generate_nonce()
        ts = "2026-03-07T15:00:00Z"
        h = compute_commitment_hash(intent, nonce, ts)
        assert verify_reveal(h, intent, nonce, ts) is True

    def test_verify_reveal_failure(self):
        h = compute_commitment_hash("real intent", "nonce", "ts")
        assert verify_reveal(h, "fake intent", "nonce", "ts") is False

    def test_generate_nonce_unique(self):
        n1 = generate_nonce()
        n2 = generate_nonce()
        assert n1 != n2
        assert len(n1) == 32  # 16 bytes hex


class TestValidateCommit:
    def test_l0_requires_plaintext(self):
        req = IntentCommitRequest(agent_id="a", level=IntentLevel.L0)
        with pytest.raises(IntentValidationError, match="L0 requires intent_plaintext"):
            validate_commit(req)

    def test_l0_valid(self):
        req = IntentCommitRequest(agent_id="a", level=IntentLevel.L0, intent_plaintext="do thing")
        validate_commit(req)  # no exception

    def test_l1_requires_hash(self):
        req = IntentCommitRequest(agent_id="a", level=IntentLevel.L1)
        with pytest.raises(IntentValidationError, match="requires commitment_hash"):
            validate_commit(req)

    def test_l1_valid(self):
        req = IntentCommitRequest(agent_id="a", level=IntentLevel.L1, commitment_hash="abc123")
        validate_commit(req)

    def test_l2_requires_scope_and_sig(self):
        req = IntentCommitRequest(agent_id="a", level=IntentLevel.L2, commitment_hash="abc")
        with pytest.raises(IntentValidationError, match="requires scope"):
            validate_commit(req)

        req2 = IntentCommitRequest(
            agent_id="a", level=IntentLevel.L2, commitment_hash="abc",
            scope=IntentScope(tools=["git"])
        )
        with pytest.raises(IntentValidationError, match="requires Ed25519"):
            validate_commit(req2)

    def test_l2_valid(self):
        req = IntentCommitRequest(
            agent_id="a", level=IntentLevel.L2, commitment_hash="abc",
            scope=IntentScope(tools=["git"]), signature="sig"
        )
        validate_commit(req)

    def test_l3_valid(self):
        req = IntentCommitRequest(
            agent_id="a", level=IntentLevel.L3, commitment_hash="abc",
            scope=IntentScope(tools=["git"], max_value_usd=100), signature="sig"
        )
        validate_commit(req)


class TestValidateReveal:
    def test_reveal_l0(self):
        commitment = IntentCommitment(
            agent_id="a", level=IntentLevel.L0, status="committed"
        )
        reveal = IntentRevealRequest(
            commitment_id=commitment.id, intent_plaintext="did thing",
            nonce="x", timestamp="ts"
        )
        validate_reveal(commitment, reveal)  # no exception

    def test_reveal_l1_success(self):
        nonce = generate_nonce()
        ts = "2026-03-07T15:00:00Z"
        intent = "review code"
        h = compute_commitment_hash(intent, nonce, ts)

        commitment = IntentCommitment(
            agent_id="a", level=IntentLevel.L1, commitment_hash=h, status="committed"
        )
        reveal = IntentRevealRequest(
            commitment_id=commitment.id, intent_plaintext=intent,
            nonce=nonce, timestamp=ts
        )
        validate_reveal(commitment, reveal)

    def test_reveal_l1_mismatch(self):
        commitment = IntentCommitment(
            agent_id="a", level=IntentLevel.L1,
            commitment_hash="deadbeef", status="committed"
        )
        reveal = IntentRevealRequest(
            commitment_id=commitment.id, intent_plaintext="wrong",
            nonce="n", timestamp="t"
        )
        with pytest.raises(IntentValidationError, match="does not match"):
            validate_reveal(commitment, reveal)

    def test_reveal_already_revealed(self):
        commitment = IntentCommitment(
            agent_id="a", level=IntentLevel.L1,
            commitment_hash="x", status="revealed"
        )
        reveal = IntentRevealRequest(
            commitment_id=commitment.id, intent_plaintext="x",
            nonce="n", timestamp="t"
        )
        with pytest.raises(IntentValidationError, match="status is 'revealed'"):
            validate_reveal(commitment, reveal)
