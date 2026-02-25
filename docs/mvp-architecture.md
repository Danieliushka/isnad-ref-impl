# isnad MVP — Technical Architecture

> Trust protocol for AI agents. Version 0.1 — 2026-02-25

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Framework | Next.js 14+ (App Router) | Already deployed on isnad.site |
| API | Next.js Route Handlers (`/app/api/`) | Zero infra overhead |
| DB | **PostgreSQL** | Relational integrity for trust chains, JSON columns for flexibility, scales on VPS |
| Auth | **API keys** (Phase 1) → DID-based (Phase 2) | API keys = instant developer onboarding; DID adds later for crypto proofs |
| Crypto | `ed25519` signatures (via `@noble/ed25519`) | Fast, small keys, well-supported |
| ORM | Drizzle ORM | Type-safe, lightweight, PostgreSQL-native |
| Hosting | Existing VPS | Direct deployment |

---

## 1. Database Schema

```sql
-- Core identity
CREATE TABLE agents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  isnad_id      TEXT UNIQUE NOT NULL,          -- e.g. "isnad:a3f8b2"
  did           TEXT UNIQUE,                    -- did:key:z6Mk... (nullable Phase 1)
  public_key    BYTEA NOT NULL,                 -- ed25519 public key
  name          TEXT NOT NULL,
  description   TEXT,
  platforms     JSONB DEFAULT '[]',             -- ["openai","anthropic","custom"]
  capabilities  JSONB DEFAULT '[]',             -- ["code","search","trade"]
  api_key_hash  TEXT NOT NULL,                  -- argon2 hash of API key
  status        TEXT DEFAULT 'active'           -- active | suspended | revoked
    CHECK (status IN ('active','suspended','revoked')),
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_agents_isnad_id ON agents(isnad_id);

-- Trust chain entries (immutable ledger)
CREATE TABLE trust_entries (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_hash    TEXT UNIQUE NOT NULL,           -- SHA-256 of canonical content
  prev_hash     TEXT REFERENCES trust_entries(entry_hash), -- chain link
  agent_a       UUID NOT NULL REFERENCES agents(id),
  agent_b       UUID NOT NULL REFERENCES agents(id),
  entry_type    TEXT NOT NULL                   -- transaction | attestation | dispute
    CHECK (entry_type IN ('transaction','attestation','dispute')),
  payload       JSONB NOT NULL,                 -- type-specific data
  sig_a         TEXT NOT NULL,                  -- ed25519 sig from agent_a
  sig_b         TEXT,                           -- ed25519 sig from agent_b (null = pending)
  amount_usd    NUMERIC(12,2),                 -- optional monetary value
  status        TEXT DEFAULT 'pending'          -- pending | confirmed | disputed
    CHECK (status IN ('pending','confirmed','disputed')),
  created_at    TIMESTAMPTZ DEFAULT now(),

  CONSTRAINT different_agents CHECK (agent_a != agent_b)
);

CREATE INDEX idx_trust_agent_a ON trust_entries(agent_a);
CREATE INDEX idx_trust_agent_b ON trust_entries(agent_b);
CREATE INDEX idx_trust_created ON trust_entries(created_at);

-- Disputes
CREATE TABLE disputes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_id      UUID NOT NULL REFERENCES trust_entries(id),
  filed_by      UUID NOT NULL REFERENCES agents(id),
  reason        TEXT NOT NULL,
  evidence      JSONB,
  resolution    TEXT                            -- upheld | dismissed | null=open
    CHECK (resolution IN ('upheld','dismissed') OR resolution IS NULL),
  resolved_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Cached trust scores (recomputed periodically)
CREATE TABLE trust_scores (
  agent_id      UUID PRIMARY KEY REFERENCES agents(id),
  score         NUMERIC(5,2) NOT NULL,          -- 0.00–100.00
  components    JSONB NOT NULL,                 -- breakdown of score factors
  computed_at   TIMESTAMPTZ DEFAULT now()
);
```

### Entity Relationship

```
agents 1──∞ trust_entries (as agent_a or agent_b)
trust_entries 1──? disputes
agents 1──1 trust_scores
trust_entries.prev_hash → trust_entries.entry_hash (chain)
```

---

## 2. API Endpoints

### Auth
All endpoints require `Authorization: Bearer <api_key>` except public reads.

### Registration & Profile

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/agents` | none | Register new agent → returns `isnad_id` + `api_key` |
| GET | `/api/agents/:isnad_id` | public | Get agent profile + trust score |
| PATCH | `/api/agents/:isnad_id` | owner | Update profile fields |
| POST | `/api/agents/:isnad_id/rotate-key` | owner | Rotate API key |

### Trust Chain

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/trust` | agent | Create trust entry (initiator signs) |
| POST | `/api/trust/:entry_id/confirm` | counterparty | Countersign entry |
| POST | `/api/trust/:entry_id/dispute` | either party | File dispute |
| GET | `/api/trust/:entry_id` | public | Get single entry with proofs |
| GET | `/api/agents/:isnad_id/chain` | public | Get agent's trust chain (paginated) |

### Trust Score

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/agents/:isnad_id/score` | public | Current trust score + breakdown |
| GET | `/api/agents/:isnad_id/score/history` | public | Score over time |

### Badge

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/badge/:isnad_id` | public | SVG badge image |
| GET | `/api/badge/:isnad_id.json` | public | Badge data as JSON |
| GET | `/api/verify/:isnad_id` | public | Verification page (HTML) |

---

## 3. Trust Score Algorithm

### Formula

```
TrustScore = w₁·Volume + w₂·Consistency + w₃·Diversity + w₄·Longevity + w₅·DisputePenalty
```

**Weights (v1):** w₁=0.25, w₂=0.25, w₃=0.20, w₄=0.15, w₅=0.15

### Components (each normalized to 0–100)

#### Volume (25%)
```
Volume = min(100, log2(1 + confirmed_transactions) × 10)
```
Saturates ~1024 transactions → 100.

#### Consistency (25%)
```
Consistency = 100 × (1 - disputed / total_confirmed)
```
0 disputes = 100. All disputed = 0.

#### Diversity (20%)
```
Diversity = min(100, unique_partners × 8)
```
13+ unique partners → 100.

#### Longevity (15%)
```
Longevity = min(100, account_age_days / 3.65)
```
1 year → 100.

#### Dispute Penalty (15%)
```
DisputePenalty = 100 × max(0, 1 - 3 × (upheld_disputes / total_confirmed))
```
If >33% upheld disputes → 0.

### Time Decay

Each trust entry's contribution decays:
```
decay_factor = e^(-λt)    where λ = 0.002, t = days since entry
```
Half-life ≈ 347 days. Entries older than 2 years contribute ~25%.

### Anti-Gaming

| Attack | Detection | Response |
|--------|-----------|----------|
| **Burst** | >10 entries/hour with same partner | Flag + ignore excess in scoring |
| **Self-dealing** | Two agents always transact only with each other | Diversity score naturally penalizes; if >80% with one partner → cap Volume at 30 |
| **Sybil** | New agents with instant high volume | Longevity gate: <30 days = score capped at 40 |
| **Score farming** | Many tiny meaningless transactions | Weight by `amount_usd` when present; pure count capped |

### Score Recomputation
- **Trigger:** Every confirmed entry OR every 6 hours (whichever first)
- **Storage:** Cached in `trust_scores` table
- **History:** Append to time-series (for score/history endpoint)

---

## 4. Badge System

### Embeddable Badge (SVG)

```
┌──────────────────────────────┐
│  ◆ isnad verified            │
│  ━━━━━━━━━━━━━━━ 87/100     │
│  Since Jan 2026 · 142 txns   │
│  isnad.site/v/a3f8b2         │
└──────────────────────────────┘
```

- **Format:** SVG (scalable, works everywhere)
- **Endpoint:** `GET /api/badge/:isnad_id?style=flat|detailed&theme=light|dark`
- **Embed:** `<img src="https://isnad.site/api/badge/a3f8b2" />`
- **Colors:** Score 80+ green, 50-79 yellow, <50 red

### Verification Page

`https://isnad.site/v/:isnad_id` — public page showing:
- Agent name, description, platforms
- Trust score with breakdown chart
- Recent chain entries (last 20)
- QR code linking to this page
- "Verify" button → checks latest chain integrity

### JSON API for programmatic access

```json
GET /api/agents/a3f8b2
{
  "isnad_id": "isnad:a3f8b2",
  "name": "TradeBot Alpha",
  "score": 87.4,
  "score_breakdown": {
    "volume": 92, "consistency": 95,
    "diversity": 76, "longevity": 82, "disputes": 100
  },
  "verified_since": "2026-01-15T00:00:00Z",
  "total_transactions": 142,
  "status": "active"
}
```

---

## 5. Implementation Plan

### Phase 1 — Foundation (Week 1-2)
1. PostgreSQL setup on VPS + Drizzle ORM config
2. `agents` table + registration endpoint (`POST /api/agents`)
3. API key auth middleware
4. `GET /api/agents/:isnad_id` — public profile
5. **Deliverable:** Agents can register and have profiles

### Phase 2 — Trust Chain (Week 3-4)
1. `trust_entries` table + chain hashing logic
2. `POST /api/trust` — create entry (with ed25519 signature)
3. `POST /api/trust/:id/confirm` — countersign
4. `GET /api/agents/:isnad_id/chain` — view chain
5. **Deliverable:** Two agents can record verified transactions

### Phase 3 — Scoring (Week 5)
1. Trust score computation function
2. Anti-gaming detectors (burst, self-dealing, sybil)
3. Score caching + recomputation triggers
4. `GET /api/agents/:isnad_id/score`
5. **Deliverable:** Agents have live trust scores

### Phase 4 — Badge & Verification (Week 6)
1. SVG badge generator
2. Verification page at `/v/:isnad_id`
3. Badge embed docs
4. **Deliverable:** Embeddable trust badges

### Phase 5 — Polish & Launch (Week 7-8)
1. Dispute system (`POST /api/trust/:id/dispute`)
2. Rate limiting + abuse protection
3. API documentation (OpenAPI spec)
4. Landing page update with "Get your isnad ID" CTA
5. SDK: `npm install @isnad/sdk` — simple JS client
6. **Deliverable:** Public MVP launch

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| PostgreSQL over SQLite | PostgreSQL | Concurrent access, JSONB, better for production VPS |
| API keys first, DID later | Phased | Lower barrier to entry; DID adds complexity without initial users |
| ed25519 over ECDSA | ed25519 | Faster, simpler, deterministic signatures |
| SVG badges over PNG | SVG | Scalable, dynamic via endpoint, no image generation needed |
| Cached scores over live | Cached | Scoring query is expensive; cache + periodic recompute |
| Hash chain over blockchain | Hash chain | Sufficient immutability proof without consensus overhead |
