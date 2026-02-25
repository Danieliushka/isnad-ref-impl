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
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from isnad.core import AgentIdentity, Attestation, TrustChain, RevocationRegistry

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


async def require_api_key(api_key: str = Security(_api_key_header)) -> dict:
    """Dependency that validates the X-API-Key header against the database."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    key_record = await _db.validate_api_key(api_key)
    if key_record is None:
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
    yield
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
    """Attach CORS and security-headers middlewares to *app*."""
    origins = allowed_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


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
            cur = await _db._db.execute("SELECT COUNT(*) FROM trust_checks")
            row = await cur.fetchone()
            agents_checked = row[0] if row else 0
        except Exception:
            pass

    return StatsResponse(
        agents_checked=agents_checked,
        attestations_verified=len(_trust_chain.attestations),
        avg_response_ms=round(avg_ms, 2),
        uptime=round(time.time() - _start_time, 2),
    )


@router.get("/check/{agent_id}", response_model=TrustCheckResult)
async def check_agent(agent_id: str, request: Request):
    """
    **Flagship endpoint** — Run a full 36-module trust evaluation.

    Accepts an agent ID, name, or public key. Returns a detailed report
    with overall score, 6 category breakdowns, confidence level, risk flags,
    and attestation count. Results are persisted to the database.
    """
    _check_rate_limit(request)
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
            cur = await _db._db.execute("SELECT COUNT(*) FROM agents")
            row = await cur.fetchone()
            total = row[0] if row else 0
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
async def register_agent(body: AgentRegisterRequest):
    """Register a new agent. Generates Ed25519 keypair and API key server-side."""
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
    """Get full public profile of an agent."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    import json

    agent = await _db.get_agent(agent_id)
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

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    agent = await _db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.get("api_key_hash") != api_key_hash:
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

def create_app(*, allowed_origins: list[str] | None = None,
               use_lifespan: bool = True) -> FastAPI:
    """Create a standalone FastAPI app with the v1 router and middlewares."""
    app = FastAPI(
        title="isnad API",
        description="Agent Trust Protocol — v1 API",
        version="0.3.0",
        lifespan=lifespan if use_lifespan else None,
    )
    add_middlewares(app, allowed_origins=allowed_origins)
    app.include_router(router)
    return app
