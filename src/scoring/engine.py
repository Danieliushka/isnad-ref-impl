"""
Real Scoring Engine — 5-category weighted trust scoring.

Categories (from research):
  Identity    25%  — verified platforms, keys, email, cross-platform consistency
  Activity    20%  — GitHub activity, account age, last activity
  Reputation  25%  — attestations, ratings, peer endorsements  
  Security    15%  — wallet age, key strength, audit presence
  Consistency 15%  — cross-platform name/avatar match, activity regularity

Score = Σ(category_weight × normalized_category_score) × freshness_multiplier
Range: 0-100
"""

from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .github_collector import GitHubData

logger = logging.getLogger(__name__)

# Half-life for freshness decay (180 days)
HALF_LIFE_DAYS = 180


def freshness_multiplier(days_since: int) -> float:
    """Exponential decay with 180-day half-life, floor at 0.5."""
    decay = math.exp(-0.693 * days_since / HALF_LIFE_DAYS)
    return max(0.5, decay)


def score_to_tier(score: float) -> str:
    if score >= 80:
        return "TRUSTED"
    if score >= 60:
        return "VERIFIED"
    if score >= 40:
        return "BASIC"
    if score >= 20:
        return "UNVERIFIED"
    return "UNKNOWN"


def tier_emoji(tier: str) -> str:
    return {"TRUSTED": "🟢", "VERIFIED": "🔵", "BASIC": "🟡", "UNVERIFIED": "🟠", "UNKNOWN": "🔴"}.get(tier, "⚪")


@dataclass
class CategoryScore:
    name: str
    raw_score: float  # 0-max_points
    max_points: float
    normalized: float  # 0-100
    weighted: float  # after applying category weight
    details: dict = field(default_factory=dict)


@dataclass
class ScoreBreakdown:
    total_score: float  # 0-100
    tier: str
    categories: list[CategoryScore]
    computed_at: str
    github_data: Optional[dict] = None


class ScoringEngine:
    """Compute trust score from agent data."""

    WEIGHTS = {
        "identity": 0.25,
        "activity": 0.20,
        "reputation": 0.25,
        "security": 0.15,
        "consistency": 0.15,
    }

    MAX_POINTS = {
        "identity": 25,
        "activity": 20,
        "reputation": 25,
        "security": 15,
        "consistency": 15,
    }

    def compute(
        self,
        agent: dict,
        attestations: list[dict],
        github: Optional[GitHubData] = None,
        platform_data: Optional[list[dict]] = None,
    ) -> ScoreBreakdown:
        """Compute full score breakdown for an agent."""
        platforms = _parse_json(agent.get("platforms", "[]"), [])
        capabilities = _parse_json(agent.get("capabilities", "[]"), [])
        metadata = _parse_json(agent.get("metadata", "{}"), {})
        created_at = _parse_dt(agent.get("created_at", ""))

        cats = []
        total = 0.0

        # 1. Identity (25 max)
        identity_score, identity_details = self._score_identity(
            agent, platforms, capabilities, metadata
        )
        cat = self._make_category("identity", identity_score, identity_details)
        cats.append(cat)
        total += cat.weighted

        # 2. Activity (20 max)
        activity_score, activity_details = self._score_activity(
            github, created_at, platforms
        )
        cat = self._make_category("activity", activity_score, activity_details)
        cats.append(cat)
        total += cat.weighted

        # 3. Reputation (25 max)
        rep_score, rep_details = self._score_reputation(attestations, github)
        cat = self._make_category("reputation", rep_score, rep_details)
        cats.append(cat)
        total += cat.weighted

        # 4. Security (15 max)
        sec_score, sec_details = self._score_security(agent, platforms)
        cat = self._make_category("security", sec_score, sec_details)
        cats.append(cat)
        total += cat.weighted

        # 5. Consistency (15 max)
        con_score, con_details = self._score_consistency(agent, platforms, github)
        cat = self._make_category("consistency", con_score, con_details)
        cats.append(cat)
        total += cat.weighted

        # Apply freshness decay based on last_checked
        last_checked = agent.get("last_checked")
        if last_checked:
            lc_dt = _parse_dt(last_checked)
            if lc_dt:
                days = (datetime.now(timezone.utc) - lc_dt).days
                fm = freshness_multiplier(days)
                total *= fm

        total = round(min(max(total, 0), 100), 1)

        return ScoreBreakdown(
            total_score=total,
            tier=score_to_tier(total),
            categories=cats,
            computed_at=datetime.now(timezone.utc).isoformat() + "Z",
            github_data=github.to_dict() if github else None,
        )

    def _make_category(self, name: str, raw: float, details: dict) -> CategoryScore:
        max_pts = self.MAX_POINTS[name]
        raw = min(raw, max_pts)
        normalized = (raw / max_pts) * 100 if max_pts > 0 else 0
        weighted = normalized * self.WEIGHTS[name]
        return CategoryScore(
            name=name,
            raw_score=round(raw, 2),
            max_points=max_pts,
            normalized=round(normalized, 1),
            weighted=round(weighted, 2),
            details=details,
        )

    # ── Identity (25 pts max) ──

    def _score_identity(self, agent: dict, platforms: list, capabilities: list, metadata: dict) -> tuple[float, dict]:
        score = 0.0
        details = {}

        # Ed25519 key present (3 pts)
        pk = agent.get("public_key", "")
        if pk and len(pk) == 64:  # hex-encoded Ed25519 = 64 chars
            score += 3
            details["ed25519_key"] = True
        else:
            details["ed25519_key"] = False

        # GitHub linked (5 pts based on account age)
        gh_platform = any(p.get("name", "").lower() == "github" for p in platforms)
        if gh_platform:
            score += 2  # linked
            details["github_linked"] = True
        else:
            details["github_linked"] = False

        # Email present (3 pts)
        email = agent.get("contact_email") or metadata.get("contact_email")
        if email:
            score += 3
            details["email"] = True
        else:
            details["email"] = False

        # Platform count (3 pts, +1 per verified platform, max 3)
        platform_count = len(platforms)
        platform_pts = min(platform_count, 3)
        score += platform_pts
        details["platform_count"] = platform_count

        # Capabilities declared (2 pts)
        if capabilities:
            score += min(len(capabilities), 2)
            details["capabilities_count"] = len(capabilities)

        # Agent type identified (2 pts)
        agent_type = agent.get("agent_type", "")
        if agent_type and agent_type != "autonomous":
            score += 2
            details["agent_type"] = agent_type
        elif agent_type:
            score += 1
            details["agent_type"] = agent_type

        # Operator/description present (2 pts)
        desc = metadata.get("description", "")
        if desc and len(desc) > 20:
            score += 2
            details["has_description"] = True
        elif desc:
            score += 1
            details["has_description"] = True
        else:
            details["has_description"] = False

        # Name present (3 pts)
        name = agent.get("name", "")
        if name and len(name) > 1:
            score += 3
            details["has_name"] = True

        # Avatar (2 pts)
        if agent.get("avatar_url"):
            score += 2
            details["has_avatar"] = True

        return min(score, 25), details

    # ── Activity (20 pts max) ──

    def _score_activity(self, github: Optional[GitHubData], created_at: Optional[datetime], platforms: list) -> tuple[float, dict]:
        score = 0.0
        details = {}

        # GitHub repos (5 pts)
        if github:
            repos = github.public_repos
            if repos >= 20:
                score += 5
            elif repos >= 10:
                score += 4
            elif repos >= 5:
                score += 3
            elif repos >= 1:
                score += 2
            details["github_repos"] = repos

            # GitHub last push (3 pts)
            days_since = github.days_since_last_push
            if days_since is not None:
                if days_since < 7:
                    score += 3
                elif days_since < 30:
                    score += 2
                elif days_since < 90:
                    score += 1
                details["github_days_since_push"] = days_since

            # GitHub account age (4 pts)
            age = github.account_age_days
            if age >= 730:  # 2+ years
                score += 4
            elif age >= 365:
                score += 3
            elif age >= 180:
                score += 2
            elif age >= 30:
                score += 1
            details["github_account_age_days"] = age

        # Agent registration age (4 pts)
        if created_at:
            agent_age = (datetime.now(timezone.utc) - created_at).days
            if agent_age >= 365:
                score += 4
            elif agent_age >= 90:
                score += 3
            elif agent_age >= 30:
                score += 2
            elif agent_age >= 7:
                score += 1
            details["agent_age_days"] = agent_age

        # Platform count as activity signal (4 pts)
        active_platforms = sum(1 for p in platforms if p.get("url"))
        score += min(active_platforms, 4)
        details["active_platforms"] = active_platforms

        return min(score, 20), details

    # ── Reputation (25 pts max) ──

    def _score_reputation(self, attestations: list[dict], github: Optional[GitHubData]) -> tuple[float, dict]:
        score = 0.0
        details = {}

        # Attestation count (5 pts, +1 per unique attester, max 5)
        unique_witnesses = {a.get("witness_id") for a in attestations}
        att_pts = min(len(unique_witnesses), 5)
        score += att_pts
        details["attestation_count"] = len(attestations)
        details["unique_witnesses"] = len(unique_witnesses)

        # GitHub stars (4 pts)
        if github:
            stars = github.total_stars
            if stars >= 1000:
                score += 4
            elif stars >= 100:
                score += 3
            elif stars >= 10:
                score += 2
            elif stars >= 1:
                score += 1
            details["github_stars"] = stars

            # GitHub followers (3 pts)
            followers = github.followers
            if followers >= 100:
                score += 3
            elif followers >= 20:
                score += 2
            elif followers >= 5:
                score += 1
            details["github_followers"] = followers

            # GitHub orgs (3 pts)
            if github.orgs_count >= 3:
                score += 3
            elif github.orgs_count >= 1:
                score += 2
            details["github_orgs"] = github.orgs_count

        # Attestation diversity bonus (5 pts if diverse tasks)
        tasks = {a.get("task", "") for a in attestations}
        task_pts = min(len(tasks), 5)
        score += task_pts
        details["unique_tasks"] = len(tasks)

        # No negative signals baseline (5 pts)
        score += 5
        details["negative_signals"] = 0

        return min(score, 25), details

    # ── Security (15 pts max) ──

    def _score_security(self, agent: dict, platforms: list) -> tuple[float, dict]:
        score = 0.0
        details = {}

        # Ed25519 key strength (4 pts)
        pk = agent.get("public_key", "")
        if pk and len(pk) == 64:
            score += 4
            details["key_type"] = "Ed25519"
            details["key_strength"] = "strong"
        elif pk:
            score += 2
            details["key_type"] = "unknown"
            details["key_strength"] = "medium"

        # Has ugig platform (3 pts — marketplace trust)
        has_ugig = any(p.get("name", "").lower() == "ugig" for p in platforms)
        if has_ugig:
            score += 3
            details["marketplace_presence"] = True

        # Multiple platforms = harder to fake (3 pts)
        if len(platforms) >= 3:
            score += 3
        elif len(platforms) >= 2:
            score += 2
        elif len(platforms) >= 1:
            score += 1
        details["platform_diversity"] = len(platforms)

        # No known vulnerabilities baseline (5 pts)
        score += 5
        details["no_known_issues"] = True

        return min(score, 15), details

    # ── Consistency (15 pts max) ──

    def _score_consistency(self, agent: dict, platforms: list, github: Optional[GitHubData]) -> tuple[float, dict]:
        score = 0.0
        details = {}

        # Cross-platform name consistency (5 pts)
        agent_name = (agent.get("name") or "").lower().strip()
        if agent_name:
            matching = 0
            for p in platforms:
                url = (p.get("url") or "").lower()
                name = (p.get("name") or "").lower()
                # Check if agent name appears in platform URL
                if agent_name.replace(" ", "").replace("-", "") in url.replace("-", "").replace("_", ""):
                    matching += 1
            if matching >= 3:
                score += 5
            elif matching >= 2:
                score += 3
            elif matching >= 1:
                score += 2
            details["name_matches"] = matching

        # Account ages consistency (3 pts)
        if github and github.account_age_days:
            created_at = _parse_dt(agent.get("created_at", ""))
            if created_at:
                agent_age = (datetime.now(timezone.utc) - created_at).days
                # GitHub should be older than isnad registration
                if github.account_age_days >= agent_age:
                    score += 3
                    details["age_consistent"] = True
                else:
                    score += 1
                    details["age_consistent"] = False

        # Activity patterns (4 pts)
        if github:
            # Has recent AND old activity = consistent
            if github.account_age_days > 180 and github.days_since_last_push is not None and github.days_since_last_push < 90:
                score += 4
                details["activity_pattern"] = "sustained"
            elif github.days_since_last_push is not None and github.days_since_last_push < 30:
                score += 2
                details["activity_pattern"] = "recent"
            else:
                details["activity_pattern"] = "sporadic"

        # Platform URL validity (3 pts)
        valid_urls = sum(1 for p in platforms if p.get("url") and p["url"].startswith("http"))
        if valid_urls >= 3:
            score += 3
        elif valid_urls >= 2:
            score += 2
        elif valid_urls >= 1:
            score += 1
        details["valid_urls"] = valid_urls

        return min(score, 15), details


def _parse_json(val, default):
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def _parse_dt(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        if s.tzinfo is None:
            return s.replace(tzinfo=timezone.utc)
        return s
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
