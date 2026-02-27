"""Tests for GET /api/v1/agents/{agent_id}/trust-score endpoint (DAN-80)."""

import math
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from isnad.api_v1 import _compute_trust_score, _TRUST_WEIGHTS, get_trust_score


# ── Unit tests for _compute_trust_score ──


class TestComputeTrustScore:
    """Test the pure scoring function."""

    def test_zero_everything(self):
        score, bd = _compute_trust_score(0, 0, 0, False, False)
        assert score == 0
        assert bd.attestation_score == 0.0
        assert bd.diversity_score == 0.0
        assert bd.age_score == 0.0
        assert bd.verification_score == 0.0

    def test_max_everything(self):
        score, bd = _compute_trust_score(100, 50, 365, True, True)
        assert score == 100

    def test_attestation_scaling(self):
        """More attestations → higher score, log-scaled."""
        s1, _ = _compute_trust_score(1, 0, 0, False, False)
        s5, _ = _compute_trust_score(5, 0, 0, False, False)
        s10, _ = _compute_trust_score(10, 0, 0, False, False)
        assert s1 < s5 < s10

    def test_diversity_scaling(self):
        """More unique witnesses → higher score."""
        s1, _ = _compute_trust_score(0, 1, 0, False, False)
        s3, _ = _compute_trust_score(0, 3, 0, False, False)
        s5, _ = _compute_trust_score(0, 5, 0, False, False)
        assert s1 < s3 < s5

    def test_age_linear(self):
        """Age score is linear up to 365 days."""
        _, bd30 = _compute_trust_score(0, 0, 30, False, False)
        _, bd180 = _compute_trust_score(0, 0, 180, False, False)
        _, bd365 = _compute_trust_score(0, 0, 365, False, False)
        _, bd730 = _compute_trust_score(0, 0, 730, False, False)
        assert bd30.age_score < bd180.age_score < bd365.age_score
        assert bd365.age_score == 100.0
        assert bd730.age_score == 100.0  # capped

    def test_verification_certified(self):
        _, bd = _compute_trust_score(0, 0, 0, False, True)
        assert bd.verification_score == 60.0

    def test_verification_verified(self):
        _, bd = _compute_trust_score(0, 0, 0, True, False)
        assert bd.verification_score == 40.0

    def test_verification_both(self):
        _, bd = _compute_trust_score(0, 0, 0, True, True)
        assert bd.verification_score == 100.0

    def test_weights_sum_to_one(self):
        total = sum(_TRUST_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_score_range(self):
        """Score always 0-100."""
        for att in [0, 1, 5, 50]:
            for div in [0, 1, 10]:
                for age in [0, 30, 365, 1000]:
                    for ver in [True, False]:
                        for cert in [True, False]:
                            s, _ = _compute_trust_score(att, div, age, ver, cert)
                            assert 0 <= s <= 100, f"Score {s} out of range"

    def test_breakdown_weights_match(self):
        _, bd = _compute_trust_score(5, 3, 100, True, False)
        assert bd.attestation_weight == _TRUST_WEIGHTS["attestation_count"]
        assert bd.diversity_weight == _TRUST_WEIGHTS["source_diversity"]
        assert bd.age_weight == _TRUST_WEIGHTS["registration_age"]
        assert bd.verification_weight == _TRUST_WEIGHTS["verification_status"]

    def test_realistic_new_agent(self):
        """New agent with 2 attestations from 2 sources, 7 days old."""
        score, bd = _compute_trust_score(2, 2, 7, False, False)
        assert 5 <= score <= 30  # should be low but nonzero

    def test_realistic_established_agent(self):
        """Established agent: 8 attestations, 4 sources, 200 days, verified."""
        score, bd = _compute_trust_score(8, 4, 200, True, True)
        assert 60 <= score <= 95


# ── API endpoint integration tests ──


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_trust_score_endpoint_agent_not_found():
    """Should return 404 for nonexistent agent."""
    from isnad.api_v1 import get_trust_score, _db
    import isnad.api_v1 as api_module

    mock_db = AsyncMock()
    mock_db.get_agent = AsyncMock(return_value=None)
    mock_db.get_agent_by_name = AsyncMock(return_value=None)

    original_db = api_module._db
    api_module._db = mock_db

    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_trust_score("nonexistent-agent")
        assert exc_info.value.status_code == 404
    finally:
        api_module._db = original_db


@pytest.mark.asyncio
async def test_trust_score_endpoint_no_db():
    """Should return 503 if database not available."""
    import isnad.api_v1 as api_module

    original_db = api_module._db
    api_module._db = None

    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_trust_score("some-agent")
        assert exc_info.value.status_code == 503
    finally:
        api_module._db = original_db


@pytest.mark.asyncio
async def test_trust_score_endpoint_success():
    """Should return valid trust score with breakdown."""
    import isnad.api_v1 as api_module

    created_at = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    mock_db = AsyncMock()
    mock_db.get_agent = AsyncMock(return_value={
        "id": "test-agent-123",
        "name": "TestAgent",
        "created_at": created_at,
        "is_certified": True,
    })
    mock_db.get_attestations_for_subject = AsyncMock(return_value=[
        {"witness_id": "w1", "subject_id": "test-agent-123"},
        {"witness_id": "w2", "subject_id": "test-agent-123"},
        {"witness_id": "w1", "subject_id": "test-agent-123"},
    ])
    mock_db.get_badges = AsyncMock(return_value=[
        {"badge_type": "isnad_verified", "agent_id": "test-agent-123"},
    ])

    original_db = api_module._db
    api_module._db = mock_db

    try:
        result = await get_trust_score("test-agent-123")
        assert result.agent_id == "test-agent-123"
        assert 0 <= result.trust_score <= 100
        assert result.breakdown.attestation_count == 3
        assert result.breakdown.source_diversity == 2
        assert result.breakdown.registration_age_days == pytest.approx(90, abs=1)
        assert result.breakdown.is_verified is True
        assert result.breakdown.is_certified is True
        assert result.breakdown.verification_score == 100.0
    finally:
        api_module._db = original_db


@pytest.mark.asyncio
async def test_trust_score_endpoint_name_lookup():
    """Should resolve agent by name if ID lookup fails."""
    import isnad.api_v1 as api_module

    mock_db = AsyncMock()
    mock_db.get_agent = AsyncMock(return_value=None)
    mock_db.get_agent_by_name = AsyncMock(return_value={
        "id": "resolved-id",
        "name": "MyAgent",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_certified": False,
    })
    mock_db.get_attestations_for_subject = AsyncMock(return_value=[])
    mock_db.get_badges = AsyncMock(return_value=[])

    original_db = api_module._db
    api_module._db = mock_db

    try:
        result = await get_trust_score("MyAgent")
        assert result.agent_id == "resolved-id"
        assert result.trust_score >= 0
    finally:
        api_module._db = original_db
