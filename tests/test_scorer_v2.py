"""Tests for TrustScorer v2 — real platform data scoring."""

import pytest
from isnad.trustscore.platform_connectors import PlatformReputation
from isnad.trustscore.scorer_v2 import TrustScorerV2, TrustSignal


class TestTrustScorerV2:
    """Test the v2 scorer with mock platform data."""

    def test_empty_scorer(self):
        scorer = TrustScorerV2([])
        score = scorer.compute()
        assert 0.0 <= score <= 0.5, f"Empty scorer should be low, got {score}"
        detailed = scorer.compute_detailed()
        assert detailed["version"] == "2.0"
        assert detailed["platform_count"] == 0

    def test_single_platform_high_rating(self):
        rep = PlatformReputation(
            platform="ugig", username="testuser",
            total_jobs=10, completed_jobs=9, cancelled_jobs=1,
            average_rating=4.8, total_reviews=8,
            profile_completed=True, skills_count=5,
            has_avatar=True, has_portfolio=True,
            member_since="2025-01-01T00:00:00+00:00",
        )
        scorer = TrustScorerV2([rep])
        score = scorer.compute()
        assert 0.5 < score <= 1.0, f"High-rated agent should score >0.5, got {score}"

    def test_single_platform_low_rating(self):
        rep = PlatformReputation(
            platform="ugig", username="baduser",
            total_jobs=5, completed_jobs=2, cancelled_jobs=2, disputed_jobs=1,
            average_rating=2.0, total_reviews=3,
            profile_completed=False, skills_count=1,
        )
        scorer = TrustScorerV2([rep])
        score = scorer.compute()
        assert score < 0.5, f"Low-rated agent should score <0.5, got {score}"

    def test_multi_platform_boost(self):
        reps = [
            PlatformReputation(
                platform="ugig", username="gendolf",
                total_jobs=5, completed_jobs=5,
                average_rating=4.5, total_reviews=5,
                profile_completed=True, skills_count=10,
                has_avatar=True, has_portfolio=True,
                member_since="2026-01-01T00:00:00+00:00",
            ),
            PlatformReputation(
                platform="github", username="gendolf",
                total_jobs=20, completed_jobs=20,
                profile_completed=True, skills_count=5,
                has_avatar=True, has_portfolio=True,
                member_since="2025-06-01T00:00:00+00:00",
                raw={"total_stars": 50, "followers": 10},
            ),
        ]
        scorer = TrustScorerV2(reps)
        score = scorer.compute()
        # Multi-platform should score higher
        single_scorer = TrustScorerV2([reps[0]])
        single_score = single_scorer.compute()
        assert score >= single_score, "Multi-platform should score >= single"

    def test_detailed_output_structure(self):
        rep = PlatformReputation(
            platform="ugig", username="test",
            average_rating=4.0, total_reviews=3,
            profile_completed=True,
        )
        scorer = TrustScorerV2([rep])
        detailed = scorer.compute_detailed()

        assert "trust_score" in detailed
        assert "signals" in detailed
        assert "platforms" in detailed
        assert "data_quality" in detailed

        for signal_name in TrustScorerV2.WEIGHTS:
            assert signal_name in detailed["signals"]
            sig = detailed["signals"][signal_name]
            assert "score" in sig
            assert "weight" in sig
            assert "confidence" in sig
            assert "evidence" in sig

    def test_no_reviews_low_confidence(self):
        rep = PlatformReputation(
            platform="ugig", username="newuser",
            profile_completed=True, skills_count=5,
        )
        scorer = TrustScorerV2([rep])
        detailed = scorer.compute_detailed()
        # Platform reputation should have 0 confidence with no reviews
        rep_signal = detailed["signals"]["platform_reputation"]
        assert rep_signal["confidence"] == 0.0

    def test_dispute_penalty(self):
        clean = PlatformReputation(
            platform="ugig", username="clean",
            completed_jobs=10, cancelled_jobs=0, disputed_jobs=0,
        )
        disputed = PlatformReputation(
            platform="ugig", username="disputed",
            completed_jobs=10, cancelled_jobs=0, disputed_jobs=3,
        )
        clean_scorer = TrustScorerV2([clean])
        dirty_scorer = TrustScorerV2([disputed])

        clean_detail = clean_scorer.compute_detailed()
        dirty_detail = dirty_scorer.compute_detailed()

        clean_track = clean_detail["signals"]["delivery_track_record"]["score"]
        dirty_track = dirty_detail["signals"]["delivery_track_record"]["score"]
        assert clean_track > dirty_track, "Disputes should lower track record score"

    def test_consistent_username_bonus(self):
        same_name = [
            PlatformReputation(platform="ugig", username="gendolf"),
            PlatformReputation(platform="github", username="gendolf"),
        ]
        diff_name = [
            PlatformReputation(platform="ugig", username="gendolf"),
            PlatformReputation(platform="github", username="different"),
        ]
        same_scorer = TrustScorerV2(same_name)
        diff_scorer = TrustScorerV2(diff_name)

        same_detail = same_scorer.compute_detailed()
        diff_detail = diff_scorer.compute_detailed()

        same_cross = same_detail["signals"]["cross_platform_consistency"]
        diff_cross = diff_detail["signals"]["cross_platform_consistency"]
        assert same_cross["evidence"]["consistent_username"] is True
        assert diff_cross["evidence"]["consistent_username"] is False

    def test_weights_sum_to_one(self):
        total = sum(TrustScorerV2.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights should sum to 1.0, got {total}"

    def test_score_bounded(self):
        """Score should always be between 0 and 1."""
        # Extreme high
        rep = PlatformReputation(
            platform="ugig", username="perfect",
            total_jobs=100, completed_jobs=100,
            average_rating=5.0, total_reviews=50,
            profile_completed=True, skills_count=20,
            has_avatar=True, has_portfolio=True,
            member_since="2020-01-01T00:00:00+00:00",
        )
        scorer = TrustScorerV2([rep])
        assert 0.0 <= scorer.compute() <= 1.0

        # Extreme low
        rep2 = PlatformReputation(
            platform="ugig", username="terrible",
            total_jobs=10, completed_jobs=0, cancelled_jobs=5, disputed_jobs=5,
            average_rating=1.0, total_reviews=10,
        )
        scorer2 = TrustScorerV2([rep2])
        assert 0.0 <= scorer2.compute() <= 1.0


class TestPlatformConnectors:
    """Test connector data structures."""

    def test_platform_reputation_defaults(self):
        rep = PlatformReputation(platform="test", username="user")
        assert rep.total_jobs == 0
        assert rep.average_rating == 0.0
        assert rep.profile_completed is False
        assert rep.raw == {}

    def test_connector_registry(self):
        from isnad.trustscore.platform_connectors import CONNECTORS
        assert "ugig" in CONNECTORS
        assert "github" in CONNECTORS
        assert "moltlaunch" in CONNECTORS
        assert "clawk" in CONNECTORS
