# isnad Platform — Architecture Document

> Version 0.2 · 2026-02-23 · Author: Architect Agent

---

## 1. System Overview

```
                          ┌─────────────────────────────────────────┐
                          │           INTERNET / CLIENTS            │
                          └────────┬──────────┬──────────┬──────────┘
                                   │          │          │
                          ┌────────▼───┐ ┌────▼────┐ ┌──▼──────────┐
                          │  Trust     │ │  API    │ │  Trust      │
                          │  Explorer  │ │  Docs   │ │  Check      │
                          │  (SPA)     │ │  Page   │ │  Widget     │
                          └────────┬───┘ └────┬────┘ └──┬──────────┘
                                   │          │          │
                          ─────────▼──────────▼──────────▼──────────
                          │          Nginx / Caddy Reverse Proxy    │
                          ──────────────────┬───────────────────────
                                            │
                          ┌─────────────────▼─────────────────────┐
                          │         FastAPI Application            │
                          │                                        │
                          │  ┌──────────┐ ┌──────────┐ ┌────────┐ │
                          │  │ Auth     │ │ Rate     │ │ Cache  │ │
                          │  │ Middle-  │ │ Limiter  │ │ (L1/L2)│ │
                          │  │ ware     │ │          │ │        │ │
                          │  └────┬─────┘ └────┬─────┘ └───┬────┘ │
                          │       │            │           │      │
                          │  ┌────▼────────────▼───────────▼────┐ │
                          │  │           Router Layer            │ │
                          │  │                                   │ │
                          │  │ /check  /certify  /explorer      │ │
                          │  │ /identity /attest /verify         │ │
                          │  │ /discovery /policies /delegations │ │
                          │  └──────────────┬───────────────────┘ │
                          │                 │                      │
                          │  ┌──────────────▼───────────────────┐ │
                          │  │        Service Layer              │ │
                          │  │                                   │ │
                          │  │ TrustChain  CertificationEngine  │ │
                          │  │ DiscoveryRegistry  PolicyEngine  │ │
                          │  │ Analytics   Monitoring            │ │
                          │  └──────────────┬───────────────────┘ │
                          │                 │                      │
                          │  ┌──────────────▼───────────────────┐ │
                          │  │       Repository Layer            │ │
                          │  │  (SQLAlchemy async / raw SQL)     │ │
                          │  └──────────────┬───────────────────┘ │
                          └─────────────────┼──────────────────────┘
                                            │
                          ┌─────────────────▼──────────────────────┐
                          │   PostgreSQL (prod) / SQLite (dev)     │
                          └────────────────────────────────────────┘
```

---

## 2. Tech Stack Decisions

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **API** | FastAPI 0.115+ | Already in use, async, auto-OpenAPI |
| **ORM** | SQLAlchemy 2.0 + async | Type-safe, migration-ready, both PG & SQLite |
| **Migrations** | Alembic | Standard for SQLAlchemy |
| **DB (dev)** | SQLite (WAL mode) | Zero-config, existing `SQLiteBackend` works |
| **DB (prod)** | PostgreSQL 16 | Scalable, JSONB, full-text search for explorer |
| **Auth** | API keys + optional JWT | Simple for MVP; JWT for future session-based |
| **Cache** | Existing `TrustCache` (in-memory L1) + Redis L2 (Phase 2) | Already implemented in `caching.py` |
| **Frontend** | Static HTML + HTMX + Tailwind | No build step, fast, SSR-friendly |
| **Deployment** | Docker Compose → single VPS | Simplest path; Dockerfile exists |
| **Crypto** | PyNaCl (Ed25519) | Already in use, battle-tested |

---

## 3. Database Schema

### 3.1 Core Tables

```sql
-- Agent identities
CREATE TABLE agents (
    id              TEXT PRIMARY KEY,          -- "agent:abc123..."
    public_key      TEXT NOT NULL UNIQUE,
    name            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB DEFAULT '{}'
);

-- Attestation chain (the heart of isnad)
CREATE TABLE attestations (
    id              TEXT PRIMARY KEY,          -- attestation_id hash
    subject_id      TEXT NOT NULL REFERENCES agents(id),
    witness_id      TEXT NOT NULL REFERENCES agents(id),
    task            TEXT NOT NULL,
    evidence        TEXT DEFAULT '',
    timestamp       TIMESTAMPTZ NOT NULL,
    signature       TEXT NOT NULL,
    witness_pubkey  TEXT NOT NULL,
    scope           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_att_subject ON attestations(subject_id);
CREATE INDEX idx_att_witness ON attestations(witness_id);
CREATE INDEX idx_att_timestamp ON attestations(timestamp);

-- Revocation registry
CREATE TABLE revocations (
    id              SERIAL PRIMARY KEY,
    target_id       TEXT NOT NULL,             -- agent_id or attestation_id
    reason          TEXT NOT NULL,
    revoked_by      TEXT NOT NULL REFERENCES agents(id),
    scope           TEXT,
    signature       TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_rev_target ON revocations(target_id);

-- Certification results (persistent)
CREATE TABLE certifications (
    id              TEXT PRIMARY KEY,          -- cert_id hash
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    trust_score     REAL NOT NULL,
    confidence      TEXT NOT NULL,             -- "high"/"medium"/"low"
    modules_passed  INT NOT NULL,
    modules_total   INT NOT NULL DEFAULT 36,
    certified       BOOLEAN NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    signature       TEXT NOT NULL,
    details         JSONB NOT NULL,            -- per-category breakdown
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cert_agent ON certifications(agent_id);
CREATE INDEX idx_cert_expires ON certifications(expires_at);

-- Discovery profiles
CREATE TABLE discovery_profiles (
    agent_id        TEXT PRIMARY KEY REFERENCES agents(id),
    name            TEXT NOT NULL,
    capabilities    TEXT[] DEFAULT '{}',
    endpoints       JSONB DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    signature       TEXT NOT NULL,
    registered_at   TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_disc_caps ON discovery_profiles USING GIN(capabilities);
-- SQLite equivalent: TEXT + JSON, no GIN

-- Delegations
CREATE TABLE delegations (
    content_hash    TEXT PRIMARY KEY,
    delegator_key   TEXT NOT NULL,
    delegate_key    TEXT NOT NULL,
    scope           TEXT NOT NULL,
    parent_hash     TEXT REFERENCES delegations(content_hash),
    depth           INT NOT NULL DEFAULT 0,
    max_depth       INT NOT NULL DEFAULT 1,
    expires_at      TIMESTAMPTZ,
    signature       TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_del_delegate ON delegations(delegate_key);
```

### 3.2 Auth & API Keys

```sql
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash        TEXT NOT NULL UNIQUE,      -- SHA-256 of the key
    key_prefix      TEXT NOT NULL,             -- first 8 chars for display "isnd_abc1..."
    owner_name      TEXT NOT NULL,
    owner_email     TEXT,
    scopes          TEXT[] DEFAULT '{read}',   -- "read", "write", "certify", "admin"
    rate_limit      INT DEFAULT 100,           -- requests per minute
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT true
);
CREATE INDEX idx_apikey_hash ON api_keys(key_hash);

CREATE TABLE api_key_usage (
    id              BIGSERIAL PRIMARY KEY,
    key_id          UUID REFERENCES api_keys(id),
    endpoint        TEXT NOT NULL,
    method          TEXT NOT NULL,
    status_code     INT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_usage_key ON api_key_usage(key_id);
CREATE INDEX idx_usage_ts ON api_key_usage(timestamp);
```

### 3.3 Trust Policies (persistent)

```sql
CREATE TABLE trust_policies (
    name            TEXT PRIMARY KEY,
    default_action  TEXT NOT NULL DEFAULT 'deny',
    rules           JSONB NOT NULL,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. API Endpoint Design

### 4.1 Public Endpoints (no auth)

#### `GET /` — Service info
```json
{"service": "isnad", "version": "0.2.0", "docs": "/docs"}
```

#### `GET /health` — Health check
```json
{"status": "ok", "db": "ok", "timestamp": 1708700000}
```

#### `GET /check/{agent_id}` — 🆕 Trust Check (the VirusTotal for agents)
The flagship public endpoint. Human-friendly trust report.

**Response:**
```json
{
  "agent_id": "agent:abc123",
  "name": "WeatherBot",
  "trust_score": 0.847,
  "trust_level": "HIGH",
  "certified": true,
  "certification_id": "cert_a1b2c3",
  "certification_expires": "2026-03-25T00:00:00Z",
  "summary": "Trusted agent with 47 attestations from 12 unique witnesses",
  "categories": {
    "identity": {"score": 0.9, "status": "pass", "detail": "Ed25519 key verified, wallet linked"},
    "attestation": {"score": 0.85, "status": "pass", "detail": "47 valid attestations, 0 revoked"},
    "behavioral": {"score": 0.8, "status": "pass", "detail": "No anomalies detected"},
    "platform": {"score": 0.75, "status": "pass", "detail": "Present on 2 platforms"},
    "transactions": {"score": 0.9, "status": "pass", "detail": "Clean on-chain history"},
    "security": {"score": 0.88, "status": "pass", "detail": "No security incidents"}
  },
  "attestation_count": 47,
  "unique_witnesses": 12,
  "revocations": [],
  "first_seen": "2026-01-15T10:00:00Z",
  "last_attestation": "2026-02-20T14:30:00Z",
  "flags": []
}
```

**Trust levels:** `NONE` (0), `LOW` (<0.3), `MEDIUM` (<0.6), `HIGH` (<0.85), `VERY_HIGH` (≥0.85)

#### `GET /explorer` — 🆕 Trust Explorer page (HTML)
Server-rendered HTML page. Lists certified agents with search/filter.

#### `GET /explorer/api` — Trust Explorer data (JSON)
**Query params:** `?q=search&capability=code-review&min_score=0.5&sort=score&page=1&limit=20`

**Response:**
```json
{
  "total": 142,
  "page": 1,
  "agents": [
    {
      "agent_id": "agent:abc123",
      "name": "WeatherBot",
      "trust_score": 0.847,
      "trust_level": "HIGH",
      "certified": true,
      "capabilities": ["weather", "forecasting"],
      "attestation_count": 47,
      "first_seen": "2026-01-15T10:00:00Z"
    }
  ]
}
```

### 4.2 Authenticated Endpoints (API key required)

Header: `Authorization: Bearer isnd_xxxxxxxxxxxx`

#### `POST /identity` — Create agent identity
**Request:** `{"name": "MyAgent"}`
**Response:** `{"agent_id": "agent:abc123", "public_key": "ed25519hex..."}`

#### `POST /attest` — Create attestation
**Request:**
```json
{
  "subject_id": "agent:abc123",
  "witness_id": "agent:def456",
  "task": "code-review",
  "evidence": "Reviewed PR #42 correctly"
}
```
**Response:**
```json
{
  "attestation_id": "att_hash",
  "subject": "agent:abc123",
  "witness": "agent:def456",
  "task": "code-review",
  "timestamp": "2026-02-23T13:00:00Z",
  "signature": "hex...",
  "chain_size": 148
}
```

#### `POST /verify` — Verify single attestation
#### `POST /batch-verify` — Verify multiple attestations
#### `GET /trust-score/{agent_id}?scope=optional` — Raw trust score

#### `POST /certify` — Run certification
**Request:**
```json
{
  "agent_id": "agent:abc123",
  "agent_wallet": "0xabc...",
  "platform": "acp",
  "capabilities": ["code-review", "weather"],
  "evidence_urls": ["https://github.com/example"]
}
```
**Response:** Full `CertificationResult` (see existing schema — certified, score, 6 categories, signature, expiry)

#### `GET /certify/{certification_id}` — Verify existing certification

#### `POST /revoke` — Revoke agent/attestation
#### `GET /revocations/{target_id}` — Check revocation status

#### `POST /discovery/register` — Register agent profile
#### `GET /discovery/agents?capability=x` — Search agents
#### `GET /discovery/agents/{agent_id}` — Get agent profile
#### `DELETE /discovery/agents/{agent_id}` — Unregister

#### `POST /delegations` — Create delegation
#### `POST /delegations/sub-delegate` — Sub-delegate
#### `GET /delegations/verify/{hash}` — Verify delegation chain
#### `GET /delegations/for/{pubkey}` — List delegations

#### `GET /policies` — List trust policies
#### `POST /policies` — Create policy
#### `GET /policies/{name}` — Get policy
#### `POST /policies/{name}/evaluate` — Evaluate agent against policy
#### `DELETE /policies/{name}` — Delete policy

#### `POST /v1/rotate-key` — Key rotation
#### `POST /v1/verify-rotation` — Verify rotation proof

### 4.3 Admin Endpoints (admin API key)

#### `POST /admin/api-keys` — Create API key
**Request:** `{"owner_name": "Acme Corp", "owner_email": "dev@acme.com", "scopes": ["read", "certify"]}`
**Response:** `{"key": "isnd_xxxxxxxxxxxxxx", "key_id": "uuid", "note": "Store this key — it won't be shown again"}`

#### `GET /admin/api-keys` — List keys
#### `DELETE /admin/api-keys/{key_id}` — Revoke key
#### `GET /admin/stats` — Platform stats (total agents, attestations, certifications)

---

## 5. Component Breakdown

### 5.1 Backend API (`src/isnad/`)

| Module | Purpose | Changes for MVP |
|--------|---------|-----------------|
| `core.py` | Identity, Attestation, TrustChain, Revocation | Stable — no changes |
| `api.py` | FastAPI routes | Refactor into router modules, add auth middleware |
| `storage.py` | Pluggable backends (Memory, SQLite, File) | Replace KV approach with proper relational schema |
| `analytics.py` | Trust graph analysis, sybil detection | Wire into `/check` endpoint |
| `discovery.py` | Agent registry | Wire into `/explorer` |
| `trust_report.py` | Markdown trust reports | Adapt for JSON `/check` response |
| `caching.py` | L1/L2 cache | Wire into trust score lookups |
| `monitoring.py` | Metrics, health checks | Expose via `/admin/stats` |
| `compliance.py` | GDPR erasure, consent | Keep, wire into delete endpoints |
| `policy.py` | Trust policies | Already API-connected |
| `delegation.py` | Delegation chains | Already API-connected |
| `trustscore/` | Multi-signal scoring | Wire into certification engine |

### 5.2 New Modules to Create

| Module | Purpose |
|--------|---------|
| `src/isnad/auth.py` | API key validation middleware, key management |
| `src/isnad/db.py` | SQLAlchemy models, engine setup, session factory |
| `src/isnad/repos/` | Repository pattern — `agents.py`, `attestations.py`, `certifications.py` |
| `src/isnad/routers/` | Split `api.py` into: `check.py`, `certify.py`, `explorer.py`, `identity.py`, `admin.py` |
| `src/isnad/services/check.py` | Trust Check aggregation logic |
| `templates/` | Jinja2 HTML templates for Explorer + docs page |
| `static/` | CSS (Tailwind CDN), minimal JS (HTMX) |
| `alembic/` | Database migrations |

### 5.3 Frontend (Trust Explorer)

Minimal server-rendered approach:
- `GET /explorer` → Jinja2 template with HTMX for search/filter
- `GET /docs/custom` → Custom API docs page (beyond Swagger)
- `/docs` → FastAPI auto-generated Swagger (already works)
- Tailwind via CDN, HTMX for interactivity, zero build step

### 5.4 Auth Flow

```
Client sends: Authorization: Bearer isnd_xxxxxxxx
                    │
                    ▼
         ┌──────────────────┐
         │  Auth Middleware  │
         │                  │
         │  1. Extract key  │
         │  2. SHA-256 hash │
         │  3. Lookup in DB │
         │  4. Check scopes │
         │  5. Check expiry │
         │  6. Rate limit   │
         └────────┬─────────┘
                  │
         Pass: request.state.api_key = key_record
         Fail: 401 / 403 / 429
```

Public endpoints (`/check/*`, `/explorer/*`, `/health`, `/docs`) skip auth. Rate-limited by IP.

---

## 6. Migration Plan: In-Memory → Persistent Storage

### Current State
- All data in Python dicts/lists (lost on restart)
- `storage.py` has `SQLiteBackend` but it's a generic KV store
- `PersistentTrustChain` wrapper exists but uses KV, not relational

### Migration Steps

1. **Create SQLAlchemy models** (`src/isnad/db.py`) matching schema in §3
2. **Create repository layer** (`src/isnad/repos/`) with async CRUD
3. **Create Alembic migration** for initial schema
4. **Adapt service layer**: Replace direct `trust_chain` / `identities` dict usage with repository calls
5. **Keep in-memory caching**: TrustChain still computes scores in-memory, hydrated from DB on startup (same pattern as `PersistentTrustChain`)
6. **Deprecate KV storage.py**: Keep for backward compat, but new code uses relational repos

### Compatibility
- `core.py` domain objects unchanged — repos serialize/deserialize to/from them
- Existing tests continue to work (they test core logic, not storage)
- New integration tests for repository layer

---

## 7. Phase Breakdown

### Phase 1 — Foundation (Week 1-2)

**Goal:** Working API with persistence, auth, and Trust Check endpoint.

- [ ] Set up SQLAlchemy models + Alembic (`db.py`, `alembic/`)
- [ ] Implement repository layer (`repos/agents.py`, `repos/attestations.py`, etc.)
- [ ] Split `api.py` into routers (`routers/check.py`, `routers/certify.py`, etc.)
- [ ] Implement API key auth middleware (`auth.py`)
- [ ] Build `GET /check/{agent_id}` — the flagship endpoint
- [ ] Admin endpoint to create/manage API keys
- [ ] Basic Dockerfile update with SQLite default
- [ ] Migration script for any existing data

**Deliverable:** `docker compose up` → working API with SQLite, auth, and Trust Check.

### Phase 2 — Explorer & Polish (Week 3-4)

**Goal:** Public-facing Trust Explorer + polished certification.

- [ ] Trust Explorer HTML page (`GET /explorer`) with HTMX search
- [ ] Explorer JSON API (`GET /explorer/api`) with pagination, filters
- [ ] Polish `/certify` — persist certifications, add verification lookup
- [ ] Custom API docs page (beyond Swagger)
- [ ] Rate limiting per API key + IP-based for public endpoints
- [ ] Wire `analytics.py` into Trust Check (sybil scores, network position)
- [ ] Add trust badges / embeddable widget endpoint
- [ ] PostgreSQL support + docker-compose with PG option

**Deliverable:** Public-facing website where anyone can look up agent trust.

### Phase 3 — Scale & Integrate (Week 5-8)

**Goal:** Production hardening, integrations, ecosystem.

- [ ] Redis L2 cache for trust scores
- [ ] Webhook notifications (certification events)
- [ ] SDK client library (Python package)
- [ ] ACP protocol bridge (`acp_bridge.py` already exists)
- [ ] Federation support (`federation.py` already exists)
- [ ] Monitoring dashboard (wire `monitoring.py` into `/admin/dashboard`)
- [ ] GDPR compliance endpoints (data export, erasure)
- [ ] Batch certification API for platforms
- [ ] Public stats page (total agents, attestations, trust graph viz)

---

## 8. Configuration

```python
# src/isnad/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./isnad.db"
    # Auth
    ADMIN_API_KEY: str = ""              # Bootstrap admin key
    API_KEY_PREFIX: str = "isnd_"
    # Rate limiting
    RATE_LIMIT_PUBLIC: int = 30          # per minute per IP
    RATE_LIMIT_AUTHENTICATED: int = 100  # per minute per key
    # Cache
    CACHE_TTL_TRUST_SCORE: int = 300     # 5 min
    CACHE_TTL_CERTIFICATION: int = 3600  # 1 hour
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8420
    
    class Config:
        env_file = ".env"
```

---

## 9. Key Design Decisions

1. **SQLite for dev/small deploy, Postgres for scale** — SQLAlchemy abstracts the difference. Single-file SQLite is perfect for `docker compose up` demos.

2. **Repository pattern over raw SQL** — Testable, swappable. Core domain objects (`Attestation`, `TrustChain`) stay pure.

3. **In-memory TrustChain stays** — Trust score computation uses graph traversal. Hydrate from DB on startup, write-through on mutations. Don't query DB for every score calculation.

4. **HTMX over React/Vue** — The Explorer is a read-heavy page with search. HTMX + Jinja2 = zero JS build step, SEO-friendly, fast.

5. **API keys over OAuth** — Target users are developers integrating isnad into their agent platforms. API keys are simple, familiar, sufficient. OAuth is overkill for Phase 1.

6. **Keep existing module structure** — The 36+ modules are well-organized. Don't rewrite; add routers/repos/auth layers around them.

7. **Port 8420** — Already configured, memorable.

---

## 10. File Structure (Target)

```
isnad-ref-impl/
├── alembic/                    # DB migrations
│   ├── versions/
│   └── env.py
├── src/isnad/
│   ├── __init__.py
│   ├── config.py               # NEW: Pydantic settings
│   ├── db.py                   # NEW: SQLAlchemy models + engine
│   ├── auth.py                 # NEW: API key middleware
│   ├── app.py                  # NEW: FastAPI app factory (replaces api.py top-level)
│   ├── routers/                # NEW: split from api.py
│   │   ├── check.py            # GET /check/{agent_id}
│   │   ├── certify.py          # POST /certify, GET /certify/{id}
│   │   ├── explorer.py         # GET /explorer, GET /explorer/api
│   │   ├── identity.py         # POST /identity, attestations, verify
│   │   ├── discovery.py        # Discovery registry routes
│   │   ├── policy.py           # Trust policy routes
│   │   ├── delegation.py       # Delegation routes
│   │   └── admin.py            # API key mgmt, stats
│   ├── repos/                  # NEW: repository layer
│   │   ├── agents.py
│   │   ├── attestations.py
│   │   ├── certifications.py
│   │   └── api_keys.py
│   ├── services/               # NEW: business logic
│   │   └── check.py            # Trust Check aggregation
│   ├── core.py                 # KEEP: domain objects
│   ├── analytics.py            # KEEP: graph analysis
│   ├── caching.py              # KEEP: L1/L2 cache
│   ├── monitoring.py           # KEEP: metrics
│   ├── compliance.py           # KEEP: GDPR
│   ├── discovery.py            # KEEP: registry logic
│   ├── policy.py               # KEEP: policy engine
│   ├── delegation.py           # KEEP: delegation logic
│   ├── storage.py              # KEEP (deprecated): legacy KV
│   └── ...                     # Other existing modules
├── templates/                  # NEW: Jinja2
│   ├── explorer.html
│   ├── check.html
│   └── docs.html
├── static/                     # NEW: CSS/JS
├── tests/                      # Existing 45 test files
├── docs/
│   └── ARCHITECTURE.md         # This document
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── pyproject.toml
```

---

## 11. Dependencies to Add

```toml
# pyproject.toml additions
[project.dependencies]
sqlalchemy = ">=2.0"
aiosqlite = ">=0.20"          # SQLite async driver
alembic = ">=1.13"
pydantic-settings = ">=2.0"
jinja2 = ">=3.1"              # Templates
python-multipart = ">=0.0.9"  # Form data
# Optional for production:
# asyncpg = ">=0.29"          # PostgreSQL async driver
# redis = ">=5.0"             # L2 cache
```

---

*This document is the source of truth for the isnad platform rebuild. All implementation agents should reference it.*
