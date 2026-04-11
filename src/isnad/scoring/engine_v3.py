"""
isnad Scoring Engine v3 — Unified model with 4 dimensions.

Score: 0-100, Confidence: 0.0-1.0, Tier: UNKNOWN/EMERGING/ESTABLISHED/TRUSTED

Master formula (v3.1 — 5 dimensions):
  raw = Provenance*0.25 + TrackRecord*0.30 + Presence*0.20 + Endorsements*0.15 + InfraIntegrity*0.10
  final = round(raw * 100 * decay)
"""

from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from isnad.scoring.confidence import compute_confidence
from isnad.scoring.collectors.github_collector_v3 import GitHubData, fetch_github_data
from isnad.scoring.collectors.ugig_collector import UgigData, fetch_ugig_data
from isnad.scoring.collectors.internal_collector import InternalData, fetch_internal_data
from isnad.scoring.collectors.platform_verifier import PlatformVerification, verify_platforms
from isnad.scoring.collectors.coinpay_collector import CoinPayData, fetch_coinpay_reputation

logger = logging.getLogger(__name__)

# Constants
COLD_START_SCORE = 15
COLD_START_CONFIDENCE = 0.05
MAX_DAILY_INCREASE = 10
KNOWN_AGENT_TYPES = {"autonomous", "semi-autonomous", "tool", "oracle", "tool-calling", "human-supervised"}


@dataclass
class DimensionResult:
    raw: float = 0.0
    weighted: float = 0.0


@dataclass
class ScoreResult:
    final_score: int = COLD_START_SCORE
    confidence: float = COLD_START_CONFIDENCE
    tier: str = "UNKNOWN"
    provenance: DimensionResult = field(default_factory=DimensionResult)
    track_record: DimensionResult = field(default_factory=DimensionResult)
    presence: DimensionResult = field(default_factory=DimensionResult)
    endorsements: DimensionResult = field(default_factory=DimensionResult)
    infra_integrity: DimensionResult = field(default_factory=DimensionResult)
    decay_factor: float = 1.0
    computed_at: str = ""
    data_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.final_score,
            "confidence": self.confidence,
            "tier": self.tier,
            "dimensions": {
                "provenance": {"raw": round(self.provenance.raw, 4), "weighted": round(self.provenance.weighted, 2)},
                "track_record": {"raw": round(self.track_record.raw, 4), "weighted": round(self.track_record.weighted, 2)},
                "presence": {"raw": round(self.presence.raw, 4), "weighted": round(self.presence.weighted, 2)},
                "endorsements": {"raw": round(self.endorsements.raw, 4), "weighted": round(self.endorsements.weighted, 2)},
                "infra_integrity": {"raw": round(self.infra_integrity.raw, 4), "weighted": round(self.infra_integrity.weighted, 2)},
            },
            "decay_factor": round(self.decay_factor, 4),
            "computed_at": self.computed_at,
        }


def score_provenance(agent: dict, github_verified: bool) -> float:
    """Provenance dimension: 0.0-1.0. Max raw = 40."""
    pts = 0
    pk = agent.get("public_key", "")
    if pk and len(pk) == 64:
        pts += 10
    if github_verified:
        pts += 8
    meta = agent.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    operator = meta.get("operator", "")
    if operator and len(operator) > 3:
        pts += 5
    if agent.get("contact_email"):
        pts += 4
    desc = meta.get("description", "")
    if desc and len(desc) > 50:
        pts += 3
    elif desc and len(desc) > 10:
        pts += 1
    if agent.get("agent_type") in KNOWN_AGENT_TYPES:
        pts += 2
    avatar = agent.get("avatar_url", "") or ""
    if avatar.startswith("http"):
        pts += 1
    return min(pts / 40, 1.0)


def score_track_record(
    ugig: UgigData,
    github: GitHubData,
    attestations: list[dict],
    coinpay: CoinPayData | None = None,
) -> float:
    """Track Record dimension: 0.0-1.0. Max raw = 120 (scaled to 1.0)."""
    pts = 0
    # ugig gigs
    completed = max(ugig.completed_gigs, 0)
    pts += min(completed * 5, 25)
    # ugig rating (only count if agent has completed at least 1 gig)
    if completed > 0 and ugig.avg_rating > 0:
        pts += min(ugig.avg_rating * 5, 25)
    # GitHub commits (90d)
    pts += min(github.commits_90d // 10, 10)
    # GitHub stars
    pts += min(math.log2(github.total_stars + 1) * 2, 10)
    # Attestations from unique witnesses
    unique_witnesses = {a.get("witness_id") for a in attestations if a.get("witness_id")}
    pts += min(len(unique_witnesses) * 3, 15)
    # Task diversity
    unique_tasks = {a.get("task", "") for a in attestations if a.get("task")}
    pts += min(len(unique_tasks) * 2, 10)

    # CoinPay DID reputation (up to 20 pts bonus)
    if coinpay and coinpay.found:
        # Score contribution: coinpay score is 0-5, map to 0-8 pts
        pts += min(coinpay.score * 1.6, 8)
        # Task completion volume: log-scaled, up to 5 pts
        pts += min(math.log2(coinpay.total_tasks + 1) * 1.5, 5)
        # Success rate bonus: high success rate = up to 4 pts
        pts += coinpay.success_rate * 4
        # Diversity (unique counterparties): up to 3 pts
        pts += min(math.log2(coinpay.unique_buyers + 1), 3)
        # Anomaly/compliance penalties from trust vector
        tv = coinpay.trust_vector
        if tv.anomaly < 0:
            pts += tv.anomaly * 2  # negative penalty
        if tv.compliance < 0:
            pts += tv.compliance * 2  # negative penalty

    # Guard against NaN from bad upstream data
    if math.isnan(pts) or math.isinf(pts):
        pts = 0

    return min(pts / 120, 1.0)


def score_presence(
    agent_age_days: int,
    github: GitHubData,
    platforms: PlatformVerification,
) -> float:
    """Presence dimension: 0.0-1.0. Max raw = 50."""
    pts = 0
    pts += min(agent_age_days // 30, 12)
    pts += min(github.account_age_days // 90, 8)
    pts += min(platforms.verified * 3, 12)
    pts += min(platforms.name_matches * 4, 8)
    # Activity regularity
    github_sustained = (
        github.account_age_days > 180
        and github.last_push_at is not None
        and (datetime.now(timezone.utc) - github.last_push_at).days < 90
    )
    github_recent = (
        github.last_push_at is not None
        and (datetime.now(timezone.utc) - github.last_push_at).days < 90
    )
    if github_sustained:
        pts += 10
    elif github_recent:
        pts += 5
    return min(pts / 50, 1.0)


def score_endorsements(
    internal: InternalData,
    github: GitHubData,
) -> float:
    """Endorsements dimension: 0.0-1.0. Max raw = 34."""
    pts = 0
    pts += min(internal.attestations_from_established * 5, 15)
    pts += min(internal.attestations_from_emerging * 2, 6)
    pts += min(math.log2(github.followers + 1), 7)
    pts += min(github.orgs * 2, 6)
    pts -= internal.negative_attestations * 10
    return max(min(pts / 34, 1.0), 0.0)


def score_infra_integrity(agent: dict) -> float:
    """Infrastructure Integrity dimension: 0.0-1.0. Max raw = 30.
    Measures TEE attestation, build reproducibility, runtime environment."""
    pts = 0
    meta = agent.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    # TEE type declared
    tee = (meta.get("tee_type", "") or "").lower()
    if tee in ("nitro", "tdx", "sev-snp", "sevsnp", "sgx"):
        pts += 10
    elif tee and tee != "none":
        pts += 3
    # Attestation hash present
    if meta.get("attestation_hash"):
        pts += 8
    # Build hash present (reproducible builds)
    if meta.get("build_hash"):
        pts += 5
    # Runtime declared (container, bare-metal, cloud)
    runtime = (meta.get("runtime_env", "") or "").lower()
    if runtime:
        pts += 3
    # Measurements match transparency log
    if meta.get("measurements_match"):
        pts += 4
    return min(pts / 30, 1.0)


def freshness_decay(days_since_last_activity: int) -> float:
    """Half-life 180 days, floor 0.5."""
    return max(0.5, math.exp(-0.693 * days_since_last_activity / 180))


def assign_tier(score: int, confidence: float) -> str:
    """Assign tier based on score and confidence."""
    if confidence < 0.2:
        return "UNKNOWN"
    if score > 80 and confidence >= 0.6:
        return "TRUSTED"
    if score > 60 and confidence >= 0.4:
        return "ESTABLISHED"
    if score > 20 and confidence >= 0.2:
        return "EMERGING"
    return "UNKNOWN"


def _get_agent_age_days(agent: dict) -> int:
    """Calculate agent age in days from created_at."""
    created = agent.get("created_at", "")
    if not created:
        return 0
    try:
        if isinstance(created, datetime):
            dt = created
        else:
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 0


def _get_last_activity_days(agent: dict, github: GitHubData, attestations: list[dict]) -> int:
    """Determine days since last activity."""
    now = datetime.now(timezone.utc)
    latest = None

    # GitHub last push
    if github.last_push_at:
        latest = github.last_push_at

    # Last attestation
    for a in attestations:
        ts = a.get("timestamp", "")
        if ts:
            try:
                if isinstance(ts, datetime):
                    dt = ts
                else:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if latest is None or dt > latest:
                    latest = dt
            except Exception:
                pass

    if latest is None:
        return 365  # no activity → max decay
    return max(0, (now - latest).days)


def _build_confidence_signals(
    agent: dict, github: GitHubData, ugig: UgigData,
    internal: InternalData, platforms: PlatformVerification,
    agent_age_days: int, coinpay: CoinPayData | None = None,
) -> dict[str, bool]:
    """Build confidence signal dict."""
    meta = agent.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return {
        "has_public_key": bool(agent.get("public_key") and len(agent.get("public_key", "")) == 64),
        "github_verified": github.verified,
        "has_operator": bool(meta.get("operator") and len(meta.get("operator", "")) > 3),
        "has_email": bool(agent.get("contact_email")),
        "has_description": bool(meta.get("description") and len(meta.get("description", "")) > 10),
        "has_avatar": bool((agent.get("avatar_url") or "").startswith("http")),
        "has_ugig_data": ugig.found,
        "has_github_commits": github.commits_90d > 0,
        "has_attestations": len(internal.attestations) > 0,
        "agent_age_gt_30d": agent_age_days > 30,
        "github_age_gt_90d": github.account_age_days > 90,
        "platforms_gt_1": platforms.verified > 1,
        "has_peer_attestations": (internal.attestations_from_established + internal.attestations_from_emerging) > 0,
        "has_github_followers": github.followers > 0,
        "has_coinpay_did": coinpay.found if coinpay else False,
        "has_tee_attestation": bool((agent.get("metadata") or {}).get("tee_type") if isinstance(agent.get("metadata"), dict) else False),
    }


class ScoringEngineV3:
    """Main scoring engine v3."""

    def __init__(self, db=None):
        self.db = db

    async def compute(self, agent: dict) -> ScoreResult:
        """Compute v3 score for an agent."""
        now = datetime.now(timezone.utc)
        result = ScoreResult(computed_at=now.isoformat() + "Z")

        agent_id = agent.get("id", "")
        agent_name = agent.get("name", "")

        # Parse platforms
        platforms_raw = agent.get("platforms", "[]")
        if isinstance(platforms_raw, str):
            try:
                platforms_list = json.loads(platforms_raw)
            except Exception:
                platforms_list = []
        else:
            platforms_list = platforms_raw if isinstance(platforms_raw, list) else []

        # Extract GitHub username from platforms or metadata
        github_username = ""
        for p in platforms_list:
            pname = (p.get("name", "") or "").lower()
            purl = p.get("url", "") or ""
            if "github" in pname or "github.com" in purl:
                # Extract username from URL: github.com/{user} or github.com/{user}/{repo}
                parts = [x for x in purl.replace("https://", "").replace("http://", "").split("/") if x]
                # parts[0] = "github.com", parts[1] = username, parts[2] = repo (optional)
                if len(parts) >= 2:
                    github_username = parts[1]
                break

        # Extract CoinPay DID from platforms or metadata
        coinpay_did = ""
        for p in platforms_list:
            pname = (p.get("name", "") or "").lower()
            purl = p.get("url", "") or ""
            if "coinpay" in pname or "coinpayportal" in purl:
                # DID might be in url or a "did" field
                coinpay_did = p.get("did", "") or p.get("identifier", "") or ""
                if not coinpay_did and "did:" in purl:
                    coinpay_did = purl
                break
        metadata = agent.get("metadata") or {}
        if not coinpay_did and isinstance(metadata, dict):
            coinpay_did = metadata.get("coinpay_did", "") or metadata.get("did", "") or ""

        # Collect data
        github = await fetch_github_data(github_username)
        ugig = fetch_ugig_data(agent_name)
        internal = await fetch_internal_data(self.db, agent_id)
        platform_verification = await verify_platforms(platforms_list, agent_name)
        coinpay = await fetch_coinpay_reputation(coinpay_did)

        agent_age_days = _get_agent_age_days(agent)

        # Score dimensions
        prov = score_provenance(agent, github.verified)
        track = score_track_record(ugig, github, internal.attestations, coinpay)
        pres = score_presence(agent_age_days, github, platform_verification)
        endorse = score_endorsements(internal, github)
        infra = score_infra_integrity(agent)

        result.provenance = DimensionResult(raw=prov, weighted=prov * 25)
        result.track_record = DimensionResult(raw=track, weighted=track * 30)
        result.presence = DimensionResult(raw=pres, weighted=pres * 20)
        result.endorsements = DimensionResult(raw=endorse, weighted=endorse * 15)
        result.infra_integrity = DimensionResult(raw=infra, weighted=infra * 10)

        raw_score = (prov * 0.25 + track * 0.30 + pres * 0.20 + endorse * 0.15 + infra * 0.10) * 100

        # Decay
        days_inactive = _get_last_activity_days(agent, github, internal.attestations)
        decay = freshness_decay(days_inactive)
        result.decay_factor = decay

        final = round(raw_score * decay)
        final = max(final, COLD_START_SCORE)  # floor

        # Rate limit (if we have old score)
        old_score = agent.get("trust_score", 0)
        if old_score and isinstance(old_score, (int, float)) and old_score > 0:
            if final > old_score + MAX_DAILY_INCREASE:
                final = int(old_score + MAX_DAILY_INCREASE)

        result.final_score = min(final, 100)

        # Confidence
        signals = _build_confidence_signals(agent, github, ugig, internal, platform_verification, agent_age_days, coinpay)
        result.confidence = compute_confidence(signals)

        # Tier
        result.tier = assign_tier(result.final_score, result.confidence)

        # Data snapshot for audit
        result.data_snapshot = {
            "github": {"username": github.username, "verified": github.verified, "followers": github.followers,
                       "orgs": github.orgs, "commits_90d": github.commits_90d, "stars": github.total_stars,
                       "age_days": github.account_age_days},
            "ugig": {"found": ugig.found, "completed": ugig.completed_gigs, "rating": ugig.avg_rating},
            "internal": {"attestations": len(internal.attestations),
                         "from_established": internal.attestations_from_established,
                         "from_emerging": internal.attestations_from_emerging,
                         "negative": internal.negative_attestations},
            "platforms": {"total": platform_verification.total, "verified": platform_verification.verified,
                          "name_matches": platform_verification.name_matches},
            "coinpay": {"found": coinpay.found, "did": coinpay.did, "score": coinpay.score,
                        "total_tasks": coinpay.total_tasks, "success_rate": coinpay.success_rate,
                        "unique_buyers": coinpay.unique_buyers,
                        "trust_vector": {"E": coinpay.trust_vector.economic, "P": coinpay.trust_vector.productivity,
                                         "B": coinpay.trust_vector.behavioral, "D": coinpay.trust_vector.diversity,
                                         "R": coinpay.trust_vector.recency, "A": coinpay.trust_vector.anomaly,
                                         "C": coinpay.trust_vector.compliance} if coinpay.found else None},
            "infra": {"score": infra, "tee_type": (agent.get("metadata") or {}).get("tee_type") if isinstance(agent.get("metadata"), dict) else None},
            "agent_age_days": agent_age_days,
            "days_inactive": days_inactive,
            "confidence_signals": signals,
        }

        return result

    async def compute_and_store(self, agent: dict) -> ScoreResult:
        """Compute score and update DB."""
        result = await self.compute(agent)
        agent_id = agent.get("id", "")

        if self.db and agent_id:
            try:
                await self.db.update_agent(
                    agent_id,
                    trust_score=result.final_score,
                    trust_confidence=result.confidence,
                    trust_tier=result.tier,
                    last_scored_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.warning("Failed to update agent score: %s", e)

            # Audit trail
            try:
                async with self.db._pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO score_audit
                           (agent_id, final_score, confidence, tier,
                            provenance_raw, track_record_raw, presence_raw, endorsements_raw,
                            decay_factor, data_snapshot)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                        agent_id, result.final_score, result.confidence, result.tier,
                        result.provenance.raw, result.track_record.raw,
                        result.presence.raw, result.endorsements.raw,
                        result.decay_factor, json.dumps(result.data_snapshot),
                    )
            except Exception as e:
                logger.warning("Failed to write score audit: %s", e)

        return result
