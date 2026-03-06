"""Tests for scoring engine v3."""

import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from isnad.scoring.engine_v3 import (
    score_provenance, score_track_record, score_presence, score_endorsements,
    freshness_decay, assign_tier, ScoringEngineV3, ScoreResult,
    DimensionResult, COLD_START_SCORE, _get_agent_age_days,
)
from isnad.scoring.confidence import compute_confidence
from isnad.scoring.collectors.github_collector_v3 import GitHubData
from isnad.scoring.collectors.ugig_collector import UgigData
from isnad.scoring.collectors.internal_collector import InternalData
from isnad.scoring.collectors.platform_verifier import PlatformVerification


# ── Provenance ──

def test_provenance_empty_agent():
    assert score_provenance({}, False) == 0.0


def test_provenance_full_agent():
    agent = {
        "public_key": "a" * 64,
        "contact_email": "test@example.com",
        "agent_type": "autonomous",
        "avatar_url": "https://example.com/avatar.png",
        "metadata": {"operator": "Daniel K", "description": "A" * 60},
    }
    score = score_provenance(agent, github_verified=True)
    # 10 + 8 + 5 + 4 + 3 + 2 + 1 = 33 / 40 = 0.825
    assert score == pytest.approx(33 / 40, abs=0.01)


def test_provenance_partial():
    agent = {"public_key": "a" * 64, "agent_type": "tool"}
    score = score_provenance(agent, False)
    # 10 + 2 = 12/40 = 0.3
    assert score == pytest.approx(0.3, abs=0.01)


def test_provenance_short_description():
    agent = {"metadata": {"description": "Short but >10"}}
    score = score_provenance(agent, False)
    # only 1 pt for description 10-50 chars
    assert score == pytest.approx(1 / 40, abs=0.01)


# ── Track Record ──

def test_track_record_empty():
    ugig = UgigData()
    github = GitHubData()
    assert score_track_record(ugig, github, []) == 0.0


def test_track_record_with_ugig():
    ugig = UgigData(completed_gigs=3, avg_rating=4.5)
    github = GitHubData()
    score = score_track_record(ugig, github, [])
    # 3*5=15 + 4.5*5=22.5 = 37.5 / 120 (max raw = 120 with CoinPay)
    assert score == pytest.approx(37.5 / 120, abs=0.01)


def test_track_record_with_github():
    ugig = UgigData()
    github = GitHubData(commits_90d=50, total_stars=100)
    score = score_track_record(ugig, github, [])
    # 50//10=5 pts + log2(101)*2 ≈ 13.3 → capped at 10
    assert score > 0.1


def test_track_record_with_attestations():
    ugig = UgigData()
    github = GitHubData()
    atts = [
        {"witness_id": "w1", "task": "code_review"},
        {"witness_id": "w2", "task": "testing"},
        {"witness_id": "w3", "task": "code_review"},
    ]
    score = score_track_record(ugig, github, atts)
    # 3 unique witnesses * 3 = 9 pts + 2 unique tasks * 2 = 4 pts = 13/120
    assert score == pytest.approx(13 / 120, abs=0.01)


# ── Presence ──

def test_presence_empty():
    github = GitHubData()
    platforms = PlatformVerification()
    assert score_presence(0, github, platforms) == 0.0


def test_presence_established():
    github = GitHubData(account_age_days=365, last_push_at=datetime.now(timezone.utc) - timedelta(days=10))
    platforms = PlatformVerification(total=3, verified=3, name_matches=2)
    score = score_presence(180, github, platforms)
    # 180//30=6 + 365//90=4 + 3*3=9 + 2*4=8 + 10(sustained) = 37/50
    assert score == pytest.approx(37 / 50, abs=0.01)


# ── Endorsements ──

def test_endorsements_empty():
    internal = InternalData()
    github = GitHubData()
    assert score_endorsements(internal, github) == 0.0


def test_endorsements_with_data():
    internal = InternalData(attestations_from_established=2, attestations_from_emerging=1)
    github = GitHubData(followers=50, orgs=2)
    score = score_endorsements(internal, github)
    # 2*5=10 + 1*2=2 + log2(51)≈5.67 + 2*2=4 = 21.67/34
    assert score > 0.5


def test_endorsements_negative():
    internal = InternalData(negative_attestations=3)
    github = GitHubData()
    score = score_endorsements(internal, github)
    # 0 - 30 → clamped to 0
    assert score == 0.0


# ── Decay ──

def test_decay_zero_days():
    assert freshness_decay(0) == pytest.approx(1.0, abs=0.01)


def test_decay_180_days():
    assert freshness_decay(180) == pytest.approx(0.5, abs=0.01)


def test_decay_floor():
    assert freshness_decay(1000) == 0.5


# ── Tier Assignment ──

def test_tier_unknown_low_confidence():
    assert assign_tier(90, 0.1) == "UNKNOWN"


def test_tier_trusted():
    assert assign_tier(85, 0.7) == "TRUSTED"


def test_tier_established():
    assert assign_tier(70, 0.5) == "ESTABLISHED"


def test_tier_emerging():
    assert assign_tier(40, 0.3) == "EMERGING"


def test_tier_low_score():
    assert assign_tier(10, 0.3) == "UNKNOWN"


# ── Confidence ──

def test_confidence_empty():
    assert compute_confidence({}) == 0.0


def test_confidence_full():
    signals = {k: True for k, _ in [
        ("has_public_key", 0), ("github_verified", 0), ("has_operator", 0),
        ("has_email", 0), ("has_description", 0), ("has_avatar", 0),
        ("has_ugig_data", 0), ("has_github_commits", 0), ("has_attestations", 0),
        ("agent_age_gt_30d", 0), ("github_age_gt_90d", 0), ("platforms_gt_1", 0),
        ("has_peer_attestations", 0), ("has_github_followers", 0),
    ]}
    conf = compute_confidence(signals)
    assert conf == 1.0


def test_confidence_partial():
    signals = {"has_public_key": True, "github_verified": True, "has_email": True}
    conf = compute_confidence(signals)
    # 0.08 + 0.08 + 0.04 = 0.20
    assert conf == pytest.approx(0.20, abs=0.01)


# ── Engine Integration ──

@pytest.mark.asyncio
async def test_engine_cold_start():
    """Engine returns cold start for empty agent."""
    with patch("isnad.scoring.engine_v3.fetch_github_data", new_callable=AsyncMock) as mock_gh, \
         patch("isnad.scoring.engine_v3.fetch_ugig_data") as mock_ugig, \
         patch("isnad.scoring.engine_v3.fetch_internal_data", new_callable=AsyncMock) as mock_int, \
         patch("isnad.scoring.engine_v3.verify_platforms", new_callable=AsyncMock) as mock_plat:
        mock_gh.return_value = GitHubData()
        mock_ugig.return_value = UgigData()
        mock_int.return_value = InternalData()
        mock_plat.return_value = PlatformVerification()

        engine = ScoringEngineV3(db=None)
        result = await engine.compute({"id": "test-id", "name": "test"})

        assert result.final_score == COLD_START_SCORE
        assert result.confidence == 0.0
        assert result.tier == "UNKNOWN"


@pytest.mark.asyncio
async def test_engine_with_data():
    """Engine computes reasonable score with data."""
    now = datetime.now(timezone.utc)
    with patch("isnad.scoring.engine_v3.fetch_github_data", new_callable=AsyncMock) as mock_gh, \
         patch("isnad.scoring.engine_v3.fetch_ugig_data") as mock_ugig, \
         patch("isnad.scoring.engine_v3.fetch_internal_data", new_callable=AsyncMock) as mock_int, \
         patch("isnad.scoring.engine_v3.verify_platforms", new_callable=AsyncMock) as mock_plat:
        mock_gh.return_value = GitHubData(
            username="testuser", verified=True, account_age_days=400,
            followers=30, orgs=2, commits_90d=50, total_stars=20,
            last_push_at=now - timedelta(days=5),
        )
        mock_ugig.return_value = UgigData(completed_gigs=2, avg_rating=4.0, found=True)
        mock_int.return_value = InternalData(
            attestations=[{"witness_id": "w1", "task": "review"}],
            attestations_from_established=1,
        )
        mock_plat.return_value = PlatformVerification(total=3, verified=2, name_matches=1)

        agent = {
            "id": "test-id", "name": "testuser",
            "public_key": "a" * 64,
            "contact_email": "t@t.com",
            "agent_type": "autonomous",
            "metadata": {"description": "A" * 60, "operator": "Daniel"},
            "created_at": (now - timedelta(days=200)).isoformat(),
            "platforms": '[{"name":"github","url":"https://github.com/testuser"}]',
        }
        engine = ScoringEngineV3(db=None)
        result = await engine.compute(agent)

        assert result.final_score > COLD_START_SCORE
        assert result.confidence > 0.3
        assert result.tier in ("EMERGING", "ESTABLISHED", "TRUSTED")


def test_agent_age_days():
    now = datetime.now(timezone.utc)
    agent = {"created_at": (now - timedelta(days=100)).isoformat()}
    assert _get_agent_age_days(agent) == pytest.approx(100, abs=1)


def test_agent_age_days_missing():
    assert _get_agent_age_days({}) == 0


def test_score_result_to_dict():
    r = ScoreResult(
        final_score=42, confidence=0.35, tier="EMERGING",
        provenance=DimensionResult(raw=0.5, weighted=15.0),
        track_record=DimensionResult(raw=0.3, weighted=10.5),
        presence=DimensionResult(raw=0.4, weighted=8.0),
        endorsements=DimensionResult(raw=0.2, weighted=3.0),
        decay_factor=0.95, computed_at="2026-03-04T13:00:00Z",
    )
    d = r.to_dict()
    assert d["score"] == 42
    assert d["tier"] == "EMERGING"
    assert "provenance" in d["dimensions"]
