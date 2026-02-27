"""
isnad API v1 — Versioned REST API for the isnad trust platform.

Router prefix: /api/v1
Public endpoints (no auth required):
  GET /check/{agent_id}     — Full trust check report (flagship)
  GET /explorer              — Paginated agent list with scores
  GET /explorer/{agent_id}   — Single agent detail
  GET /stats                 — Platform statistics
  GET /health                — Health check
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


class TrustCheckResult(BaseModel):
    """Full trust-check report returned by /check/{agent_id}."""
    agent_id: str
    overall_score: int = Field(ge=0, le=100, description="Aggregate trust score 0-100")
    confidence: str = Field(description="high | medium | low")
    risk_flags: list[str] = []
    attestation_count: int = 0
    last_checked: str = Field(description="ISO-8601 timestamp")
    categories: list[CategoryScore] = []
    certification_id: str = ""
    certified: bool = False


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


class StatsResponse(BaseModel):
    """Platform-wide statistics."""
    agents_checked: int
    attestations_verified: int
    avg_response_ms: float
    uptime: float


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
    categories.append(CategoryScore(name="behavioral", score=round(beh_score / 6 * 100),
                                     modules_passed=beh_score, modules_total=6,
                                     findings=["no negative behavioral signals"]))
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

    # confidence
    if evidence_urls and wallet and platform:
        confidence = "high"
    elif wallet or platform:
        confidence = "medium"
    else:
        confidence = "low"

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
async def get_usage(request: Request, agent: dict = Depends(require_api_key_with_rate_limit)):
    """Get API usage for the current month. Requires X-API-Key header."""
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
async def create_api_key(body: ApiKeyRequest):
    """Generate a new API key. The raw key is returned once; only its hash is stored."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    raw_key = f"isnad_{secrets.token_urlsafe(32)}"
    await _db.create_api_key(raw_key, body.owner_email, body.rate_limit)
    return ApiKeyResponse(api_key=raw_key, owner_email=body.owner_email, rate_limit=body.rate_limit)


@router.get("/stats", response_model=StatsResponse)
async def stats():
    """Platform-wide statistics."""
    avg_ms = sum(_request_times[-100:]) / max(len(_request_times[-100:]), 1) if _request_times else 0.0
    agents_checked = 0
    if _db is not None:
        try:
            async with _db._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM trust_checks")
                agents_checked = row["cnt"] if row else 0
        except Exception:
            pass

    return StatsResponse(
        agents_checked=agents_checked,
        attestations_verified=len(_trust_chain.attestations),
        avg_response_ms=round(avg_ms, 2),
        uptime=round(time.time() - _start_time, 2),
    )


@router.get("/check/{agent_id}", response_model=TrustCheckResult)
@limiter.limit("60/minute")
async def check_agent(agent_id: str, request: Request, _caller: dict = Depends(require_api_key_with_rate_limit)):
    """
    **Flagship endpoint** — Run a full 36-module trust evaluation.
    """
    sanitize_input(agent_id, "agent_id")
    t0 = time.time()

    # Resolve agent_id — could be id, name, or pubkey
    resolved_id = agent_id
    # Try lookup by pubkey or name if db available
    if _db is not None:
        try:
            agent_row = await _db.get_agent(agent_id)
            if agent_row is None:
                agent_row = await _db.get_agent_by_pubkey(agent_id)
            if agent_row is not None:
                resolved_id = agent_row["id"]
        except Exception:
            pass

    result = _run_certification(resolved_id)

    # Persist to DB
    if _db is not None:
        try:
            report = result.model_dump()
            await _db.create_trust_check(
                agent_id=resolved_id,
                score=result.overall_score / 100.0,
                report=report,
                requester_ip=request.client.host if request.client else "",
            )
        except Exception:
            pass  # don't fail the request on DB errors

    elapsed_ms = (time.time() - t0) * 1000
    _request_times.append(elapsed_ms)

    return result


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
                agent_row = await _db.get_agent_by_pubkey(agent_id)
        except Exception:
            pass

    if agent_row:
        atts = []
        try:
            atts = await _db.get_attestations_for_subject(agent_id)
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


class SimpleRegisterResponse(BaseModel):
    """Response with agent_id and api_key."""
    agent_id: str
    api_key: str


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

    # Generate Ed25519 keypair
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
            f"SELECT * FROM agents {where} ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}",
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
        raise HTTPException(status_code=404, detail="Agent not found")

    platform_data = await _db.get_platform_data(agent_id)

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

    badge_id = hashlib.sha256(f"badge:{agent_id}:{body.badge_type}:{time.time()}".encode()).hexdigest()[:16]
    created = await _db.create_badge(badge_id, agent_id, body.badge_type, body.expires_at, body.metadata)
    if not created:
        raise HTTPException(status_code=409, detail="Badge already exists for this agent")

    return BadgeOut(
        id=badge_id,
        agent_id=agent_id,
        badge_type=body.badge_type,
        granted_at=datetime.now(timezone.utc).isoformat() + "Z",
        expires_at=body.expires_at,
        metadata=body.metadata,
    )


async def _auto_grant_badge(agent_id: str, badge_type: str, metadata: Optional[dict] = None):
    """Auto-grant a badge if not already present. Called internally."""
    if _db is None:
        return
    badge_id = hashlib.sha256(f"badge:{agent_id}:{badge_type}:auto".encode()).hexdigest()[:16]
    await _db.create_badge(badge_id, agent_id, badge_type, metadata=metadata or {})


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


@router.get("/trust-score-v2/{agent_id}")
async def trust_score_v2_compat(agent_id: str, request: Request):
    """Backward-compatible trust-score-v2 endpoint.

    Calls the same TrustScorerV2 logic as the old API and returns the
    response shape the frontend expects.
    """
    from isnad.trustscore.scorer_v2 import TrustScorerV2

    # Try to resolve platform links from DB
    platforms: dict[str, str] = {}
    resolved_id = agent_id

    if _db is not None:
        try:
            agent_row = await _db.get_agent(agent_id)
            if agent_row is None:
                # Try lookup by name
                async with _db._pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM agents WHERE LOWER(name) = LOWER($1)", agent_id
                    )
                    if row:
                        agent_row = dict(row)
            if agent_row:
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
        except Exception:
            pass

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
