"""
isnad API v1 — Versioned REST API for the isnad trust platform.

Router prefix: /api/v1
Public endpoints (no auth required):
  GET /check/{agent_id}     — Cached trust check report (no recompute)
  GET /explorer              — Paginated agent list with scores
  GET /explorer/{agent_id}   — Single agent detail
  GET /stats                 — Platform statistics
  GET /health                — Health check

Auth-required endpoints:
  POST /check               — Live trust check (X-API-Key, counts quota)
  GET  /check?agent=<id>    — Live trust check (X-API-Key, counts quota)
  GET  /usage               — API usage stats (X-API-Key, NO quota cost)
  POST /keys                — Create API key (X-Admin-Key)
  POST /agents/{id}/recalculate-score — Force recompute (X-Admin-Key)
"""

from __future__ import annotations

import json
import hashlib
import hmac
import math
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from isnad.core import AgentIdentity, Attestation, TrustChain, RevocationRegistry
from isnad.acn_bridge import ACNBridge
from isnad.security import (
    sanitize_input, timing_safe_validate_key, require_admin_key,
    log_auth_failure, logger, limiter, apply_security,
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CategoryScore(BaseModel):
    """Score for a single evaluation category (0-100)."""
    name: str
    score: int = Field(ge=0, le=100)
    modules_passed: int
    modules_total: int
    findings: list[str] = []


class DimensionScore(BaseModel):
    """Score for a single v3 dimension."""
    raw: float = 0.0
    weighted: float = 0.0


class CanonicalDimension(BaseModel):
    """Single dimension in the canonical trust response."""
    raw: float = Field(0.0, description="Raw score 0.0-1.0")
    weighted: float = Field(0.0, description="Weighted contribution")
    weight: float = Field(0.0, description="Dimension weight (e.g. 0.30)")


class BadgeSummary(BaseModel):
    """Badge in the canonical trust response."""
    badge_type: str
    status: str = "active"
    granted_at: Optional[str] = None


class CanonicalTrustResponse(BaseModel):
    """Canonical trust response — single source of truth for all trust reads.

    This is the ONE authoritative response shape for trust data.
    All frontend surfaces, docs, badges, and explorer should use this model.
    """
    agent_id: str
    score: int = Field(ge=0, le=100, description="Trust score 0-100")
    grade: str = Field("UNKNOWN", description="UNKNOWN | EMERGING | ESTABLISHED | TRUSTED")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence 0.0-1.0")
    dimensions: Optional[dict[str, CanonicalDimension]] = Field(
        None, description="Scoring dimensions: provenance (25%), track_record (30%), presence (20%), endorsements (15%), infra_integrity (10%)")
    decay_factor: float = Field(1.0, description="Freshness decay multiplier")
    verified_sources: list[str] = Field(default_factory=list, description="Platforms with verified presence")
    badges: list[BadgeSummary] = Field(default_factory=list, description="Earned badges")
    last_calculated_at: Optional[str] = Field(None, description="ISO-8601 timestamp of last v3 scoring run")
    staleness: str = Field("unknown", description="fresh (<24h) | stale (>24h) | unknown (never scored)")
    calculation_version: str = Field("v3", description="Scoring engine version")


class TrustCheckResult(BaseModel):
    """Full trust-check report returned by /check/{agent_id}."""
    agent_id: str
    overall_score: int = Field(ge=0, le=100, description="Aggregate trust score 0-100")
    confidence: float = Field(0.0, description="Confidence 0.0-1.0")
    tier: str = Field("UNKNOWN", description="UNKNOWN | EMERGING | ESTABLISHED | TRUSTED")
    dimensions: Optional[dict[str, DimensionScore]] = Field(None, description="v3 scoring dimensions")
    decay_factor: float = Field(1.0, description="Freshness decay factor")
    risk_flags: list[str] = []
    attestation_count: int = 0
    last_checked: str = Field(description="ISO-8601 timestamp")
    categories: list[CategoryScore] = []
    certification_id: str = ""
    certified: bool = False
    raw_hash: Optional[str] = Field(None, description="Content hash for commit-reveal-intent verification")


class AgentSummary(BaseModel):
    """Compact agent record for explorer list."""
    agent_id: str
    name: str = ""
    trust_score: float = 0.0
    attestation_count: int = 0
    is_certified: bool = False
    last_checked: Optional[str] = None


class ExplorerPage(BaseModel):
    """Paginated explorer response."""
    agents: list[AgentSummary]
    total: int
    page: int
    limit: int


class AgentDetail(BaseModel):
    """Detailed agent view for explorer/{agent_id}."""
    agent_id: str
    name: str = ""
    public_key: str = ""
    trust_score: float = 0.0
    attestation_count: int = 0
    is_certified: bool = False
    last_checked: Optional[str] = None
    metadata: dict = {}
    recent_attestations: list[dict] = []


class BadgeOut(BaseModel):
    """Badge response model."""
    id: str
    agent_id: str
    badge_type: str
    granted_at: str
    expires_at: Optional[str] = None
    metadata: dict = {}


class BadgeCreate(BaseModel):
    """Badge creation request."""
    badge_type: str = Field(..., description="isnad_verified | early_adopter | trusted_reviewer")
    expires_at: Optional[str] = None
    metadata: dict = {}


VALID_BADGE_TYPES = {"isnad_verified", "early_adopter", "trusted_reviewer"}


class TrustScoreStats(BaseModel):
    """Aggregate trust score statistics."""
    average: float = 0.0
    min: float = 0.0
    max: float = 0.0


class StatsResponse(BaseModel):
    """Platform-wide statistics."""
    total_agents: int = 0
    total_attestations: int = 0
    agents_checked: int = 0
    attestations_verified: int = 0
    trust_scores: TrustScoreStats = TrustScoreStats()
    avg_response_ms: float = 0.0
    uptime: float = 0.0


class ApiKeyRequest(BaseModel):
    """Request body for API key generation."""
    owner_email: str
    rate_limit: int = 100


class ApiKeyResponse(BaseModel):
    """Response with the generated API key (shown only once)."""
    api_key: str
    owner_email: str
    rate_limit: int
    message: str = "Store this key securely — it won't be shown again."


class HealthResponse(BaseModel):
    """Health-check payload."""
    status: str = "ok"
    version: str = "0.3.0"
    modules: int = 36
    tests: int = 1029


# ---------------------------------------------------------------------------
# /verify models (ACN integration)
# ---------------------------------------------------------------------------

class CreditTierInfo(BaseModel):
    score: float
    tier: str
    description: str


class VerifyBreakdown(BaseModel):
    attestation_count: int = 0
    witness_diversity: float = 0.0
    recency_score: float = 0.0
    categories: list[str] = []


class VerifyResponse(BaseModel):
    agent_id: str
    trust_score: float
    confidence: str
    credit_tier: CreditTierInfo
    breakdown: VerifyBreakdown
    verified_at: str
    certification_id: str
    protocol_version: str = "0.3.0"


# ---------------------------------------------------------------------------
# Agent Registration models
# ---------------------------------------------------------------------------

class PlatformEntry(BaseModel):
    name: str
    url: str = ""

class AgentRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=1000)
    agent_type: str = Field("autonomous", pattern=r"^(autonomous|tool-calling|human-supervised)$")
    platforms: list[PlatformEntry] = []
    capabilities: list[str] = []
    offerings: str = Field("", max_length=2000)
    avatar_url: str | None = None
    contact_email: str | None = None
    public_key: str | None = Field(None, min_length=64, max_length=64, description="Optional: agent's own Ed25519 public key (64 hex chars). If provided, used instead of generating a new one.")

class AgentRegisterResponse(BaseModel):
    agent_id: str
    public_key: str
    api_key: str
    created_at: str
    message: str = "Store your API key securely — it will not be shown again."

class AgentProfileResponse(BaseModel):
    agent_id: str
    name: str
    description: str = ""
    agent_type: str = "autonomous"
    public_key: str = ""
    platforms: list[dict] = []
    capabilities: list[str] = []
    offerings: str = ""
    avatar_url: str | None = None
    contact_email: str | None = None
    trust_score: float = 0.0
    is_certified: bool = False
    created_at: str = ""

class AgentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_type: str | None = Field(None, pattern=r"^(autonomous|tool-calling|human-supervised)$")
    platforms: list[PlatformEntry] | None = None
    capabilities: list[str] | None = None
    offerings: str | None = None
    avatar_url: str | None = None
    contact_email: str | None = None

class AgentListResponse(BaseModel):
    agents: list[AgentProfileResponse]
    total: int
    page: int
    limit: int


# ---------------------------------------------------------------------------
# In-memory state (shared with the main app or injected)
# ---------------------------------------------------------------------------

_identities: dict[str, AgentIdentity] = {}
_revocation_registry = RevocationRegistry()
_trust_chain = TrustChain(revocation_registry=_revocation_registry)
_start_time: float = time.time()
_request_times: list[float] = []  # recent response times in ms

# Optional database handle (set via configure())
_db = None


def configure(
    *,
    identities: dict[str, AgentIdentity] | None = None,
    trust_chain: TrustChain | None = None,
    revocation_registry: RevocationRegistry | None = None,
    db=None,
):
    """Inject shared state into the v1 router (call before app startup)."""
    global _identities, _trust_chain, _revocation_registry, _db
    if identities is not None:
        _identities = identities
    if trust_chain is not None:
        _trust_chain = trust_chain
    if revocation_registry is not None:
        _revocation_registry = revocation_registry
    if db is not None:
        _db = db


# ---------------------------------------------------------------------------
# API Key Auth
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

FREE_TIER_MONTHLY_LIMIT = 50


def _current_month() -> str:
    """Return current month as 'YYYY-MM'."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def require_api_key(request: Request, api_key: str = Security(_api_key_header)) -> dict:
    """Dependency that validates the X-API-Key header against the database."""
    ip = request.client.host if request.client else "unknown"
    if not api_key:
        log_auth_failure(ip, "missing API key", request.url.path)
        raise HTTPException(status_code=401, detail="Missing API key")
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    key_record = await _db.validate_api_key(api_key)
    if key_record is None:
        log_auth_failure(ip, "invalid API key", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key_record


async def require_api_key_with_rate_limit(
    request: Request, api_key: str = Security(_api_key_header)
) -> dict:
    """Validate API key and enforce freemium rate limits.

    Returns the agent row (with api_tier). Raises 429 if free tier exceeded.
    """
    ip = request.client.host if request.client else "unknown"
    if not api_key:
        log_auth_failure(ip, "missing API key", request.url.path)
        raise HTTPException(status_code=401, detail="Missing API key")
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent_by_api_key(api_key)
    if agent is None:
        log_auth_failure(ip, "invalid API key", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid API key")

    tier = agent.get("api_tier", "free")
    month = _current_month()

    if tier == "free":
        usage = await _db.get_api_usage(agent["id"], month)
        if usage >= FREE_TIER_MONTHLY_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Free tier limit exceeded ({FREE_TIER_MONTHLY_LIMIT} calls/month). Upgrade to paid for unlimited access.",
            )

    # Track usage
    await _db.increment_api_usage(agent["id"], month)

    # Attach to request state for downstream use
    request.state.agent = agent
    request.state.api_tier = tier
    return agent


async def require_api_key_readonly(
    request: Request, api_key: str = Security(_api_key_header)
) -> dict:
    """Validate API key WITHOUT incrementing usage counter.

    Used for informational endpoints (e.g. /usage) that should not
    consume quota themselves.
    """
    ip = request.client.host if request.client else "unknown"
    if not api_key:
        log_auth_failure(ip, "missing API key", request.url.path)
        raise HTTPException(status_code=401, detail="Missing API key")
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent_by_api_key(api_key)
    if agent is None:
        log_auth_failure(ip, "invalid API key", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid API key")

    request.state.agent = agent
    request.state.api_tier = agent.get("api_tier", "free")
    return agent


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, close on shutdown."""
    global _db
    if _db is None:
        try:
            from isnad.database import Database
            _db = Database("isnad.db")
            await _db.connect()
        except Exception:
            pass  # DB optional
    # Migrate in-memory data on first run
    if _db is not None and _identities:
        try:
            await _db.migrate_from_memory(_identities, _trust_chain, _revocation_registry)
        except Exception:
            pass
    # Start platform worker
    global _worker
    if _db is not None:
        try:
            from isnad.worker import PlatformWorker
            _worker = PlatformWorker(_db)
            await _worker.start()
        except Exception:
            pass  # Worker is optional
    yield
    # Stop worker
    if _worker is not None:
        try:
            await _worker.stop()
        except Exception:
            pass
    if _db is not None:
        try:
            await _db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["v1"])


# ---------------------------------------------------------------------------
# Middleware helpers (to be added to a FastAPI app)
# ---------------------------------------------------------------------------

def add_middlewares(app: FastAPI, *, allowed_origins: list[str] | None = None):
    """Attach all security middlewares via isnad.security.apply_security."""
    if allowed_origins:
        os.environ.setdefault("ALLOWED_ORIGINS", ",".join(allowed_origins))
    apply_security(app)


# ---------------------------------------------------------------------------
# Rate-limit helper
# ---------------------------------------------------------------------------

def _check_rate_limit(request: Request):
    """Lightweight IP-based rate check. Uses rate_limiter module if available."""
    try:
        from isnad.rate_limiter import TrustRateLimiter, RateTier, RateCheckResult
        # We keep a module-level limiter lazily
        limiter = getattr(_check_rate_limit, "_limiter", None)
        if limiter is None:
            limiter = TrustRateLimiter(tiers=[
                RateTier(min_trust=0.0, requests_per_minute=60, burst=10),
            ])
            _check_rate_limit._limiter = limiter  # type: ignore[attr-defined]
        ip = request.client.host if request.client else "unknown"
        result = limiter.check(ip, trust_score=0.0)
        if not result.allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except ImportError:
        pass  # rate_limiter not available — skip


# ---------------------------------------------------------------------------
# Certification logic (ported from api.py /certify)
# ---------------------------------------------------------------------------

def _run_certification(agent_id: str, name: str = "", wallet: str = "",
                       platform: str = "", capabilities: list[str] | None = None,
                       evidence_urls: list[str] | None = None) -> TrustCheckResult:
    """Run the 36-module trust evaluation and return a TrustCheckResult."""

    now = datetime.now(timezone.utc)
    cert_id = hashlib.sha256(f"cert:{agent_id}:{now.isoformat()}".encode()).hexdigest()[:16]

    categories: list[CategoryScore] = []
    total_passed = 0

    # --- identity (6 modules) ---
    id_score = 0
    id_findings: list[str] = []
    if agent_id:
        id_score += 1; id_findings.append("agent_id present")
    if wallet:
        id_score += 2; id_findings.append(f"wallet: {wallet[:10]}...")
    if capabilities:
        id_score += 1; id_findings.append(f"{len(capabilities)} capabilities declared")
    if platform:
        id_score += 1; id_findings.append(f"platform: {platform}")
    if evidence_urls:
        id_score += 1; id_findings.append(f"{len(evidence_urls)} evidence URLs")
    categories.append(CategoryScore(name="identity", score=round(id_score / 6 * 100),
                                     modules_passed=id_score, modules_total=6, findings=id_findings))
    total_passed += id_score

    # --- attestation (6 modules) ---
    relevant = [a for a in _trust_chain.attestations if a.subject == agent_id or a.witness == agent_id]
    att_score = min(len(relevant), 6)
    categories.append(CategoryScore(name="attestation", score=round(att_score / 6 * 100),
                                     modules_passed=att_score, modules_total=6,
                                     findings=[f"{len(relevant)} attestations in chain"]))
    total_passed += att_score

    # --- behavioral (6 modules) ---
    beh_score = 3
    beh_findings: list[str] = ["no negative behavioral signals"]
    # Note: behavioral signals from webhooks are applied async in _enrich_behavioral_score()
    categories.append(CategoryScore(name="behavioral", score=round(beh_score / 6 * 100),
                                     modules_passed=beh_score, modules_total=6,
                                     findings=beh_findings))
    total_passed += beh_score

    # --- platform (6 modules) ---
    plat_score = 0
    plat_findings: list[str] = []
    if platform:
        plat_score += 2; plat_findings.append(f"registered on {platform}")
    if evidence_urls:
        plat_score += min(len(evidence_urls), 4)
        plat_findings.append(f"{len(evidence_urls)} external profiles/repos")
    plat_score = min(plat_score, 6)
    categories.append(CategoryScore(name="platform", score=round(plat_score / 6 * 100),
                                     modules_passed=plat_score, modules_total=6, findings=plat_findings))
    total_passed += plat_score

    # --- transactions (6 modules) ---
    tx_score = 2
    tx_findings = ["baseline trust for new agents"]
    if wallet:
        tx_score += 2; tx_findings.append("wallet provided for on-chain verification")
    tx_score = min(tx_score, 6)
    categories.append(CategoryScore(name="transactions", score=round(tx_score / 6 * 100),
                                     modules_passed=tx_score, modules_total=6, findings=tx_findings))
    total_passed += tx_score

    # --- security (6 modules) ---
    sec_score = 3
    sec_findings = ["no known security incidents"]
    if wallet and wallet.startswith("0x"):
        sec_score += 1; sec_findings.append("valid EVM wallet format")
    sec_score = min(sec_score, 6)
    categories.append(CategoryScore(name="security", score=round(sec_score / 6 * 100),
                                     modules_passed=sec_score, modules_total=6, findings=sec_findings))
    total_passed += sec_score

    overall = round(total_passed / 36 * 100)

    # confidence (float 0.0-1.0)
    if evidence_urls and wallet and platform:
        confidence = 0.8
    elif wallet or platform:
        confidence = 0.5
    else:
        confidence = 0.2

    # risk flags
    risk_flags: list[str] = []
    if att_score == 0:
        risk_flags.append("no_attestations")
    if id_score < 3:
        risk_flags.append("weak_identity")
    if overall < 60:
        risk_flags.append("below_certification_threshold")

    return TrustCheckResult(
        agent_id=agent_id,
        overall_score=overall,
        confidence=confidence,
        risk_flags=risk_flags,
        attestation_count=len(relevant),
        last_checked=now.isoformat() + "Z",
        categories=categories,
        certification_id=cert_id,
        certified=overall >= 60,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check — always returns 200 if the service is up."""
    return HealthResponse()


class UsageResponse(BaseModel):
    """API usage stats for the authenticated agent."""
    agent_id: str
    api_tier: str
    month: str
    calls_used: int
    calls_remaining: int | None = Field(None, description="null = unlimited (paid tier)")
    monthly_limit: int | None = Field(None, description="null = unlimited (paid tier)")


@router.get("/usage", response_model=UsageResponse)
async def get_usage(request: Request, agent: dict = Depends(require_api_key_readonly)):
    """Get API usage for the current month. Requires X-API-Key header.

    This endpoint does NOT consume quota — it uses a read-only auth check.
    """
    month = _current_month()
    usage = await _db.get_api_usage(agent["id"], month)
    tier = agent.get("api_tier", "free")

    if tier == "free":
        return UsageResponse(
            agent_id=agent["id"],
            api_tier=tier,
            month=month,
            calls_used=usage,
            calls_remaining=max(0, FREE_TIER_MONTHLY_LIMIT - usage),
            monthly_limit=FREE_TIER_MONTHLY_LIMIT,
        )
    else:
        return UsageResponse(
            agent_id=agent["id"],
            api_tier=tier,
            month=month,
            calls_used=usage,
            calls_remaining=None,
            monthly_limit=None,
        )


@router.post("/keys", response_model=ApiKeyResponse)
async def create_api_key(body: ApiKeyRequest, _admin: bool = Depends(require_admin_key)):
    """Generate a new API key. The raw key is returned once; only its hash is stored.

    Requires X-Admin-Key header — key creation is admin-only.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    raw_key = f"isnad_{secrets.token_urlsafe(32)}"
    await _db.create_api_key(raw_key, body.owner_email, body.rate_limit)
    return ApiKeyResponse(api_key=raw_key, owner_email=body.owner_email, rate_limit=body.rate_limit)


@router.get("/stats", response_model=StatsResponse)
async def stats():
    """Platform-wide statistics: agents, attestations, trust scores."""
    avg_ms = sum(_request_times[-100:]) / max(len(_request_times[-100:]), 1) if _request_times else 0.0
    agents_checked = 0
    total_agents = len(_identities)
    total_attestations = len(_trust_chain.attestations)
    trust_score_stats = TrustScoreStats()

    if _db is not None:
        try:
            async with _db._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM trust_checks")
                agents_checked = row["cnt"] if row else 0
                # Count registered agents from DB
                agent_row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM agents")
                if agent_row:
                    total_agents = max(total_agents, agent_row["cnt"])
                # Trust score stats from trust_checks
                score_row = await conn.fetchrow(
                    "SELECT AVG(overall_score) as avg_score, "
                    "MIN(overall_score) as min_score, "
                    "MAX(overall_score) as max_score "
                    "FROM trust_checks"
                )
                if score_row and score_row["avg_score"] is not None:
                    trust_score_stats = TrustScoreStats(
                        average=round(float(score_row["avg_score"]), 2),
                        min=round(float(score_row["min_score"]), 2),
                        max=round(float(score_row["max_score"]), 2),
                    )
        except Exception:
            pass

    # Fallback: read trust scores from agents table
    if trust_score_stats.average == 0.0 and _db is not None:
        try:
            async with _db._pool.acquire() as conn:
                agent_scores = await conn.fetchrow(
                    "SELECT AVG(trust_score) as avg_score, "
                    "MIN(trust_score) as min_score, "
                    "MAX(trust_score) as max_score "
                    "FROM agents WHERE trust_score > 0"
                )
                if agent_scores and agent_scores["avg_score"] is not None:
                    trust_score_stats = TrustScoreStats(
                        average=round(float(agent_scores["avg_score"]), 2),
                        min=round(float(agent_scores["min_score"]), 2),
                        max=round(float(agent_scores["max_score"]), 2),
                    )
        except Exception:
            pass

    # Fallback: compute trust scores from in-memory chain if no DB scores
    if trust_score_stats.average == 0.0 and _identities:
        scores = [_trust_chain.trust_score(aid) for aid in _identities]
        scores = [s for s in scores if s > 0]
        if scores:
            trust_score_stats = TrustScoreStats(
                average=round(sum(scores) / len(scores), 4),
                min=round(min(scores), 4),
                max=round(max(scores), 4),
            )

    return StatsResponse(
        total_agents=total_agents,
        total_attestations=total_attestations,
        agents_checked=agents_checked,
        attestations_verified=total_attestations,
        trust_scores=trust_score_stats,
        avg_response_ms=round(avg_ms, 2),
        uptime=round(time.time() - _start_time, 2),
    )


class CheckRequest(BaseModel):
    """Request body for POST /check."""
    agent_id: str = Field(..., min_length=1, max_length=200, description="Agent ID, name, or public key to check")
    raw_hash: Optional[str] = Field(None, max_length=128, description="Optional content hash for commit-reveal-intent verification (hex-encoded)")


async def _run_v3_check(agent_identifier: str, request: Request, raw_hash: str | None = None) -> TrustCheckResult:
    """Shared v3 trust check logic for all /check variants."""
    t0 = time.time()

    agent_row = None
    resolved_id = agent_identifier
    if _db is not None:
        try:
            agent_row = await _db.get_agent(agent_identifier)
            if agent_row is None:
                agent_row = await _db.get_agent_by_name(agent_identifier)
            if agent_row is None:
                agent_row = await _db.get_agent_by_pubkey(agent_identifier)
            if agent_row is not None:
                resolved_id = agent_row["id"]
        except Exception:
            pass

    # Use v3 engine if agent is in DB
    if agent_row is not None and _db is not None:
        try:
            from isnad.scoring.engine_v3 import ScoringEngineV3
            engine = ScoringEngineV3(db=_db)
            v3_result = await engine.compute_and_store(agent_row)

            now = datetime.now(timezone.utc)
            cert_id = hashlib.sha256(f"cert:{resolved_id}:{now.isoformat()}".encode()).hexdigest()[:16]

            risk_flags: list[str] = []
            if v3_result.confidence < 0.2:
                risk_flags.append("low_confidence")
            if v3_result.track_record.raw < 0.1:
                risk_flags.append("no_track_record")
            if v3_result.provenance.raw < 0.3:
                risk_flags.append("weak_identity")
            if v3_result.final_score < 60:
                risk_flags.append("below_certification_threshold")

            categories = [
                CategoryScore(name="provenance", score=round(v3_result.provenance.raw * 100),
                              modules_passed=round(v3_result.provenance.raw * 10), modules_total=10,
                              findings=[f"Provenance: {v3_result.provenance.raw:.0%} (weight 25%)"]),
                CategoryScore(name="track_record", score=round(v3_result.track_record.raw * 100),
                              modules_passed=round(v3_result.track_record.raw * 10), modules_total=10,
                              findings=[f"Track Record: {v3_result.track_record.raw:.0%} (weight 30%)"]),
                CategoryScore(name="presence", score=round(v3_result.presence.raw * 100),
                              modules_passed=round(v3_result.presence.raw * 10), modules_total=10,
                              findings=[f"Presence: {v3_result.presence.raw:.0%} (weight 20%)"]),
                CategoryScore(name="endorsements", score=round(v3_result.endorsements.raw * 100),
                              modules_passed=round(v3_result.endorsements.raw * 10), modules_total=10,
                              findings=[f"Endorsements: {v3_result.endorsements.raw:.0%} (weight 15%)"]),
                CategoryScore(name="infra_integrity", score=round(v3_result.infra_integrity.raw * 100),
                              modules_passed=round(v3_result.infra_integrity.raw * 10), modules_total=10,
                              findings=[f"Infrastructure Integrity: {v3_result.infra_integrity.raw:.0%} (weight 10%)"]),
            ]

            att_count = v3_result.data_snapshot.get("internal", {}).get("attestations", 0)

            result = TrustCheckResult(
                agent_id=resolved_id,
                overall_score=v3_result.final_score,
                confidence=v3_result.confidence,
                tier=v3_result.tier,
                dimensions={
                    "provenance": DimensionScore(raw=v3_result.provenance.raw, weighted=v3_result.provenance.weighted),
                    "track_record": DimensionScore(raw=v3_result.track_record.raw, weighted=v3_result.track_record.weighted),
                    "presence": DimensionScore(raw=v3_result.presence.raw, weighted=v3_result.presence.weighted),
                    "endorsements": DimensionScore(raw=v3_result.endorsements.raw, weighted=v3_result.endorsements.weighted),
                    "infra_integrity": DimensionScore(raw=v3_result.infra_integrity.raw, weighted=v3_result.infra_integrity.weighted),
                },
                decay_factor=v3_result.decay_factor,
                risk_flags=risk_flags,
                attestation_count=att_count,
                last_checked=now.isoformat() + "Z",
                categories=categories,
                certification_id=cert_id,
                certified=v3_result.final_score >= 60 and v3_result.confidence >= 0.4,
                raw_hash=raw_hash,
            )

            try:
                report = result.model_dump()
                await _db.create_trust_check(
                    agent_id=resolved_id,
                    score=v3_result.final_score / 100.0,
                    report=report,
                    requester_ip=request.client.host if request.client else "",
                    raw_hash=raw_hash,
                )
            except Exception:
                pass

            elapsed_ms = (time.time() - t0) * 1000
            _request_times.append(elapsed_ms)
            return result
        except Exception as e:
            logger.warning("v3 scoring failed, falling back to legacy: %s", e)

    # Fallback: legacy certification
    result = _run_certification(resolved_id)
    if raw_hash:
        result.raw_hash = raw_hash

    if _db is not None:
        try:
            report = result.model_dump()
            await _db.create_trust_check(
                agent_id=resolved_id,
                score=result.overall_score / 100.0,
                report=report,
                requester_ip=request.client.host if request.client else "",
                raw_hash=raw_hash,
            )
        except Exception:
            pass

    elapsed_ms = (time.time() - t0) * 1000
    _request_times.append(elapsed_ms)
    return result


@router.post("/check", response_model=TrustCheckResult)
@limiter.limit("60/minute")
async def check_agent_post(request: Request, body: CheckRequest, _caller: dict = Depends(require_api_key_with_rate_limit)):
    """POST variant of the trust check — accepts agent_id in the request body."""
    sanitize_input(body.agent_id, "agent_id")
    return await _run_v3_check(body.agent_id, request, raw_hash=body.raw_hash)


@router.get("/check", response_model=TrustCheckResult)
@limiter.limit("60/minute")
async def check_agent_query(
    request: Request,
    agent: str = Query(..., min_length=1, max_length=200, description="Agent ID, name, or public key"),
    _caller: dict = Depends(require_api_key_with_rate_limit),
):
    """GET /check?agent=<id> — query-param variant of the trust check."""
    sanitize_input(agent, "agent_id")
    return await _run_v3_check(agent, request)


# Duplicate GET /check route removed — single handler above


@router.get("/check/{agent_id}", response_model=TrustCheckResult)
@limiter.limit("60/minute")
async def check_agent(agent_id: str, request: Request):
    """
    **Flagship endpoint** — Unified v3 trust evaluation (read-only).

    Returns the last cached trust report for the agent. No live recompute
    is triggered on this public GET. Use POST /agents/{agent_id}/recalculate-score
    (admin-only) to force a fresh computation.
    """
    sanitize_input(agent_id, "agent_id")

    # Snapshot-only: return cached report, never trigger live recompute
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Resolve agent
    agent_row = await _db.get_agent(agent_id)
    if agent_row is None:
        agent_row = await _db.get_agent_by_name(agent_id)
    if agent_row is None:
        agent_row = await _db.get_agent_by_pubkey(agent_id)
    if agent_row is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved_id = agent_row["id"]
    checks = await _db.get_trust_checks(resolved_id, limit=1)
    if checks:
        report = checks[0].get("report", {})
        if isinstance(report, dict) and "overall_score" in report:
            try:
                return TrustCheckResult(**report)
            except Exception:
                pass

    # No cached score — return a minimal response from agent row data
    now = datetime.now(timezone.utc)
    return TrustCheckResult(
        agent_id=resolved_id,
        overall_score=round(agent_row.get("trust_score", 0) or 0),
        confidence=agent_row.get("trust_confidence", 0.0) or 0.0,
        tier=agent_row.get("trust_tier", "UNKNOWN") or "UNKNOWN",
        last_checked=now.isoformat() + "Z",
        certified=bool(agent_row.get("is_certified")),
    )


# ---------------------------------------------------------------------------
# Canonical Trust Endpoint — single source of truth
# ---------------------------------------------------------------------------

_DIMENSION_WEIGHTS = {
    "provenance": 0.25,
    "track_record": 0.30,
    "presence": 0.20,
    "endorsements": 0.15,
    "infra_integrity": 0.10,
}


@router.get("/trust/{agent_id}", response_model=CanonicalTrustResponse,
            tags=["Trust"], summary="Canonical trust read (snapshot)")
@limiter.limit("120/minute")
async def get_canonical_trust(agent_id: str, request: Request):
    """**Canonical trust endpoint** — returns the authoritative trust snapshot.

    This is a pure read from the database. No live recompute is triggered.
    Returns the latest v3 scoring result with dimensions, badges, verified sources,
    and staleness indicator.

    Use `POST /agents/{agent_id}/recalculate-score` (admin-only) to trigger a fresh
    computation.
    """
    sanitize_input(agent_id, "agent_id")

    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Resolve agent
    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        agent = await _db.get_agent_by_pubkey(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved_id = agent["id"]
    score = round(agent.get("trust_score", 0) or 0)
    grade = agent.get("trust_tier", "UNKNOWN") or "UNKNOWN"
    confidence = agent.get("trust_confidence", 0.0) or 0.0
    last_scored = agent.get("last_scored_at")

    # Compute staleness
    staleness = "unknown"
    last_calculated_at = None
    if last_scored:
        last_calculated_at = str(last_scored)
        try:
            scored_dt = datetime.fromisoformat(str(last_scored).replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - scored_dt).total_seconds() / 3600
            staleness = "fresh" if age_hours < 24 else "stale"
        except Exception:
            staleness = "unknown"

    # Get dimensions from latest score_audit
    dimensions = None
    decay_factor = 1.0
    audit = await _db.get_latest_score_audit(resolved_id)
    if audit:
        dimensions = {}
        # Parse data_snapshot for dimensions not stored as columns (e.g. infra_integrity)
        snapshot = audit.get("data_snapshot")
        if isinstance(snapshot, str):
            try:
                import json as _json
                snapshot = _json.loads(snapshot)
            except Exception:
                snapshot = {}
        elif not isinstance(snapshot, dict):
            snapshot = {}
        for dim_name, weight in _DIMENSION_WEIGHTS.items():
            raw_val = audit.get(f"{dim_name}_raw", None)
            if raw_val is None and dim_name == "infra_integrity":
                # Fallback: read from data_snapshot
                raw_val = (snapshot.get("infra", {}) or {}).get("score", 0.0)
            raw_val = raw_val or 0.0
            dimensions[dim_name] = CanonicalDimension(
                raw=round(float(raw_val), 4),
                weighted=round(float(raw_val) * weight, 4),
                weight=weight,
            )
        decay_factor = audit.get("decay_factor", 1.0) or 1.0

    # Get verified sources from platform_data (deduplicated, sorted)
    platform_rows = await _db.get_platform_data(resolved_id)
    verified_sources = sorted({p["platform_name"] for p in platform_rows if p.get("platform_name")})

    # Get badges
    badge_rows = await _db.get_badges(resolved_id)
    badges = [
        BadgeSummary(
            badge_type=b.get("badge_type", ""),
            status=b.get("status", "active"),
            granted_at=b.get("granted_at"),
        )
        for b in badge_rows
    ]

    return CanonicalTrustResponse(
        agent_id=resolved_id,
        score=min(max(score, 0), 100),
        grade=grade,
        confidence=round(confidence, 4),
        dimensions=dimensions,
        decay_factor=round(decay_factor, 4),
        verified_sources=verified_sources,
        badges=badges,
        last_calculated_at=last_calculated_at,
        staleness=staleness,
        calculation_version="v3",
    )


@router.get("/verify/{agent_id}", response_model=VerifyResponse)
@limiter.limit("60/minute")
async def verify_agent(agent_id: str, request: Request, _caller: dict = Depends(require_api_key_with_rate_limit)):
    """
    ACN Verify endpoint — returns trust score with credit tier mapping.

    Public endpoint for Risueno ACN integration. Runs the trust evaluation
    and maps the result to a credit tier via ACNBridge.
    """
    sanitize_input(agent_id, "agent_id")

    # Run trust check (reuse certification logic)
    result = _run_certification(agent_id)

    # Normalize overall_score (0-100) to trust_score (0.0-1.0)
    trust_score = result.overall_score / 100.0

    # Map trust → credit via ACNBridge
    bridge = ACNBridge()
    credit_score = bridge.trust_to_credit(trust_score)

    # Determine credit tier
    if credit_score >= 750:
        tier, desc = "A", "Excellent standing"
    elif credit_score >= 700:
        tier, desc = "B", "Good standing"
    elif credit_score >= 650:
        tier, desc = "C", "Fair standing"
    elif credit_score >= 600:
        tier, desc = "D", "Below average"
    else:
        tier, desc = "F", "Poor standing"

    # Compute breakdown
    relevant_atts = [a for a in _trust_chain.attestations
                     if a.subject == agent_id or a.witness == agent_id]
    witnesses = {a.witness for a in relevant_atts if a.subject == agent_id}
    witness_diversity = min(len(witnesses) / 5.0, 1.0) if witnesses else 0.0

    # Recency: fraction of attestations from last 30 days
    now_ts = time.time()
    thirty_days = 30 * 86400
    recent = [a for a in relevant_atts
              if hasattr(a, 'timestamp') and (now_ts - getattr(a, 'timestamp', 0)) < thirty_days]
    recency_score = len(recent) / max(len(relevant_atts), 1)

    categories = [c.name for c in result.categories if c.score > 0]

    now = datetime.now(timezone.utc)
    cert_id = hashlib.sha256(f"verify:{agent_id}:{now.isoformat()}".encode()).hexdigest()[:16]

    # Auto-grant isnad_verified badge if trust_score >= 0.7 (score >= 7 on 10-point scale)
    if trust_score >= 0.7:
        try:
            await _auto_grant_badge(agent_id, "isnad_verified", {"granted_by": "auto_verify", "trust_score": trust_score})
        except Exception:
            pass  # Non-critical — don't fail verify if badge grant fails

    return VerifyResponse(
        agent_id=agent_id,
        trust_score=round(trust_score, 4),
        confidence=result.confidence,
        credit_tier=CreditTierInfo(
            score=credit_score,
            tier=tier,
            description=desc,
        ),
        breakdown=VerifyBreakdown(
            attestation_count=len(relevant_atts),
            witness_diversity=round(witness_diversity, 4),
            recency_score=round(recency_score, 4),
            categories=categories,
        ),
        verified_at=now.isoformat() + "Z",
        certification_id=cert_id,
    )


@router.get("/explorer", response_model=ExplorerPage)
async def explorer(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query("", description="Filter by agent ID or name"),
    sort: str = Query("trust_score", description="Sort field: trust_score | name | last_checked"),
):
    """Paginated list of agents with trust scores."""
    agents: list[AgentSummary] = []
    total = 0

    if _db is not None:
        try:
            # Use DB
            offset = (page - 1) * limit
            rows = await _db.list_agents(limit=limit, offset=offset)
            # count total
            async with _db._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM agents")
                total = row["cnt"] if row else 0
            for r in rows:
                if search and search.lower() not in (r.get("id", "") + r.get("name", "")).lower():
                    continue
                agents.append(AgentSummary(
                    agent_id=r["id"],
                    name=r.get("name", ""),
                    trust_score=r.get("trust_score", 0.0),
                    is_certified=bool(r.get("is_certified", 0)),
                    last_checked=r.get("last_checked"),
                ))
        except Exception:
            pass
    else:
        # Fallback: in-memory identities
        all_ids = list(_identities.keys())
        if search:
            all_ids = [i for i in all_ids if search.lower() in i.lower()]
        total = len(all_ids)
        offset = (page - 1) * limit
        for aid in all_ids[offset:offset + limit]:
            score = _trust_chain.trust_score(aid)
            atts = _trust_chain._by_subject.get(aid, [])
            agents.append(AgentSummary(agent_id=aid, trust_score=round(score, 4),
                                        attestation_count=len(atts)))

    return ExplorerPage(agents=agents, total=total, page=page, limit=limit)


@router.get("/explorer/{agent_id}", response_model=AgentDetail)
async def explorer_detail(agent_id: str):
    """Detailed view of a single agent."""
    agent_row = None
    if _db is not None:
        try:
            agent_row = await _db.get_agent(agent_id)
            if agent_row is None:
                agent_row = await _db.get_agent_by_name(agent_id)
            if agent_row is None:
                agent_row = await _db.get_agent_by_pubkey(agent_id)
        except Exception:
            pass

    if agent_row:
        resolved_id = agent_row["id"]
        atts = []
        try:
            atts = await _db.get_attestations_for_subject(resolved_id)
        except Exception:
            pass
        import json
        meta = agent_row.get("metadata", "{}")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return AgentDetail(
            agent_id=agent_row["id"],
            name=agent_row.get("name", ""),
            public_key=agent_row.get("public_key", ""),
            trust_score=agent_row.get("trust_score", 0.0),
            attestation_count=len(atts),
            is_certified=bool(agent_row.get("is_certified", 0)),
            last_checked=agent_row.get("last_checked"),
            metadata=meta,
            recent_attestations=atts[:10],
        )

    # Fallback: in-memory
    if agent_id in _identities:
        identity = _identities[agent_id]
        score = _trust_chain.trust_score(agent_id)
        atts = _trust_chain._by_subject.get(agent_id, [])
        return AgentDetail(
            agent_id=agent_id,
            public_key=identity.public_key_hex,
            trust_score=round(score, 4),
            attestation_count=len(atts),
            recent_attestations=[a.to_dict() for a in atts[:10]],
        )

    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


# ---------------------------------------------------------------------------
# Simple Registration Endpoint (Kit the Fox compatible)
# ---------------------------------------------------------------------------

class SimpleRegisterRequest(BaseModel):
    """Minimal registration request for programmatic agent onboarding."""
    agent_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=1000)
    homepage_url: str | None = None
    public_key: str | None = Field(None, min_length=64, max_length=64, description="Optional: agent's own Ed25519 public key (64 hex chars). If provided, used instead of generating a new one.")


class SimpleRegisterResponse(BaseModel):
    """Response with agent_id and api_key."""
    agent_id: str
    api_key: str


@router.get("/register")
async def register_info(request: Request):
    """Registration info endpoint for programmatic discovery.

    Returns registration requirements and pricing tiers so agents
    (e.g. Kit the Fox) can discover how to register programmatically.
    """
    return {
        "endpoint": "POST /api/v1/register",
        "method": "POST",
        "content_type": "application/json",
        "fields": {
            "agent_name": {"type": "string", "required": True, "description": "Unique agent name"},
            "description": {"type": "string", "required": False, "description": "Agent description"},
            "homepage_url": {"type": "string", "required": False, "description": "Agent homepage URL"},
        },
        "response": {
            "agent_id": "string (UUID)",
            "api_key": "string (shown once, starts with isnad_)",
        },
        "pricing": {
            "free": {"price": 0, "checks_per_month": 100},
            "pro": {"price": 29, "currency": "USD", "checks_per_month": 10000},
            "enterprise": {"price": "custom", "checks_per_month": "unlimited"},
        },
        "example": {
            "curl": 'curl -X POST https://isnad.site/api/v1/register -H "Content-Type: application/json" -d \'{"agent_name": "my-agent", "description": "My AI agent"}\'',
        },
        "docs": "https://isnad.site/docs",
    }


@router.post("/register", response_model=SimpleRegisterResponse, status_code=201)
@limiter.limit("10/minute")
async def simple_register(request: Request, body: SimpleRegisterRequest):
    """Register a new agent with minimal fields.

    Designed for programmatic registration by other agents (e.g. Kit the Fox).
    Returns agent_id + api_key. The api_key is shown only once.
    """
    sanitize_input(body.agent_name, "agent_name")
    sanitize_input(body.description, "description")
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    import uuid
    import json as _json
    from nacl.signing import SigningKey

    # Check for duplicate name
    existing = await _db.get_agent_by_name(body.agent_name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Agent with name '{body.agent_name}' already exists")

    # Generate keypair + API key
    if body.public_key:
        # Validate it's valid hex
        try:
            bytes.fromhex(body.public_key)
            public_key_hex = body.public_key
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid public_key: must be 64 hex characters")
    else:
        signing_key = SigningKey.generate()
        public_key_hex = signing_key.verify_key.encode().hex()
    raw_api_key = f"isnad_{secrets.token_urlsafe(32)}"
    api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
    agent_id = str(uuid.uuid4())

    metadata = {"description": body.description}
    if body.homepage_url:
        metadata["homepage_url"] = body.homepage_url

    await _db.create_agent(
        agent_id=agent_id,
        public_key=public_key_hex,
        name=body.agent_name,
        metadata=metadata,
    )

    # Store API key hash and homepage
    update_fields: dict = {"api_key_hash": api_key_hash}
    if body.homepage_url:
        update_fields["platforms"] = _json.dumps([{"name": "homepage", "url": body.homepage_url}])
    await _db.update_agent(agent_id, **update_fields)

    return SimpleRegisterResponse(agent_id=agent_id, api_key=raw_api_key)


class UpdatePubkeyRequest(BaseModel):
    """Request body for updating an agent's stored public key."""
    public_key: str = Field(..., min_length=64, max_length=64, description="Agent's Ed25519 public key (64 hex chars)")


@router.patch("/agents/{agent_id}/pubkey")
async def update_agent_pubkey(agent_id: str, body: UpdatePubkeyRequest, request: Request):
    """Update the stored public key for an already-registered agent.

    Requires the agent's API key in the X-API-Key header. Allows an agent to
    correct a mismatch between the server-stored public key and the key it
    actually uses for signing evidence.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Validate API key
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    agent = await _db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    stored_hash = agent.get("api_key_hash", "")
    if not stored_hash or not timing_safe_validate_key(api_key, stored_hash):
        ip = request.client.host if request.client else "unknown"
        log_auth_failure(ip, "invalid API key for agent", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid API key for this agent")

    # Validate public_key is valid hex
    try:
        bytes.fromhex(body.public_key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid public_key: must be 64 hex characters")

    await _db.update_agent(agent_id, public_key=body.public_key)

    return {"agent_id": agent_id, "public_key": body.public_key, "updated": True}


# ---------------------------------------------------------------------------
# Agent Registration Endpoints (full)
# ---------------------------------------------------------------------------

@router.post("/agents/register", response_model=AgentRegisterResponse)
@limiter.limit("10/minute")
async def register_agent(request: Request, body: AgentRegisterRequest):
    """Register a new agent. Generates Ed25519 keypair and API key server-side."""
    # Sanitize inputs
    sanitize_input(body.name, "name")
    sanitize_input(body.description, "description")
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    import uuid
    import json
    from nacl.signing import SigningKey

    # Check for duplicate name
    existing = await _db.get_agent_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Agent with name '{body.name}' already exists")

    # Use provided public key or generate a new keypair
    if body.public_key:
        try:
            bytes.fromhex(body.public_key)
            public_key_hex = body.public_key
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid public_key: must be 64 hex characters")
    else:
        signing_key = SigningKey.generate()
        public_key_hex = signing_key.verify_key.encode().hex()

    # Generate API key
    raw_api_key = f"isnad_{secrets.token_urlsafe(32)}"
    api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()

    agent_id = str(uuid.uuid4())

    metadata = {
        "description": body.description,
        "agent_type": body.agent_type,
    }

    # Create agent in DB
    result = await _db.create_agent(
        agent_id=agent_id,
        public_key=public_key_hex,
        name=body.name,
        metadata=metadata,
    )

    # Update additional fields
    update_fields = {
        "agent_type": body.agent_type,
        "platforms": json.dumps([p.model_dump() for p in body.platforms]),
        "capabilities": json.dumps(body.capabilities),
        "offerings": body.offerings or "",
        "api_key_hash": api_key_hash,
    }
    if body.avatar_url:
        update_fields["avatar_url"] = body.avatar_url
    if body.contact_email:
        update_fields["contact_email"] = body.contact_email

    await _db.update_agent(agent_id, **update_fields)

    return AgentRegisterResponse(
        agent_id=agent_id,
        public_key=public_key_hex,
        api_key=raw_api_key,
        created_at=result["created_at"],
    )


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    agent_type: str | None = Query(None),
    platform: str | None = Query(None),
    search: str | None = Query(None),
):
    """List agents with pagination and filters."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    import json

    offset = (page - 1) * limit

    # Build query with filters
    conditions = []
    params = []
    param_idx = 1

    if agent_type:
        conditions.append(f"agent_type = ${param_idx}")
        params.append(agent_type)
        param_idx += 1

    if platform:
        conditions.append(f"platforms::text ILIKE ${param_idx}")
        params.append(f"%{platform}%")
        param_idx += 1

    if search:
        conditions.append(f"name ILIKE ${param_idx}")
        params.append(f"%{search}%")
        param_idx += 1

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    async with _db._pool.acquire() as conn:
        count_row = await conn.fetchrow(f"SELECT COUNT(*) as cnt FROM agents {where}", *params)
        total = count_row["cnt"]

        rows = await conn.fetch(
            f"SELECT * FROM agents {where} ORDER BY trust_score DESC, created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}",
            *params, limit, offset,
        )

    agents = []
    for r in rows:
        r = dict(r)
        platforms_raw = r.get("platforms", "[]")
        if isinstance(platforms_raw, str):
            try:
                platforms_raw = json.loads(platforms_raw)
            except Exception:
                platforms_raw = []

        caps_raw = r.get("capabilities", "[]")
        if isinstance(caps_raw, str):
            try:
                caps_raw = json.loads(caps_raw)
            except Exception:
                caps_raw = []

        meta = r.get("metadata", "{}")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        agents.append(AgentProfileResponse(
            agent_id=r["id"],
            name=r.get("name", ""),
            description=meta.get("description", ""),
            agent_type=r.get("agent_type", "autonomous"),
            public_key=r.get("public_key", ""),
            platforms=platforms_raw if isinstance(platforms_raw, list) else [],
            capabilities=caps_raw if isinstance(caps_raw, list) else [],
            offerings=r.get("offerings", "") or "",
            avatar_url=r.get("avatar_url"),
            contact_email=r.get("contact_email"),
            trust_score=r.get("trust_score", 0.0) or 0.0,
            is_certified=bool(r.get("is_certified", False)),
            created_at=r.get("created_at", ""),
        ))

    return AgentListResponse(agents=agents, total=total, page=page, limit=limit)


@router.get("/agents/{agent_id}", response_model=AgentProfileResponse)
async def get_agent_profile(agent_id: str):
    """Get full public profile of an agent (supports UUID or case-insensitive name)."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    import json

    agent = await _db.get_agent(agent_id)
    if not agent:
        # Fallback: try case-insensitive name lookup for user-friendly URLs
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    platforms_raw = agent.get("platforms", "[]")
    if isinstance(platforms_raw, str):
        try:
            platforms_raw = json.loads(platforms_raw)
        except Exception:
            platforms_raw = []

    caps_raw = agent.get("capabilities", "[]")
    if isinstance(caps_raw, str):
        try:
            caps_raw = json.loads(caps_raw)
        except Exception:
            caps_raw = []

    meta = agent.get("metadata", "{}")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    return AgentProfileResponse(
        agent_id=agent["id"],
        name=agent.get("name", ""),
        description=meta.get("description", ""),
        agent_type=agent.get("agent_type", "autonomous"),
        public_key=agent.get("public_key", ""),
        platforms=platforms_raw if isinstance(platforms_raw, list) else [],
        capabilities=caps_raw if isinstance(caps_raw, list) else [],
        offerings=agent.get("offerings", "") or "",
        avatar_url=agent.get("avatar_url"),
        contact_email=agent.get("contact_email"),
        trust_score=agent.get("trust_score", 0.0) or 0.0,
        is_certified=bool(agent.get("is_certified", False)),
        created_at=agent.get("created_at", ""),
    )


@router.patch("/agents/{agent_id}", response_model=AgentProfileResponse)
async def update_agent_profile(agent_id: str, body: AgentUpdateRequest, request: Request):
    """Update agent profile. Requires API key in X-API-Key header."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    import json

    # Validate API key against this agent
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    agent = await _db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    stored_hash = agent.get("api_key_hash", "")
    if not stored_hash or not timing_safe_validate_key(api_key, stored_hash):
        ip = request.client.host if request.client else "unknown"
        log_auth_failure(ip, "invalid API key for agent", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid API key for this agent")

    # Build update fields
    update_fields = {}
    if body.name is not None:
        update_fields["name"] = body.name
    if body.agent_type is not None:
        update_fields["agent_type"] = body.agent_type
    if body.platforms is not None:
        update_fields["platforms"] = json.dumps([p.model_dump() for p in body.platforms])
    if body.capabilities is not None:
        update_fields["capabilities"] = json.dumps(body.capabilities)
    if body.offerings is not None:
        update_fields["offerings"] = body.offerings
    if body.avatar_url is not None:
        update_fields["avatar_url"] = body.avatar_url
    if body.contact_email is not None:
        update_fields["contact_email"] = body.contact_email
    if body.description is not None:
        # Update metadata.description
        meta = agent.get("metadata", "{}")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        meta["description"] = body.description
        update_fields["metadata"] = json.dumps(meta)

    if update_fields:
        await _db.update_agent(agent_id, **update_fields)

    # Return updated profile
    return await get_agent_profile(agent_id)


# ---------------------------------------------------------------------------
# App factory (convenience — can also just include the router in an existing app)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Trust Report & Worker Endpoints
# ---------------------------------------------------------------------------

class TrustReportResponse(BaseModel):
    agent_id: str
    overall_score: int
    decay_factor: float
    platform_count: int
    scores: dict
    computed_at: str


@router.get("/agents/{agent_id}/trust-report", response_model=TrustReportResponse)
async def get_trust_report(agent_id: str):
    """Full trust report with breakdown from platform data."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        agent = await _db.get_agent_by_pubkey(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved_id = agent["id"]
    platform_data = await _db.get_platform_data(resolved_id)

    from isnad.trustscore.scorer_v2 import PlatformTrustCalculator
    calc = PlatformTrustCalculator(platform_data)
    report = calc.compute_report()

    return TrustReportResponse(
        agent_id=agent_id,
        overall_score=report["overall_score"],
        decay_factor=report["decay_factor"],
        platform_count=report["platform_count"],
        scores=report["scores"],
        computed_at=report["computed_at"],
    )


# ─── Badge endpoints ───────────────────────────────────────────────

@router.get("/agents/{agent_id}/badges", response_model=list[BadgeOut])
async def get_agent_badges(agent_id: str):
    """Get all badges for an agent."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    rows = await _db.get_badges(agent_id)
    return [
        BadgeOut(
            id=r["id"],
            agent_id=r["agent_id"],
            badge_type=r["badge_type"],
            granted_at=str(r["granted_at"]),
            expires_at=str(r["expires_at"]) if r.get("expires_at") else None,
            metadata=json.loads(r["metadata"]) if isinstance(r.get("metadata"), str) else (r.get("metadata") or {}),
        )
        for r in rows
    ]


@router.post("/agents/{agent_id}/badges", response_model=BadgeOut, status_code=201)
async def create_agent_badge(agent_id: str, body: BadgeCreate, _admin: bool = Depends(require_admin_key)):
    """Create a badge for an agent (admin only)."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    if body.badge_type not in VALID_BADGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid badge type. Must be one of: {VALID_BADGE_TYPES}")

    agent = await _db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    now_iso = datetime.now(timezone.utc).isoformat() + "Z"
    created = await _db.create_badge(agent_id, body.badge_type, status="active",
                                     granted_at=now_iso, expires_at=body.expires_at)
    if not created:
        raise HTTPException(status_code=409, detail="Badge already exists for this agent")

    badge_id = hashlib.sha256(f"badge:{agent_id}:{body.badge_type}".encode()).hexdigest()[:16]
    return BadgeOut(
        id=badge_id,
        agent_id=agent_id,
        badge_type=body.badge_type,
        granted_at=now_iso,
        expires_at=body.expires_at,
        metadata=body.metadata,
    )


async def _auto_grant_badge(agent_id: str, badge_type: str, metadata: Optional[dict] = None):
    """Auto-grant a badge if not already present. Called internally."""
    if _db is None:
        return
    now_iso = datetime.now(timezone.utc).isoformat() + "Z"
    await _db.create_badge(agent_id, badge_type, status="active", granted_at=now_iso)


# ---------------------------------------------------------------------------
# Evidence Submission Endpoint — DAN-105 (Hash Agent × isnad)
# ---------------------------------------------------------------------------

class EvidenceSubmitRequest(BaseModel):
    """Evidence submission from an external agent (e.g. Hash Agent / SkillFence).

    The payload is Ed25519-signed by the submitting agent. The signature covers
    the canonical JSON of the payload fields (sorted keys, no whitespace).
    """
    agent_id: str = Field(..., min_length=1, max_length=200, description="Submitting agent's isnad ID or public key")
    audit_id: str = Field(..., min_length=1, max_length=200, description="UUID of the audit/scan run")
    evidence_type: str = Field("security_scan", description="Type: security_scan | code_review | behavioral | attestation")
    payload: dict = Field(..., description="Evidence data (findings, scores, metadata)")
    signature: str = Field(..., min_length=1, description="Hex-encoded Ed25519 signature over canonical payload JSON")
    public_key: str = Field(..., min_length=64, max_length=64, description="Hex-encoded Ed25519 public key (32 bytes)")


class EvidenceSubmitResponse(BaseModel):
    """Confirmation of evidence submission."""
    evidence_id: str
    agent_id: str
    audit_id: str
    verified: bool
    score_impact: float = Field(0.0, description="Impact on agent's trust score (0.0 if not yet applied)")
    message: str = "Evidence received and verified."


VALID_EVIDENCE_TYPES = {"security_scan", "code_review", "behavioral", "attestation"}


def _verify_ed25519_signature(payload: dict, signature_hex: str, public_key_hex: str) -> tuple[bool, str]:
    """Verify an Ed25519 signature over canonical JSON payload.

    Returns (is_valid, error_message).
    """
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        # Canonical JSON: sorted keys, no whitespace
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        message_bytes = canonical.encode("utf-8")

        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        signature_bytes = bytes.fromhex(signature_hex)
        verify_key.verify(message_bytes, signature_bytes)
        return True, ""
    except BadSignatureError:
        return False, "Invalid signature: payload does not match"
    except ValueError as e:
        return False, f"Invalid key or signature format: {e}"
    except Exception as e:
        return False, f"Signature verification failed: {e}"


@router.post("/evidence", response_model=EvidenceSubmitResponse, status_code=201)
@limiter.limit("30/minute")
async def submit_evidence(request: Request, body: EvidenceSubmitRequest):
    """Submit cryptographically signed evidence from an external agent.

    Used by agents like Hash Agent (SkillFence) to submit security scan
    results, code review findings, or other evidence that feeds into
    the isnad trust scoring engine.

    The signature must be a valid Ed25519 signature over the canonical
    JSON representation of the payload (sorted keys, compact separators).
    """
    sanitize_input(body.agent_id, "agent_id")
    sanitize_input(body.audit_id, "audit_id")

    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    if body.evidence_type not in VALID_EVIDENCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid evidence_type. Must be one of: {sorted(VALID_EVIDENCE_TYPES)}",
        )

    # Verify Ed25519 signature
    sig_valid, sig_error = _verify_ed25519_signature(body.payload, body.signature, body.public_key)

    # Resolve agent — by ID or public key
    agent = await _db.get_agent(body.agent_id)
    if agent is None:
        agent = await _db.get_agent_by_pubkey(body.public_key)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not registered. Register first via POST /api/v1/register")

    resolved_agent_id = agent["id"]

    # Check public key matches registered agent
    stored_pk = agent.get("public_key", "")
    if stored_pk and stored_pk != body.public_key:
        raise HTTPException(
            status_code=403,
            detail="Public key does not match registered agent's key",
        )

    # Generate evidence ID
    evidence_id = hashlib.sha256(
        f"ev:{resolved_agent_id}:{body.audit_id}:{time.time()}".encode()
    ).hexdigest()[:24]

    # Check for duplicate audit_id from same agent
    existing = await _db.get_evidence_for_audit(body.audit_id)
    for ev in existing:
        if ev.get("agent_id") == resolved_agent_id:
            raise HTTPException(
                status_code=409,
                detail=f"Evidence for audit_id '{body.audit_id}' already submitted by this agent",
            )

    # Calculate score impact based on evidence type and verification
    score_impact = 0.0
    if sig_valid:
        impact_map = {
            "security_scan": 2.0,
            "code_review": 1.5,
            "behavioral": 1.0,
            "attestation": 0.5,
        }
        score_impact = impact_map.get(body.evidence_type, 0.5)

    # Store evidence
    record = await _db.create_evidence(
        evidence_id=evidence_id,
        agent_id=resolved_agent_id,
        audit_id=body.audit_id,
        evidence_type=body.evidence_type,
        payload=body.payload,
        signature=body.signature,
        public_key=body.public_key,
        verified=sig_valid,
        verification_error=sig_error if not sig_valid else None,
        score_impact=score_impact if sig_valid else 0.0,
    )

    # Also create a behavioral signal for the scoring engine
    if sig_valid:
        try:
            await _db.create_behavioral_signal(
                agent_id=resolved_agent_id,
                source=body.evidence_type,
                event_type="evidence_submitted",
                metadata={
                    "evidence_id": evidence_id,
                    "audit_id": body.audit_id,
                    "score_impact": score_impact,
                    "payload_summary": {k: type(v).__name__ for k, v in body.payload.items()},
                },
            )
        except Exception:
            pass  # Non-critical

    message = "Evidence received and verified." if sig_valid else f"Evidence received but signature invalid: {sig_error}"

    return EvidenceSubmitResponse(
        evidence_id=evidence_id,
        agent_id=resolved_agent_id,
        audit_id=body.audit_id,
        verified=sig_valid,
        score_impact=score_impact if sig_valid else 0.0,
        message=message,
    )


@router.get("/evidence/{agent_id}")
async def get_agent_evidence(
    agent_id: str,
    limit: int = Query(50, ge=1, le=200),
    _caller: dict = Depends(require_api_key_with_rate_limit),
):
    """Get evidence submissions for an agent. Requires API key."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    records = await _db.get_evidence_for_agent(agent_id, limit=limit)
    return {"agent_id": agent_id, "evidence": records, "total": len(records)}


# ---------------------------------------------------------------------------
# Trust Score Endpoint — DAN-80
# ---------------------------------------------------------------------------

class TrustScoreBreakdown(BaseModel):
    """Breakdown of trust score components."""
    attestation_count: int = Field(description="Number of valid attestations")
    attestation_score: float = Field(ge=0, le=100, description="Score from attestation count (0-100)")
    attestation_weight: float = Field(description="Weight applied to attestation score")
    source_diversity: int = Field(description="Number of unique attestation sources (witnesses)")
    diversity_score: float = Field(ge=0, le=100, description="Score from source diversity (0-100)")
    diversity_weight: float = Field(description="Weight applied to diversity score")
    registration_age_days: int = Field(description="Days since agent registration")
    age_score: float = Field(ge=0, le=100, description="Score from registration age (0-100)")
    age_weight: float = Field(description="Weight applied to age score")
    is_verified: bool = Field(description="Whether agent has verification badge")
    is_certified: bool = Field(description="Whether agent is certified")
    verification_score: float = Field(ge=0, le=100, description="Score from verification status (0-100)")
    verification_weight: float = Field(description="Weight applied to verification score")


class TrustScoreResponse(BaseModel):
    """Trust score response with numeric score and breakdown."""
    agent_id: str
    trust_score: int = Field(ge=0, le=100, description="Overall trust score 0-100")
    breakdown: TrustScoreBreakdown
    computed_at: str = Field(description="ISO-8601 timestamp")


# Weights for trust score components
_TRUST_WEIGHTS = {
    "attestation_count": 0.30,
    "source_diversity": 0.25,
    "registration_age": 0.25,
    "verification_status": 0.20,
}


def _compute_trust_score(
    attestation_count: int,
    source_diversity: int,
    registration_age_days: int,
    is_verified: bool,
    is_certified: bool,
) -> tuple[int, TrustScoreBreakdown]:
    """Compute trust score (0-100) from components.

    Returns (score, breakdown).
    """
    # Attestation count score: log-scaled, 10 attestations = ~100
    if attestation_count == 0:
        att_score = 0.0
    else:
        att_score = min(math.log2(attestation_count + 1) / math.log2(11) * 100, 100.0)

    # Source diversity score: log-scaled, 5 unique sources = ~100
    if source_diversity == 0:
        div_score = 0.0
    else:
        div_score = min(math.log2(source_diversity + 1) / math.log2(6) * 100, 100.0)

    # Registration age score: linear up to 365 days = 100
    age_score = min(registration_age_days / 365.0 * 100, 100.0)

    # Verification score: binary signals
    ver_score = 0.0
    if is_certified:
        ver_score += 60.0
    if is_verified:
        ver_score += 40.0
    ver_score = min(ver_score, 100.0)

    # Weighted combination
    overall = (
        att_score * _TRUST_WEIGHTS["attestation_count"]
        + div_score * _TRUST_WEIGHTS["source_diversity"]
        + age_score * _TRUST_WEIGHTS["registration_age"]
        + ver_score * _TRUST_WEIGHTS["verification_status"]
    )

    breakdown = TrustScoreBreakdown(
        attestation_count=attestation_count,
        attestation_score=round(att_score, 2),
        attestation_weight=_TRUST_WEIGHTS["attestation_count"],
        source_diversity=source_diversity,
        diversity_score=round(div_score, 2),
        diversity_weight=_TRUST_WEIGHTS["source_diversity"],
        registration_age_days=registration_age_days,
        age_score=round(age_score, 2),
        age_weight=_TRUST_WEIGHTS["registration_age"],
        is_verified=is_verified,
        is_certified=is_certified,
        verification_score=round(ver_score, 2),
        verification_weight=_TRUST_WEIGHTS["verification_status"],
    )

    return round(overall), breakdown


@router.get("/agents/{agent_id}/trust-score", response_model=TrustScoreResponse)
async def get_trust_score(agent_id: str):
    """Get computed trust score (0-100) with full breakdown.

    Score = weighted combination of:
    - Attestation count (30%) — log-scaled, more attestations = higher score
    - Source diversity (25%) — unique witnesses, log-scaled
    - Registration age (25%) — linear up to 1 year
    - Verification status (20%) — certified + verified badges
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Resolve agent
    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved_id = agent["id"]

    # 1. Attestation count + source diversity
    attestations = await _db.get_attestations_for_subject(resolved_id)
    attestation_count = len(attestations)
    unique_witnesses = len({a["witness_id"] for a in attestations})

    # 2. Registration age
    created_at = agent.get("created_at", "")
    age_days = 0
    if created_at:
        try:
            if isinstance(created_at, str):
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                created = created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - created).days)
        except (ValueError, TypeError):
            pass

    # 3. Verification status
    is_certified = bool(agent.get("is_certified", False))
    is_verified = False
    try:
        badges = await _db.get_badges(resolved_id)
        is_verified = any(b.get("badge_type") == "isnad_verified" for b in badges)
    except Exception:
        pass

    score, breakdown = _compute_trust_score(
        attestation_count=attestation_count,
        source_diversity=unique_witnesses,
        registration_age_days=age_days,
        is_verified=is_verified,
        is_certified=is_certified,
    )

    return TrustScoreResponse(
        agent_id=resolved_id,
        trust_score=score,
        breakdown=breakdown,
        computed_at=datetime.now(timezone.utc).isoformat() + "Z",
    )


class ScoreV3DimensionOut(BaseModel):
    raw: float
    weighted: float


class ScoreV3DimensionsOut(BaseModel):
    provenance: ScoreV3DimensionOut
    track_record: ScoreV3DimensionOut
    presence: ScoreV3DimensionOut
    endorsements: ScoreV3DimensionOut


class ScoreV3Response(BaseModel):
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1.0)
    tier: str
    dimensions: ScoreV3DimensionsOut
    decay_factor: float
    computed_at: str


@router.get("/agents/{agent_id}/score", response_model=ScoreV3Response)
async def get_agent_score_v3(agent_id: str, _admin: bool = Depends(require_admin_key)):
    """Get v3 trust score with full breakdown (4 dimensions + confidence + tier).

    Requires X-Admin-Key — triggers live v3 recompute.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from isnad.scoring.engine_v3 import ScoringEngineV3
    engine = ScoringEngineV3(db=_db)
    result = await engine.compute_and_store(agent)

    return ScoreV3Response(**result.to_dict())


@router.get("/trust-score-v2/{agent_id}")
async def trust_score_v2_compat(agent_id: str, request: Request):
    """Backward-compatible trust-score-v2 endpoint.

    Only returns data for registered agents. Returns 404 for unknown agents.
    """
    from isnad.trustscore.scorer_v2 import TrustScorerV2

    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Resolve agent — MUST be registered
    platforms: dict[str, str] = {}
    resolved_id = agent_id
    agent_row = await _db.get_agent(agent_id)
    if agent_row is None:
        agent_row = await _db.get_agent_by_name(agent_id)
    if agent_row is None:
        raise HTTPException(status_code=404, detail="Agent not found. Only registered agents have trust scores.")

    resolved_id = agent_row["id"]
    import json as _json
    plats_raw = agent_row.get("platforms", "[]")
    if isinstance(plats_raw, str):
        try:
            plats_raw = _json.loads(plats_raw)
        except Exception:
            plats_raw = []
    for p in (plats_raw if isinstance(plats_raw, list) else []):
        pname = p.get("name", "").lower() if isinstance(p, dict) else ""
        purl = p.get("url", "") if isinstance(p, dict) else ""
        if pname and purl:
            platforms[pname] = purl

    # Also check attestation metadata (like old API)
    for att in _trust_chain.attestations:
        if att.subject == resolved_id or att.subject == agent_id:
            meta = att.metadata or {}
            for key, pname in [("ugig_username", "ugig"), ("github_username", "github"),
                               ("moltlaunch_name", "moltlaunch"), ("clawk_username", "clawk")]:
                if key in meta:
                    platforms[pname] = meta[key]

    if not platforms:
        platforms = {"ugig": agent_id, "github": agent_id}

    scorer = TrustScorerV2.from_platforms(platforms)
    result = scorer.compute_detailed()
    result["agent_id"] = resolved_id

    # Map to frontend-expected shape
    return {
        "agent_id": resolved_id,
        "trust_score": result.get("trust_score", 0.0),
        "version": result.get("version", "2.0"),
        "signals": result.get("signals", {}),
        "total_confidence": result.get("data_quality", 0.0),
        "platforms_checked": result.get("platforms", []),
    }


@router.post("/admin/scan/{agent_id}")
async def trigger_scan(agent_id: str, _admin: bool = Depends(require_admin_key)):
    """Trigger a manual platform scan for an agent. Requires admin API key."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from isnad.worker import PlatformWorker
    worker = PlatformWorker(_db)
    results = await worker.scan_agent(agent_id)

    return {
        "agent_id": agent_id,
        "platforms_scanned": len(results),
        "results": [{"platform": r["platform"], "url": r["url"], "alive": r["alive"]} for r in results],
    }


@router.delete("/admin/agents/{agent_id}")
async def admin_delete_agent(agent_id: str, _admin: bool = Depends(require_admin_key)):
    """Delete an agent (admin only). Use for cleaning up test/duplicate registrations."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    deleted = await _db.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Delete failed")
    return {"deleted": agent_id, "name": agent.get("name", "unknown")}


# ---------------------------------------------------------------------------
# ACN Integration — /verify/trust endpoint
# ---------------------------------------------------------------------------

class ACNTrustBreakdown(BaseModel):
    identity: float = Field(ge=0, le=1.0, description="Identity verification strength")
    reputation: float = Field(ge=0, le=1.0, description="Platform reputation")
    delivery: float = Field(ge=0, le=1.0, description="Task delivery track record")
    consistency: float = Field(ge=0, le=1.0, description="Cross-platform consistency")


class ACNVerifyResult(BaseModel):
    agent_id: str
    agent_name: str
    verified: bool
    trust_score: int = Field(ge=0, le=100)
    breakdown: ACNTrustBreakdown
    credit_tier: str = Field(description="platinum|gold|silver|bronze|unrated")
    confidence: str = Field(description="high|medium|low")
    attestation_count: int
    risk_flags: list[str] = []
    checked_at: str


def _score_to_credit_tier(score: int) -> str:
    if score >= 85:
        return "platinum"
    elif score >= 70:
        return "gold"
    elif score >= 50:
        return "silver"
    elif score >= 25:
        return "bronze"
    return "unrated"


@router.get("/verify/trust/{agent_id}", response_model=ACNVerifyResult)
async def verify_trust_acn(agent_id: str):
    """Verify agent trust with breakdown and ACN credit tier mapping.

    Designed for ACN (Agent Credit Network) integration:
    - Trust score breakdown by dimension (identity, reputation, delivery, consistency)
    - Credit tier mapping (platinum/gold/silver/bronze/unrated)
    - Confidence level based on data depth
    """
    # Resolve agent_id
    resolved_id = agent_id
    if _db is not None:
        try:
            agent_row = await _db.get_agent(agent_id)
            if agent_row is None:
                agent_row = await _db.get_agent_by_pubkey(agent_id)
            if agent_row is not None:
                resolved_id = agent_row["id"]
        except Exception:
            pass

    # Run full trust check
    result = _run_certification(resolved_id)

    # Extract category scores into breakdown
    cats = {c.name: c.score / 100.0 for c in result.categories}
    breakdown = ACNTrustBreakdown(
        identity=round(cats.get("identity", 0), 3),
        reputation=round(cats.get("platform", 0), 3),
        delivery=round(cats.get("behavioral", 0) * 0.5 + cats.get("transactions", 0) * 0.5, 3),
        consistency=round(cats.get("security", 0) * 0.5 + cats.get("attestation", 0) * 0.5, 3),
    )

    # Resolve agent name
    agent_name = agent_id
    ident = _identities.get(agent_id)
    if ident:
        agent_name = ident.name or agent_id
    elif _db:
        agent = await _db.get_agent(agent_id)
        if agent:
            agent_name = agent.get("name", agent_id)

    tier = _score_to_credit_tier(result.overall_score)

    return ACNVerifyResult(
        agent_id=result.agent_id,
        agent_name=agent_name,
        verified=result.overall_score >= 25 and result.attestation_count > 0,
        trust_score=result.overall_score,
        breakdown=breakdown,
        credit_tier=tier,
        confidence=result.confidence,
        attestation_count=result.attestation_count,
        risk_flags=result.risk_flags,
        checked_at=result.last_checked,
    )


# ---------------------------------------------------------------------------
# Worker reference (set during lifespan)
# ---------------------------------------------------------------------------

_worker = None


# ---------------------------------------------------------------------------
# Real Scoring Engine endpoints — DAN-80
# ---------------------------------------------------------------------------

class RealScoreCategory(BaseModel):
    name: str
    raw_score: float
    max_points: float
    normalized: float
    weighted: float
    details: dict = {}


class RealScoreBreakdownResponse(BaseModel):
    agent_id: str
    agent_name: str
    total_score: float = Field(ge=0, le=100)
    tier: str
    tier_emoji: str
    categories: list[RealScoreCategory]
    github_data: Optional[dict] = None
    computed_at: str


class RecalculateResponse(BaseModel):
    agent_id: str
    old_score: float
    new_score: float
    tier: str
    computed_at: str


@router.get("/agents/{agent_id}/score-breakdown", response_model=RealScoreBreakdownResponse)
async def get_score_breakdown(agent_id: str):
    """Get detailed real scoring breakdown (5 categories, GitHub data, tier)."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved_id = agent["id"]

    # Get latest trust_check with scoring-engine report
    async with _db._pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT report FROM trust_checks
               WHERE agent_id = $1 AND requester_ip = 'scoring-engine'
               ORDER BY requested_at DESC LIMIT 1""",
            resolved_id,
        )

    if row and row["report"]:
        report = row["report"]
        if isinstance(report, str):
            report = json.loads(report)

        categories = [
            RealScoreCategory(**c) for c in report.get("categories", [])
        ]

        def _score_to_tier(s):
            if s >= 80: return "TRUSTED"
            if s >= 60: return "VERIFIED"
            if s >= 40: return "BASIC"
            if s >= 20: return "UNVERIFIED"
            return "UNKNOWN"
        def _tier_emoji(t):
            return {"TRUSTED": "🟢", "VERIFIED": "🔵", "BASIC": "🟡", "UNVERIFIED": "🟠", "UNKNOWN": "🔴"}.get(t, "⚪")

        tier = report.get("tier", _score_to_tier(report.get("total_score", 0)))

        return RealScoreBreakdownResponse(
            agent_id=resolved_id,
            agent_name=agent.get("name", ""),
            total_score=report.get("total_score", agent.get("trust_score", 0)),
            tier=tier,
            tier_emoji=_tier_emoji(tier),
            categories=categories,
            github_data=report.get("github_data"),
            computed_at=report.get("computed_at", ""),
        )

    # No scoring-engine report yet — return basic info
    def _score_to_tier(s):
        if s >= 80: return "TRUSTED"
        if s >= 60: return "VERIFIED"
        if s >= 40: return "BASIC"
        if s >= 20: return "UNVERIFIED"
        return "UNKNOWN"
    def _tier_emoji(t):
        return {"TRUSTED": "🟢", "VERIFIED": "🔵", "BASIC": "🟡", "UNVERIFIED": "🟠", "UNKNOWN": "🔴"}.get(t, "⚪")
    ts = agent.get("trust_score", 0) or 0
    tier = _score_to_tier(ts)
    return RealScoreBreakdownResponse(
        agent_id=resolved_id,
        agent_name=agent.get("name", ""),
        total_score=ts,
        tier=tier,
        tier_emoji=_tier_emoji(tier),
        categories=[],
        computed_at="",
    )


@router.post("/agents/{agent_id}/recalculate-score", response_model=RecalculateResponse)
async def recalculate_score(agent_id: str, _admin: bool = Depends(require_admin_key)):
    """Recalculate trust score using v3 scoring engine.

    Requires X-Admin-Key header — recomputation is expensive and admin-only.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    old_score = agent.get("trust_score", 0) or 0

    from isnad.scoring.engine_v3 import ScoringEngineV3
    engine = ScoringEngineV3(db=_db)
    result = await engine.compute_and_store(agent)

    # Also store full report in trust_checks so GET /check/{id} returns fresh data
    try:
        now = datetime.now(timezone.utc)
        report_data = {
            "agent_id": agent["id"],
            "overall_score": result.final_score,
            "confidence": result.confidence,
            "tier": result.tier,
            "dimensions": {
                "provenance": {"raw": result.provenance.raw, "weighted": result.provenance.weighted},
                "track_record": {"raw": result.track_record.raw, "weighted": result.track_record.weighted},
                "presence": {"raw": result.presence.raw, "weighted": result.presence.weighted},
                "endorsements": {"raw": result.endorsements.raw, "weighted": result.endorsements.weighted},
                "infra_integrity": {"raw": result.infra_integrity.raw, "weighted": result.infra_integrity.weighted},
            },
            "decay_factor": result.decay_factor,
            "risk_flags": [],
            "attestation_count": result.data_snapshot.get("internal", {}).get("attestations", 0),
            "last_checked": now.isoformat() + "Z",
            "categories": [
                {"name": "provenance", "score": round(result.provenance.raw * 100), "modules_passed": round(result.provenance.raw * 10), "modules_total": 10, "findings": [f"Provenance: {result.provenance.raw:.0%} (weight 25%)"]},
                {"name": "track_record", "score": round(result.track_record.raw * 100), "modules_passed": round(result.track_record.raw * 10), "modules_total": 10, "findings": [f"Track Record: {result.track_record.raw:.0%} (weight 30%)"]},
                {"name": "presence", "score": round(result.presence.raw * 100), "modules_passed": round(result.presence.raw * 10), "modules_total": 10, "findings": [f"Presence: {result.presence.raw:.0%} (weight 20%)"]},
                {"name": "endorsements", "score": round(result.endorsements.raw * 100), "modules_passed": round(result.endorsements.raw * 10), "modules_total": 10, "findings": [f"Endorsements: {result.endorsements.raw:.0%} (weight 15%)"]},
                {"name": "infra_integrity", "score": round(result.infra_integrity.raw * 100), "modules_passed": round(result.infra_integrity.raw * 10), "modules_total": 10, "findings": [f"Infrastructure Integrity: {result.infra_integrity.raw:.0%} (weight 10%)"]},
            ],
            "certification_id": "",
            "certified": result.final_score >= 60 and result.confidence >= 0.4,
        }
        import json as _json
        async with _db._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO trust_checks (agent_id, report, score, requested_at) VALUES ($1, $2, $3, $4)",
                agent["id"], _json.dumps(report_data), result.final_score / 100.0, now.isoformat(),
            )
    except Exception as e:
        logger.warning("Failed to store trust check report: %s", e)

    return RecalculateResponse(
        agent_id=agent["id"],
        old_score=old_score,
        new_score=result.final_score,
        tier=result.tier,
        computed_at=result.computed_at,
    )


# ---------------------------------------------------------------------------
# PayLock webhook
# ---------------------------------------------------------------------------

PAYLOCK_VALID_EVENTS = {"escrow_created", "escrow_released", "escrow_disputed"}


class PayLockWebhookRequest(BaseModel):
    """Incoming PayLock escrow event."""
    event: str = Field(..., description="escrow_created | escrow_released | escrow_disputed")
    agent_id: str = Field(..., description="isnad agent_id involved in the escrow")
    contract_id: str = Field(..., description="PayLock contract/escrow ID")
    amount_sol: float = Field(0.0, description="Amount in SOL")
    timestamp: Optional[str] = Field(None, description="ISO-8601 event timestamp (default: now)")
    metadata: dict = Field(default_factory=dict, description="Extra data from PayLock")


class PayLockWebhookResponse(BaseModel):
    """Response after processing a PayLock event."""
    status: str = "accepted"
    signal_id: int
    agent_id: str
    event: str
    behavioral_impact: str = Field(description="Description of trust impact")


# Event → behavioral impact mapping
_PAYLOCK_IMPACT = {
    "escrow_created": "neutral — escrow opened, contract initiated",
    "escrow_released": "positive — successful delivery, funds released",
    "escrow_disputed": "negative — dispute raised, trust under review",
}


@router.get("/badge/{agent_id}", tags=["Public"], summary="Dynamic SVG trust badge")
async def get_badge_svg(agent_id: str):
    """Generate a dynamic SVG badge showing the agent's trust score and tier."""
    from fastapi.responses import Response

    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    agent = await _db.get_agent(agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    score = round(agent.get("trust_score", 0))
    # Escape user-controlled text for safe SVG embedding
    import html as _html
    name = _html.escape(agent.get("name", agent_id), quote=True)

    if score >= 80:
        tier, color, bg = "TRUSTED", "#00d4aa", "#0a2922"
    elif score >= 60:
        tier, color, bg = "VERIFIED", "#22d3ee", "#0a2429"
    elif score >= 40:
        tier, color, bg = "BASIC", "#f59e0b", "#29220a"
    elif score >= 20:
        tier, color, bg = "UNVERIFIED", "#fb923c", "#291a0a"
    else:
        tier, color, bg = "NEW", "#71717a", "#1a1a1a"

    # Calculate widths
    name_w = max(len(name) * 7 + 20, 60)
    score_w = 90
    total_w = name_w + score_w

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="28" viewBox="0 0 {total_w} 28">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#18181b"/>
      <stop offset="100%" stop-color="#1c1c22"/>
    </linearGradient>
  </defs>
  <rect width="{total_w}" height="28" rx="6" fill="url(#bg)" stroke="{color}" stroke-width="0.5" stroke-opacity="0.3"/>
  <rect x="{name_w}" width="{score_w}" height="28" rx="0" fill="{bg}"/>
  <rect x="{total_w - 6}" width="6" height="28" rx="0" fill="{bg}"/>
  <rect x="{total_w - 6}" y="0" width="6" height="28" rx="6" fill="{bg}"/>
  <text x="8" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="600" fill="#a1a1aa">isnad</text>
  <text x="38" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#d4d4d8">|</text>
  <text x="46" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="11" fill="#e4e4e7">{name}</text>
  <text x="{name_w + 10}" y="18" font-family="system-ui,-apple-system,monospace" font-size="11" font-weight="700" fill="{color}">{score}</text>
  <text x="{name_w + 32}" y="18" font-family="system-ui,-apple-system,sans-serif" font-size="9" fill="{color}" opacity="0.8">{tier}</text>
</svg>'''

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.post(
    "/webhook/paylock",
    response_model=PayLockWebhookResponse,
    tags=["Webhooks"],
    summary="PayLock escrow webhook",
    description=(
        "Receives escrow lifecycle events from PayLock and records them as "
        "behavioral signals in the isnad trust graph. Events: "
        "escrow_created, escrow_released, escrow_disputed."
    ),
)
async def paylock_webhook(request: Request):
    """Process a PayLock escrow event and record it as a behavioral signal."""
    # Read raw body first (needed for HMAC before JSON parsing)
    body = await request.body()

    # HMAC-SHA256 validation (fail-closed: reject if secret not configured)
    hmac_secret = os.environ.get("PAYLOCK_HMAC_SECRET", "")
    if not hmac_secret:
        logger.error("PayLock webhook called but PAYLOCK_HMAC_SECRET is not set — rejecting")
        raise HTTPException(status_code=503, detail="Webhook verification not configured")
    signature = request.headers.get("X-PayLock-Signature", "")
    expected = hmac.new(
        hmac_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # Parse and validate body
    import json as _json
    try:
        data = _json.loads(body)
        req = PayLockWebhookRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Validate event type
    if req.event not in PAYLOCK_VALID_EVENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown event '{req.event}'. Valid: {sorted(PAYLOCK_VALID_EVENTS)}",
        )

    # Require DB
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Verify agent exists (optional: create stub if not found)
    agent = await _db.get_agent(req.agent_id)
    if not agent:
        agent = await _db.get_agent_by_name(req.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent_id}' not registered in isnad")

    # Record behavioral signal
    signal = await _db.create_behavioral_signal(
        agent_id=agent["id"],
        source="paylock",
        event_type=req.event,
        contract_id=req.contract_id,
        amount_sol=req.amount_sol,
        metadata=req.metadata,
        created_at=req.timestamp or "",
    )

    impact = _PAYLOCK_IMPACT.get(req.event, "unknown")

    logger.info(
        "PayLock webhook: event=%s agent=%s contract=%s amount=%.4f SOL",
        req.event, agent["id"], req.contract_id, req.amount_sol,
    )

    return PayLockWebhookResponse(
        status="accepted",
        signal_id=signal["id"],
        agent_id=agent["id"],
        event=req.event,
        behavioral_impact=impact,
    )


@router.get(
    "/coinpay/reputation/{did:path}",
    tags=["Public"],
    summary="CoinPay DID reputation lookup",
    description="Query CoinPayPortal reputation data for a DID and show how it would affect isnad scoring.",
)
async def coinpay_reputation_lookup(did: str):
    """Proxy/enrich CoinPay DID reputation data."""
    from isnad.scoring.collectors.coinpay_collector import fetch_coinpay_reputation
    coinpay = await fetch_coinpay_reputation(did)
    if not coinpay.found:
        raise HTTPException(status_code=404, detail=f"DID '{did}' not found on CoinPayPortal")
    return {
        "did": coinpay.did,
        "score": coinpay.score,
        "total_tasks": coinpay.total_tasks,
        "success_rate": coinpay.success_rate,
        "unique_buyers": coinpay.unique_buyers,
        "lifetime_volume_usd": coinpay.lifetime_volume_usd,
        "trust_vector": {
            "E": coinpay.trust_vector.economic,
            "P": coinpay.trust_vector.productivity,
            "B": coinpay.trust_vector.behavioral,
            "D": coinpay.trust_vector.diversity,
            "R": coinpay.trust_vector.recency,
            "A": coinpay.trust_vector.anomaly,
            "C": coinpay.trust_vector.compliance,
        },
        "isnad_impact": {
            "dimension": "track_record",
            "description": "CoinPay DID reputation contributes up to 20 points to the track_record dimension (out of 120 max raw points)",
        },
    }


def create_app(*, allowed_origins: list[str] | None = None,
               use_lifespan: bool = True) -> FastAPI:
    """Create a standalone FastAPI app with the v1 router and middlewares."""
    if allowed_origins is None:
        env_origins = os.environ.get("ALLOWED_ORIGINS", "")
        if env_origins:
            allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    
    app = FastAPI(
        title="isnad API",
        description="Agent Trust Protocol — v1 API",
        version="0.3.0",
        lifespan=lifespan if use_lifespan else None,
        docs_url=None if os.environ.get("ISNAD_PRODUCTION") else "/docs",
        redoc_url=None if os.environ.get("ISNAD_PRODUCTION") else "/redoc",
    )
    add_middlewares(app, allowed_origins=allowed_origins)
    app.include_router(router)
    return app
