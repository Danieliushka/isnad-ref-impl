"""Tests for the daily trust score recalculation script."""

import math
import pytest
from scripts.recalculate_scores import compute_trust_score


class TestComputeTrustScore:
    """Unit tests for compute_trust_score matching api_v1 logic."""

    def test_zero_everything(self):
        score = compute_trust_score(0, 0, 0, False, False)
        assert score == 0

    def test_max_attestations(self):
        score = compute_trust_score(100, 0, 0, False, False)
        # attestation score capped at 100, weight 0.30 → 30
        assert score == 30

    def test_max_diversity(self):
        score = compute_trust_score(0, 100, 0, False, False)
        # diversity score capped at 100, weight 0.25 → 25
        assert score == 25

    def test_max_age(self):
        score = compute_trust_score(0, 0, 365, False, False)
        # age score = 100, weight 0.25 → 25
        assert score == 25

    def test_max_age_over_year(self):
        score = compute_trust_score(0, 0, 730, False, False)
        # capped at 100 → 25
        assert score == 25

    def test_verified_only(self):
        score = compute_trust_score(0, 0, 0, True, False)
        # verification_score = 40, weight 0.20 → 8
        assert score == 8

    def test_certified_only(self):
        score = compute_trust_score(0, 0, 0, False, True)
        # verification_score = 60, weight 0.20 → 12
        assert score == 12

    def test_both_verified_and_certified(self):
        score = compute_trust_score(0, 0, 0, True, True)
        # verification_score = 100, weight 0.20 → 20
        assert score == 20

    def test_full_score(self):
        score = compute_trust_score(100, 100, 365, True, True)
        assert score == 100

    def test_realistic_new_agent(self):
        # New agent: 2 attestations, 1 witness, 7 days old, not verified
        score = compute_trust_score(2, 1, 7, False, False)
        assert 0 < score < 30

    def test_realistic_established_agent(self):
        # Established: 8 attestations, 4 witnesses, 180 days, verified
        score = compute_trust_score(8, 4, 180, True, False)
        assert 30 < score <= 70

    def test_score_increases_with_attestations(self):
        s1 = compute_trust_score(1, 1, 30, False, False)
        s5 = compute_trust_score(5, 1, 30, False, False)
        s10 = compute_trust_score(10, 1, 30, False, False)
        assert s1 < s5 < s10

    def test_score_increases_with_diversity(self):
        s1 = compute_trust_score(5, 1, 30, False, False)
        s3 = compute_trust_score(5, 3, 30, False, False)
        assert s1 < s3

    def test_score_always_in_range(self):
        """Score must always be 0-100."""
        test_cases = [
            (0, 0, 0, False, False),
            (1000, 1000, 10000, True, True),
            (1, 1, 1, False, False),
        ]
        for args in test_cases:
            score = compute_trust_score(*args)
            assert 0 <= score <= 100, f"Score {score} out of range for {args}"
