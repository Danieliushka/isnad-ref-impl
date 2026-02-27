"""Tests for the real scoring engine."""

import pytest
from scoring.engine import ScoringEngine, ScoreBreakdown, freshness_multiplier, score_to_tier
from scoring.github_collector import GitHubData, extract_github_username
from datetime import datetime, timezone, timedelta


# ── Freshness ──

def test_freshness_at_zero():
    assert freshness_multiplier(0) == pytest.approx(1.0, abs=0.01)

def test_freshness_at_half_life():
    assert freshness_multiplier(180) == pytest.approx(0.5, abs=0.02)

def test_freshness_floor():
    assert freshness_multiplier(10000) == 0.5


# ── Tiers ──

def test_tier_trusted():
    assert score_to_tier(85) == "TRUSTED"

def test_tier_verified():
    assert score_to_tier(65) == "VERIFIED"

def test_tier_basic():
    assert score_to_tier(45) == "BASIC"

def test_tier_unverified():
    assert score_to_tier(25) == "UNVERIFIED"

def test_tier_unknown():
    assert score_to_tier(10) == "UNKNOWN"


# ── GitHub username extraction ──

def test_extract_github_simple():
    platforms = [{"name": "github", "url": "https://github.com/octocat"}]
    assert extract_github_username(platforms) == "octocat"

def test_extract_github_with_repo():
    platforms = [{"name": "github", "url": "https://github.com/octocat/repo"}]
    assert extract_github_username(platforms) == "octocat"

def test_extract_github_apps():
    platforms = [{"name": "github", "url": "https://github.com/apps/mybot"}]
    assert extract_github_username(platforms) == "mybot"

def test_extract_github_none():
    platforms = [{"name": "twitter", "url": "https://x.com/test"}]
    assert extract_github_username(platforms) is None

def test_extract_github_empty_url():
    platforms = [{"name": "github", "url": ""}]
    assert extract_github_username(platforms) is None


# ── Scoring Engine ──

@pytest.fixture
def engine():
    return ScoringEngine()

@pytest.fixture
def base_agent():
    return {
        "id": "test-agent-1",
        "name": "TestAgent",
        "public_key": "a" * 64,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        "platforms": [{"name": "github", "url": "https://github.com/test"}],
        "capabilities": ["code", "review"],
        "metadata": '{"description": "A test agent for testing purposes"}',
        "agent_type": "autonomous",
        "contact_email": "test@example.com",
        "avatar_url": "https://example.com/avatar.png",
    }

@pytest.fixture
def github_data():
    return GitHubData(
        username="test",
        account_created=datetime.now(timezone.utc) - timedelta(days=400),
        public_repos=15,
        followers=25,
        total_stars=50,
        last_push=datetime.now(timezone.utc) - timedelta(days=2),
        has_email=True,
        orgs_count=2,
    )


def test_engine_computes_score(engine, base_agent):
    result = engine.compute(base_agent, [])
    assert 0 <= result.total_score <= 100
    assert len(result.categories) == 5
    assert result.tier in ("TRUSTED", "VERIFIED", "BASIC", "UNVERIFIED", "UNKNOWN")


def test_engine_with_github(engine, base_agent, github_data):
    result = engine.compute(base_agent, [], github_data)
    assert result.total_score > 0
    assert result.github_data is not None
    assert result.github_data["public_repos"] == 15


def test_engine_identity_category(engine, base_agent):
    result = engine.compute(base_agent, [])
    identity = next(c for c in result.categories if c.name == "identity")
    assert identity.raw_score > 0
    assert identity.max_points == 25


def test_engine_with_attestations(engine, base_agent):
    attestations = [
        {"witness_id": "w1", "task": "code-review"},
        {"witness_id": "w2", "task": "deployment"},
        {"witness_id": "w3", "task": "code-review"},
    ]
    result = engine.compute(base_agent, attestations)
    reputation = next(c for c in result.categories if c.name == "reputation")
    assert reputation.details["attestation_count"] == 3
    assert reputation.details["unique_witnesses"] == 3


def test_engine_empty_agent(engine):
    agent = {"id": "x", "name": "", "public_key": "", "platforms": "[]", "metadata": "{}"}
    result = engine.compute(agent, [])
    assert result.total_score >= 0


def test_engine_weights_sum_to_one(engine):
    assert sum(engine.WEIGHTS.values()) == pytest.approx(1.0)


def test_github_data_to_dict(github_data):
    d = github_data.to_dict()
    assert d["username"] == "test"
    assert d["public_repos"] == 15
    assert d["account_age_days"] > 300


def test_engine_more_platforms_higher_score(engine):
    agent1 = {"id": "a", "name": "A", "public_key": "a" * 64, "platforms": "[]", "metadata": "{}"}
    agent2 = {"id": "b", "name": "B", "public_key": "b" * 64,
              "platforms": [{"name": "github", "url": "https://github.com/x"},
                           {"name": "ugig", "url": "https://ugig.net/u/x"},
                           {"name": "twitter", "url": "https://x.com/x"}],
              "metadata": "{}"}
    r1 = engine.compute(agent1, [])
    r2 = engine.compute(agent2, [])
    assert r2.total_score > r1.total_score
