"""Integration tests for TrustScorer v2 with mocked platform API responses.

These tests use realistic API responses captured from ugig.net and GitHub
to verify connector parsing and end-to-end scoring without hitting real APIs.
"""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from src.isnad.trustscore.platform_connectors import (
    UgigConnector,
    GitHubConnector,
    PlatformReputation,
    get_connector,
    CONNECTORS,
)
from src.isnad.trustscore.scorer_v2 import TrustScorerV2


# ── Realistic mock data (captured from real APIs 2026-02-24) ──

UGIG_PROFILE_RESPONSE = {
    "profile": {
        "id": "ea1c3e8c-ea54-4951-9f98-b6dee47a6614",
        "username": "gendolf",
        "full_name": "Gendolf 🤓",
        "avatar_url": "https://example.com/avatar.png",
        "bio": "Autonomous AI agent",
        "skills": ["Python", "Node.js", "TypeScript", "JavaScript", "Rust",
                   "Go", "Solidity", "Bash", "SQL", "API Development",
                   "Security Auditing", "QA Testing", "AI/ML", "Automation",
                   "Bot Development", "Cryptography", "Web Scraping",
                   "Data Analysis", "Technical Writing", "Smart Contracts"],
        "portfolio_urls": ["https://github.com/example/repo"],
        "profile_completed": True,
        "created_at": "2026-02-18T08:18:28.639628+00:00",
        "updated_at": "2026-02-21T16:19:53.682288+00:00",
        "average_rating": 0,
        "total_reviews": 0,
        "account_type": "agent",
    }
}

UGIG_REVIEWS_RESPONSE = {"data": [], "pagination": {"total": 0, "limit": 20, "offset": 0}}
UGIG_APPS_RESPONSE = {}  # Empty response for no applications

GITHUB_USER_RESPONSE = {
    "login": "Danieliushka",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345",
    "bio": None,
    "blog": "",
    "public_repos": 8,
    "followers": 2,
    "following": 5,
    "created_at": "2025-02-11T15:30:00Z",
    "updated_at": "2026-02-23T10:00:00Z",
}

GITHUB_REPOS_RESPONSE = [
    {"name": f"repo-{i}", "stargazers_count": 0, "forks_count": 0,
     "archived": False, "language": lang}
    for i, lang in enumerate(["Python", "Python", "TypeScript", "JavaScript",
                               "Rust", None, "Python", "Go"])
]


# ── UgigConnector Tests ──

class TestUgigConnector:

    def _mock_curl(self, responses: dict):
        """Create a mock for subprocess.run that returns different responses per URL."""
        def side_effect(cmd, **kwargs):
            url = cmd[-1] if isinstance(cmd, list) else ""
            for key, resp in responses.items():
                if key in str(url):
                    mock = MagicMock()
                    mock.stdout = json.dumps(resp)
                    return mock
            mock = MagicMock()
            mock.stdout = "{}"
            return mock
        return side_effect

    @patch("src.isnad.trustscore.platform_connectors.subprocess.run")
    def test_fetch_profile_parses_correctly(self, mock_run):
        mock_run.side_effect = self._mock_curl({
            "/api/profile": UGIG_PROFILE_RESPONSE,
            "/api/reviews": UGIG_REVIEWS_RESPONSE,
            "/api/applications": UGIG_APPS_RESPONSE,
        })

        c = UgigConnector()
        rep = c.fetch_profile("me")

        assert rep is not None
        assert rep.platform == "ugig"
        assert rep.username == "gendolf"
        assert rep.skills_count == 20
        assert rep.has_avatar is True
        assert rep.has_portfolio is True
        assert rep.profile_completed is True
        assert rep.member_since == "2026-02-18T08:18:28.639628+00:00"

    @patch("src.isnad.trustscore.platform_connectors.subprocess.run")
    def test_fetch_profile_empty_response(self, mock_run):
        mock_run.return_value = MagicMock(stdout="{}")
        c = UgigConnector()
        rep = c.fetch_profile("me")
        assert rep is None

    @patch("src.isnad.trustscore.platform_connectors.subprocess.run")
    def test_fetch_profile_invalid_json(self, mock_run):
        mock_run.side_effect = json.JSONDecodeError("", "", 0)
        c = UgigConnector()
        rep = c.fetch_profile("me")
        assert rep is None


# ── GitHubConnector Tests ──

class TestGitHubConnector:

    def _mock_request(self, responses: dict):
        def side_effect(cmd, **kwargs):
            url = cmd[2] if len(cmd) > 2 else ""
            for key, resp in responses.items():
                if key in url:
                    mock = MagicMock()
                    mock.stdout = json.dumps(resp)
                    return mock
            mock = MagicMock()
            mock.stdout = "{}"
            return mock
        return side_effect

    @patch("src.isnad.trustscore.platform_connectors.subprocess.run")
    def test_fetch_profile_parses_correctly(self, mock_run):
        mock_run.side_effect = self._mock_request({
            "users/Danieliushka/repos": GITHUB_REPOS_RESPONSE,
            "users/Danieliushka": GITHUB_USER_RESPONSE,
        })

        c = GitHubConnector(token="test-token")
        rep = c.fetch_profile("Danieliushka")

        assert rep is not None
        assert rep.platform == "github"
        assert rep.username == "Danieliushka"
        assert rep.total_jobs == 8
        assert rep.completed_jobs == 8  # none archived
        assert rep.skills_count >= 3  # Python, TS, JS, Rust, Go
        assert rep.has_avatar is True
        assert rep.raw["followers"] == 2

    @patch("src.isnad.trustscore.platform_connectors.subprocess.run")
    def test_fetch_profile_not_found(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"message": "Not Found", "status": "404"})
        )
        c = GitHubConnector(token="test-token")
        rep = c.fetch_profile("nonexistent-user-xyz")
        assert rep is None


# ── TrustScorerV2 End-to-End Tests ──

class TestTrustScorerV2Integration:

    def _make_ugig_rep(self) -> PlatformReputation:
        return PlatformReputation(
            platform="ugig", username="gendolf",
            total_jobs=0, completed_jobs=0,
            average_rating=0.0, total_reviews=0,
            profile_completed=True, skills_count=20,
            has_avatar=True, has_portfolio=True,
            member_since="2026-02-18T08:18:28.639628+00:00",
            last_active="2026-02-21T16:19:53.682288+00:00",
            raw={"id": "test"},
        )

    def _make_github_rep(self) -> PlatformReputation:
        return PlatformReputation(
            platform="github", username="Danieliushka",
            total_jobs=8, completed_jobs=8,
            average_rating=0.0, total_reviews=0,
            profile_completed=False, skills_count=5,
            has_avatar=True, has_portfolio=False,
            member_since="2025-02-11T15:30:00Z",
            raw={"followers": 2, "total_stars": 0, "total_forks": 0, "public_repos": 8},
        )

    def test_compute_two_platforms(self):
        reps = [self._make_ugig_rep(), self._make_github_rep()]
        scorer = TrustScorerV2(reps)
        score = scorer.compute()
        assert 0.0 < score < 1.0

    def test_compute_detailed_structure(self):
        reps = [self._make_ugig_rep(), self._make_github_rep()]
        scorer = TrustScorerV2(reps)
        result = scorer.compute_detailed()

        assert "trust_score" in result
        assert result["version"] == "2.0"
        assert result["platform_count"] == 2
        assert "platform_reputation" in result["signals"]
        assert "delivery_track_record" in result["signals"]
        assert "identity_verification" in result["signals"]
        assert "cross_platform_consistency" in result["signals"]

        for sig in result["signals"].values():
            assert 0.0 <= sig["score"] <= 1.0
            assert 0.0 <= sig["confidence"] <= 1.0

    def test_compute_empty(self):
        scorer = TrustScorerV2([])
        # With no data, delivery_track_record returns 0.5 with low confidence
        # so the score is non-zero but very low
        assert scorer.compute() <= 0.5

    def test_compute_single_platform(self):
        scorer = TrustScorerV2([self._make_ugig_rep()])
        score = scorer.compute()
        assert 0.0 < score < 1.0

    def test_from_platforms_with_mocked_connectors(self):
        ugig_rep = self._make_ugig_rep()
        github_rep = self._make_github_rep()

        with patch.object(UgigConnector, 'fetch_profile', return_value=ugig_rep), \
             patch.object(GitHubConnector, 'fetch_profile', return_value=github_rep):
            scorer = TrustScorerV2.from_platforms({
                "ugig": "gendolf",
                "github": "Danieliushka",
            })
            assert len(scorer.reputations) == 2
            score = scorer.compute()
            assert 0.0 < score < 1.0

    def test_high_reputation_scores_higher(self):
        """Agent with reviews and completions should score higher than empty profile."""
        empty = TrustScorerV2([self._make_ugig_rep()])

        good_rep = PlatformReputation(
            platform="ugig", username="star-agent",
            total_jobs=20, completed_jobs=19, cancelled_jobs=1,
            average_rating=4.8, total_reviews=15,
            profile_completed=True, skills_count=10,
            has_avatar=True, has_portfolio=True,
            member_since="2025-01-01T00:00:00Z",
            raw={"id": "star"},
        )
        good = TrustScorerV2([good_rep])

        assert good.compute() > empty.compute()


# ── Registry Tests ──

class TestConnectorRegistry:

    def test_get_known_connector(self):
        c = get_connector("ugig")
        assert isinstance(c, UgigConnector)

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            get_connector("nonexistent")

    def test_all_connectors_registered(self):
        assert "ugig" in CONNECTORS
        assert "github" in CONNECTORS
        assert "moltlaunch" in CONNECTORS
        assert "clawk" in CONNECTORS
