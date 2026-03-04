"""Confidence computation for scoring v3."""

from __future__ import annotations


CONFIDENCE_CHECKS = [
    # Provenance signals
    ("has_public_key", 0.08),
    ("github_verified", 0.08),
    ("has_operator", 0.05),
    ("has_email", 0.04),
    ("has_description", 0.03),
    ("has_avatar", 0.02),
    # Track Record signals
    ("has_ugig_data", 0.15),
    ("has_github_commits", 0.10),
    ("has_attestations", 0.10),
    # Presence signals
    ("agent_age_gt_30d", 0.08),
    ("github_age_gt_90d", 0.07),
    ("platforms_gt_1", 0.05),
    # Endorsements
    ("has_peer_attestations", 0.08),
    ("has_github_followers", 0.07),
]


def compute_confidence(signals: dict[str, bool]) -> float:
    """Compute confidence score (0.0-1.0) from present data signals."""
    total = sum(weight for signal, weight in CONFIDENCE_CHECKS if signals.get(signal))
    return round(min(total, 1.0), 2)
