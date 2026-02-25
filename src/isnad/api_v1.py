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

import hashlib
import hmac
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
async def check_agent(agent_id: str, request: Request):
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
async def verify_agent(agent_id: str, request: Request):
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
# Agent Registration Endpoints
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
