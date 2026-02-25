"""Tests for PlatformTrustCalculator — HONEST scoring."""

import json
import pytest
from datetime import datetime, timezone, timedelta

from isnad.trustscore.scorer_v2 import PlatformTrustCalculator


def _make_platform(metrics: dict, last_fetched: str | None = None,
                   raw_data: dict | None = None, platform_name: str = "test") -> dict:
    """Helper to create a platform_data row."""
    if last_fetched is None:
        last_fetched = datetime.now(timezone.utc).isoformat()
    return {
        "platform_name": platform_name,
        "platform_url": f"https://{platform_name}.example.com",
        "metrics": metrics,
        "raw_data": raw_data or {},
        "last_fetched": last_fetched,
    }


class TestEmptyData:
    """⚠️ CRITICAL: No data = LOW scores, not mid scores."""

    def test_no_platforms_all_zeros(self):
        calc = PlatformTrustCalculator([])
        report = calc.compute_report()
        assert report["overall_score"] == 0
        assert report["platform_count"] == 0
        assert report["scores"]["identity"]["score"] == 0
        assert report["scores"]["activity"]["score"] == 0
        assert report["scores"]["reputation"]["score"] == 0
        assert report["scores"]["security"]["score"] == 0

    def test_empty_metrics_low_scores(self):
        """Platform exists but has no meaningful metrics."""
        calc = PlatformTrustCalculator([_make_platform({})])
        report = calc.compute_report()
        # With empty metrics, scores should be very low
        assert report["scores"]["reputation"]["score"] == 0
        assert report["scores"]["activity"]["score"] == 0


class TestIdentityScore:
    def test_single_platform_low_confidence(self):
        """One platform = max 30 identity score (low confidence)."""
        calc = PlatformTrustCalculator([
            _make_platform({"verification_level": "basic"})
        ])
        report = calc.compute_report()
        # 1 platform = 25 base + 5 basic verification = 30
        assert report["scores"]["identity"]["score"] <= 30

    def test_multiple_platforms_higher(self):
        calc = PlatformTrustCalculator([
            _make_platform({"verification_level": "verified"}, platform_name="github"),
            _make_platform({"verification_level": "basic"}, platform_name="ugig"),
            _make_platform({"verification_level": "none"}, platform_name="other"),
        ])
        report = calc.compute_report()
        assert report["scores"]["identity"]["score"] > 50


class TestReputationScore:
    def test_no_reviews_zero_reputation(self):
        """⚠️ No reviews = reputation 0, NOT 50."""
        calc = PlatformTrustCalculator([
            _make_platform({"reputation_score": 0, "evidence_count": 0})
        ])
        report = calc.compute_report()
        assert report["scores"]["reputation"]["score"] == 0

    def test_with_evidence(self):
        calc = PlatformTrustCalculator([
            _make_platform({"reputation_score": 80, "evidence_count": 10})
        ])
        report = calc.compute_report()
        assert report["scores"]["reputation"]["score"] == 80


class TestActivityScore:
    def test_inactive_zero(self):
        calc = PlatformTrustCalculator([
            _make_platform({"activity_score": 0})
        ])
        report = calc.compute_report()
        assert report["scores"]["activity"]["score"] == 0

    def test_active(self):
        calc = PlatformTrustCalculator([
            _make_platform({"activity_score": 70}),
            _make_platform({"activity_score": 90}),
        ])
        report = calc.compute_report()
        assert report["scores"]["activity"]["score"] == 80


class TestTrustDecay:
    def test_recent_data_no_decay(self):
        """Fresh data = no significant decay."""
        now = datetime.now(timezone.utc).isoformat()
        calc = PlatformTrustCalculator([
            _make_platform({"activity_score": 80, "reputation_score": 80,
                           "evidence_count": 5}, last_fetched=now)
        ])
        report = calc.compute_report()
        assert report["decay_factor"] > 0.95

    def test_old_data_decays(self):
        """Data 30 days old = ~50% decay."""
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        calc = PlatformTrustCalculator([
            _make_platform({"activity_score": 80, "reputation_score": 80,
                           "evidence_count": 5}, last_fetched=old)
        ])
        report = calc.compute_report()
        assert 0.4 < report["decay_factor"] < 0.6

    def test_very_old_data_near_zero(self):
        """Data 90 days old = very low trust."""
        old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        calc = PlatformTrustCalculator([
            _make_platform({"activity_score": 100, "reputation_score": 100,
                           "evidence_count": 50}, last_fetched=old)
        ])
        report = calc.compute_report()
        assert report["decay_factor"] < 0.15
        assert report["overall_score"] < 20


class TestJsonStringMetrics:
    """Metrics stored as JSON strings should still work."""

    def test_metrics_as_json_string(self):
        calc = PlatformTrustCalculator([{
            "platform_name": "test",
            "platform_url": "https://test.com",
            "metrics": json.dumps({"activity_score": 50, "reputation_score": 60, "evidence_count": 3}),
            "raw_data": "{}",
            "last_fetched": datetime.now(timezone.utc).isoformat(),
        }])
        report = calc.compute_report()
        assert report["scores"]["activity"]["score"] == 50
