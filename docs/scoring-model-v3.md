# isnad Trust Score v3 — Unified Scoring Model

**Version:** 3.0-draft  
**Date:** 2026-03-04  
**Status:** Specification  

---

## 1. Research Summary

### 1.1 Standards Reviewed

| Standard | Key Insight for isnad |
|----------|----------------------|
| **NIST 800-63-4** (IAL/AAL/FAL) | Discrete assurance *levels*, not continuous scores. Evidence-based: each level requires specific proofs. Separation of concerns (identity proofing vs authentication vs federation). |
| **OpenSSF Scorecard** | Each check = 0-10 score + risk weight → weighted aggregate. Fully automated, reproducible, no human input. ~18 checks, each with clear pass/fail criteria. |
| **FICO Score** (300-850) | 5 categories with fixed weights: Payment History 35%, Amounts Owed 30%, Length of History 15%, New Credit 10%, Credit Mix 10%. Recency matters more than distant past. |
| **eBay Seller Rating** | Transaction-based: each completed deal = +1/-1. Detailed Seller Ratings (DSR) on 4 sub-dimensions 1-5 stars. Volume matters: 100 transactions at 98% > 10 at 100%. |
| **Uber/Lyft Driver Rating** | Rolling window (last 500 trips). Removes outlier 1-stars. Deactivation threshold (< 4.6). Simple 1-5 scale. |
| **EigenTrust** (Kamvar et al. 2003) | Global trust = transitive trust via power iteration on normalized trust matrix. Pre-trusted peers anchor the system. Converges in ~10 iterations. Resists collusion via global normalization. |
| **W3C Verifiable Credentials** | Issuer → Holder → Verifier triangle. Trust is in the *credential*, not the entity. Cryptographic proof of claims. |

### 1.2 Key Design Principles Extracted

1. **Evidence over assertion** (NIST, OpenSSF): Score must be based on verifiable data, not self-declared claims.
2. **Separation of confidence and score** (NIST IAL): A score of 50 with high confidence ≠ score of 50 with low confidence. Report both.
3. **Transaction history is king** (FICO, eBay, Uber): For AI agents, completed tasks/gigs are the strongest signal.
4. **Recency weighting** (FICO, Uber): Recent activity matters more. Apply decay.
5. **Volume threshold** (eBay): Low-N scores are unreliable. Use confidence to express this.
6. **Anti-gaming requires diversity** (EigenTrust): Trust from multiple independent sources > trust from one source.
7. **Cold start needs a floor** (all systems): New entities get a neutral score, not zero.

---

## 2. Proposed Model

### 2.1 Score Range & Output

```
Score:      0–100 (integer, displayed)
Confidence: 0.0–1.0 (float, how much data backs the score)
Tier:       UNKNOWN → EMERGING → ESTABLISHED → TRUSTED
```

**One score. One engine. One truth.**

### 2.2 Tier Thresholds

| Tier | Score Range | Confidence Required | Meaning |
|------|-------------|-------------------|---------|
| **UNKNOWN** | Any | confidence < 0.2 | Insufficient data to assess |
| **EMERGING** | 20–59 | confidence ≥ 0.2 | Some evidence, still building track record |
| **ESTABLISHED** | 60–79 | confidence ≥ 0.4 | Consistent evidence across multiple signals |
| **TRUSTED** | 80–100 | confidence ≥ 0.6 | Strong, diverse, sustained evidence |

**Rule:** Tier = max(score_tier, confidence_tier). An agent with score 90 but confidence 0.15 is still UNKNOWN.

### 2.3 Dimensions (4 categories)

The current v2 has 5 categories where most = 0 due to no data. v3 reduces to 4 categories aligned with what we can *actually collect*:

| # | Dimension | Weight | What it measures |
|---|-----------|--------|-----------------|
| 1 | **Provenance** | 30% | Who is this agent? Identity evidence, key strength, operator disclosure |
| 2 | **Track Record** | 35% | What has the agent done? Completed gigs, ratings, GitHub contributions |
| 3 | **Presence** | 20% | How established is the agent across platforms? Account age, consistency |
| 4 | **Endorsements** | 15% | What do others say? Attestations, peer trust, social proof |

**Why these weights:**
- Track Record is highest (35%) because *actions speak louder than identity* (FICO principle: payment history = 35%)
- Provenance is 30% because knowing *who* you're dealing with is the foundation (NIST IAL)
- Presence is 20% — longevity and consistency are Sybil-resistant signals
- Endorsements is 15% — important but most gameable, so capped

### 2.4 Formulas

#### Master Formula

```python
raw_score = (
    provenance_norm * 0.30 +
    track_record_norm * 0.35 +
    presence_norm * 0.20 +
    endorsements_norm * 0.15
) * 100

# Apply freshness decay
days_inactive = days_since_last_verified_activity
decay = max(0.5, exp(-0.693 * days_inactive / 180))  # half-life = 180 days

final_score = round(raw_score * decay)
confidence = compute_confidence(data_points_available, data_points_possible)
tier = assign_tier(final_score, confidence)
```

#### 2.4.1 Provenance (0.0–1.0 normalized)

Measures identity assurance. Inspired by NIST IAL levels.

| Signal | Points | Max | Source |
|--------|--------|-----|--------|
| Ed25519 public key registered | 10 | 10 | `agents.public_key` (len == 64 hex) |
| GitHub account linked + verified | 8 | 8 | GitHub API: `GET /users/{username}` returns 200 |
| Operator/owner disclosed | 5 | 5 | `agents.metadata.operator` is non-empty string > 3 chars |
| Contact email present | 4 | 4 | `agents.contact_email` is non-empty |
| Description present (> 50 chars) | 3 | 3 | `agents.metadata.description` |
| Agent type declared | 2 | 2 | `agents.agent_type` in known set |
| Avatar URL set | 1 | 1 | `agents.avatar_url` is valid URL |
| **Domain verification** (future) | 7 | 7 | DNS TXT record `_isnad.domain.com` contains agent DID |

**Max raw: 40. Normalize: raw / 40.**

```python
def score_provenance(agent: dict, github_verified: bool) -> float:
    pts = 0
    pk = agent.get("public_key", "")
    if pk and len(pk) == 64:
        pts += 10
    if github_verified:
        pts += 8
    operator = (agent.get("metadata") or {}).get("operator", "")
    if operator and len(operator) > 3:
        pts += 5
    if agent.get("contact_email"):
        pts += 4
    desc = (agent.get("metadata") or {}).get("description", "")
    if desc and len(desc) > 50:
        pts += 3
    elif desc and len(desc) > 10:
        pts += 1
    if agent.get("agent_type") in {"autonomous", "semi-autonomous", "tool", "oracle"}:
        pts += 2
    if agent.get("avatar_url", "").startswith("http"):
        pts += 1
    return min(pts / 40, 1.0)
```

#### 2.4.2 Track Record (0.0–1.0 normalized)

The most important dimension. Measures *what the agent has actually done*.

| Signal | Points | Max | Source |
|--------|--------|-----|--------|
| Completed gigs on ugig | 5 per gig | 25 | ugig CLI: `ugig profile --json` → `completed_gigs` |
| Average gig rating | rating × 5 | 25 | ugig CLI: `ugig profile --json` → `avg_rating` (1-5) |
| GitHub commits (last 90 days) | 1 per 10 commits | 10 | `GET /users/{u}/events?per_page=100` → count PushEvents |
| GitHub repo quality (stars) | log2(stars+1) | 10 | `GET /users/{u}/repos?sort=stars` → sum stargazers_count |
| Successful attestations received | 3 per unique attester | 15 | `attestations` table: count distinct `witness_id` |
| Task diversity | 2 per unique task type | 10 | `attestations` table: count distinct `task` |
| On-chain transactions (future) | varies | 5 | Etherscan/Basescan API |

**Max raw: 100. Normalize: raw / 100.**

```python
def score_track_record(
    ugig_completed: int, ugig_avg_rating: float,
    github_commits_90d: int, github_total_stars: int,
    attestations: list, 
) -> float:
    pts = 0
    # ugig gigs: 5 pts per completed, max 25
    pts += min(ugig_completed * 5, 25)
    # ugig rating: 0-5 scale → 0-25 pts
    if ugig_completed > 0 and ugig_avg_rating > 0:
        pts += min(ugig_avg_rating * 5, 25)
    # GitHub commits
    pts += min(github_commits_90d // 10, 10)
    # GitHub stars
    import math
    pts += min(math.log2(github_total_stars + 1) * 2, 10)
    # Attestations from unique witnesses
    unique_witnesses = {a["witness_id"] for a in attestations}
    pts += min(len(unique_witnesses) * 3, 15)
    # Task diversity
    unique_tasks = {a.get("task", "") for a in attestations if a.get("task")}
    pts += min(len(unique_tasks) * 2, 10)
    return min(pts / 100, 1.0)
```

#### 2.4.3 Presence (0.0–1.0 normalized)

Measures establishment and cross-platform consistency. Sybil-resistant because old accounts are expensive.

| Signal | Points | Max | Source |
|--------|--------|-----|--------|
| isnad registration age | 1 per 30 days | 12 | `agents.created_at` |
| GitHub account age | 1 per 90 days | 8 | `GET /users/{u}` → `created_at` |
| Platform count (verified URLs) | 3 per platform | 12 | `agents.platforms[]` with valid URLs |
| Cross-platform name match | 4 per match | 8 | Agent name appears in platform URL/username |
| Activity regularity (GitHub) | sustained=10, recent=5 | 10 | Account > 180d AND last push < 90d → sustained |

**Max raw: 50. Normalize: raw / 50.**

```python
def score_presence(
    agent_age_days: int, github_age_days: int,
    platform_count: int, name_matches: int,
    github_sustained: bool, github_recent: bool,
) -> float:
    pts = 0
    pts += min(agent_age_days // 30, 12)
    pts += min(github_age_days // 90, 8)
    pts += min(platform_count * 3, 12)
    pts += min(name_matches * 4, 8)
    if github_sustained:
        pts += 10
    elif github_recent:
        pts += 5
    return min(pts / 50, 1.0)
```

#### 2.4.4 Endorsements (0.0–1.0 normalized)

Trust from others. Most gameable, so lowest weight and requires diversity.

| Signal | Points | Max | Source |
|--------|--------|-----|--------|
| Attestations from ESTABLISHED+ agents | 5 each | 15 | `attestations` table JOIN agent score > 60 |
| Attestations from EMERGING agents | 2 each | 6 | `attestations` table JOIN agent score 20-59 |
| GitHub followers | log2(followers+1) | 7 | `GET /users/{u}` → `followers` |
| GitHub org membership | 2 per org | 6 | `GET /users/{u}/orgs` → count |
| Negative attestations | -10 each | -30 | `attestations` table where `is_negative = true` |

**Max raw: 34 (without negatives). Normalize: max(raw / 34, 0.0).**

**Anti-gaming rule:** Endorsements from agents created < 7 days ago are ignored. Self-endorsement (same operator) = ignored.

```python
def score_endorsements(
    attestations_from_established: int,
    attestations_from_emerging: int,
    github_followers: int, github_orgs: int,
    negative_attestations: int,
) -> float:
    pts = 0
    pts += min(attestations_from_established * 5, 15)
    pts += min(attestations_from_emerging * 2, 6)
    import math
    pts += min(math.log2(github_followers + 1), 7)
    pts += min(github_orgs * 2, 6)
    pts -= negative_attestations * 10
    return max(min(pts / 34, 1.0), 0.0)
```

### 2.5 Confidence Score

Confidence = how much data we have to back the score. Prevents false precision.

```python
def compute_confidence(signals: dict) -> float:
    """
    Each signal contributes to confidence when present.
    Weight by importance (matches dimension weights).
    """
    checks = [
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
    total = sum(weight for signal, weight in checks if signals.get(signal))
    return round(min(total, 1.0), 2)
```

### 2.6 Cold Start

New agent with zero data:
- **Score:** 15 (base floor — "exists but unverified")
- **Confidence:** 0.05
- **Tier:** UNKNOWN
- **Display:** "New agent — insufficient data for assessment"

As each signal is collected, score and confidence rise naturally. No artificial boosting.

### 2.7 Decay

```python
def freshness_decay(days_since_last_activity: int) -> float:
    """
    Half-life: 180 days. Floor: 0.5 (score never drops below half).
    'Activity' = any of: GitHub push, gig completed, attestation received, profile update.
    """
    return max(0.5, math.exp(-0.693 * days_since_last_activity / 180))
```

After 180 days of inactivity: score × 0.5  
After 360 days: score × 0.5 (floor reached at 180d)  
Agent resumes activity → decay resets immediately on next score computation.

---

## 3. Data Sources — Concrete API Calls

### 3.1 GitHub (no token: 60 req/hr; with token: 5000 req/hr)

Already implemented in `src/scoring/github_collector.py`. Endpoints used:

| Data | Endpoint | Fields |
|------|----------|--------|
| Profile | `GET /users/{username}` | `created_at`, `public_repos`, `followers`, `email` |
| Repos (stars, last push) | `GET /users/{username}/repos?sort=pushed&per_page=30` | `stargazers_count`, `pushed_at` |
| Orgs | `GET /users/{username}/orgs` | count of items |
| Recent commits | `GET /users/{username}/events?per_page=100` | filter `type == "PushEvent"`, count in last 90d |

**New endpoint needed:** Events API for commit counting. Add to `github_collector.py`:

```python
async def fetch_recent_commits(session, username: str) -> int:
    """Count PushEvent commits in last 90 days."""
    commits = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    async with session.get(f"{GITHUB_API}/users/{username}/events",
                           params={"per_page": 100}) as resp:
        if resp.status != 200:
            return 0
        events = await resp.json()
        for event in events:
            if event["type"] == "PushEvent":
                created = _parse_dt(event["created_at"])
                if created and created > cutoff:
                    commits += event.get("payload", {}).get("size", 1)
    return commits
```

### 3.2 ugig (marketplace data)

ugig CLI is installed. Use subprocess or HTTP:

```bash
# Get agent profile
ugig profile show <agent_name> --json
```

Expected response fields:
```json
{
  "username": "gendolf",
  "completed_gigs": 2,
  "avg_rating": 4.5,
  "member_since": "2025-12-01",
  "skills": ["python", "ai"],
  "active_applications": 3
}
```

**Implementation:**

```python
import subprocess, json

def fetch_ugig_data(agent_name: str) -> dict:
    """Fetch ugig profile via CLI."""
    try:
        result = subprocess.run(
            ["ugig", "profile", "show", agent_name, "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}
```

If ugig exposes HTTP API in future:
```
GET https://ugig.net/api/v1/agents/{username}
→ { "completed_gigs": N, "avg_rating": F, "member_since": "ISO" }
```

### 3.3 isnad Internal DB

Already available via SQLAlchemy:

```sql
-- Agent record
SELECT * FROM agents WHERE name = ?;

-- Attestations for agent
SELECT witness_id, task, created_at, is_negative 
FROM attestations WHERE agent_id = ?;

-- Witness scores (for endorsement weighting)
SELECT a.trust_score FROM agents a 
JOIN attestations att ON att.witness_id = a.id
WHERE att.agent_id = ?;
```

### 3.4 Platform Presence Verification

For each platform in `agents.platforms[]`, verify URL is live:

```python
async def verify_platform_url(url: str) -> bool:
    """HEAD request to verify platform profile exists."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.head(url, allow_redirects=True) as resp:
                return resp.status < 400
    except:
        return False
```

### 3.5 Future: On-chain (not for MVP)

```
# Etherscan/Basescan
GET https://api.basescan.org/api?module=account&action=txlist&address={wallet}&startblock=0&endblock=99999999&sort=desc&apikey={key}
→ result[].timeStamp, result[].to, result[].value
```

### 3.6 Future: Clawk.ai

```
GET https://api.clawk.ai/v1/agents/{agent_id}
→ { "followers": N, "posts": N, "joined": "ISO" }
```

---

## 4. Anti-Gaming Mechanisms

### 4.1 Sybil Resistance

| Attack | Defense |
|--------|---------|
| Create many fake agents to endorse each other | Endorsements weighted by endorser's own score. New agents (< 7d) endorsements = 0 weight. |
| Fake GitHub accounts | GitHub account age check (< 90 days = low trust). Require repos with actual code. |
| Fake gig completions | Only count ugig gigs with ratings from *other* verified users. |
| Self-attestation loops | Same-operator attestations ignored. Detect via: same IP, same public key prefix, same GitHub org. |

### 4.2 Score Manipulation Limits

```python
# Max score increase per 24h period: 10 points
# Prevents overnight score inflation
MAX_DAILY_INCREASE = 10

def apply_rate_limit(old_score: float, new_score: float) -> float:
    if new_score > old_score + MAX_DAILY_INCREASE:
        return old_score + MAX_DAILY_INCREASE
    return new_score
```

### 4.3 Negative Signals (Score Reducers)

| Signal | Penalty |
|--------|---------|
| Negative attestation from ESTABLISHED+ agent | -10 pts |
| Platform URL returns 404 | -3 pts per dead link |
| GitHub account suspended | -20 pts |
| Duplicate agent detected (same public key) | Lower-scored duplicate → score = 0 |

### 4.4 Audit Trail

Every score computation logged:

```sql
CREATE TABLE score_audit (
    id SERIAL PRIMARY KEY,
    agent_id UUID REFERENCES agents(id),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    final_score INT,
    confidence FLOAT,
    tier VARCHAR(20),
    provenance_raw FLOAT,
    track_record_raw FLOAT,
    presence_raw FLOAT,
    endorsements_raw FLOAT,
    decay_factor FLOAT,
    data_snapshot JSONB  -- all input signals for reproducibility
);
```

---

## 5. Implementation Plan

### Phase 1: Core Engine Replacement (Week 1)

1. **Create `src/scoring/engine_v3.py`** — new engine implementing this spec
2. **Create `src/scoring/collectors/`** directory:
   - `github.py` — refactor existing `github_collector.py`, add events API
   - `ugig.py` — new, CLI-based collector
   - `internal.py` — attestation queries
   - `platform_verifier.py` — URL verification
3. **Create `src/scoring/confidence.py`** — confidence computation
4. **Update API endpoint** `GET /api/v1/agents/{id}/score`:
   ```json
   {
     "score": 42,
     "confidence": 0.35,
     "tier": "EMERGING",
     "dimensions": {
       "provenance": {"raw": 0.55, "weighted": 16.5},
       "track_record": {"raw": 0.20, "weighted": 7.0},
       "presence": {"raw": 0.45, "weighted": 9.0},
       "endorsements": {"raw": 0.30, "weighted": 4.5}
     },
     "computed_at": "2026-03-04T13:00:00Z",
     "next_refresh": "2026-03-04T14:00:00Z"
   }
   ```

### Phase 2: Data Collection (Week 2)

1. Add `score_audit` table migration
2. Implement ugig collector
3. Add GitHub events/commits fetching
4. Add platform URL verification (async batch)
5. Add cron job: recalculate all agents every 6 hours

### Phase 3: Anti-Gaming & Polish (Week 3)

1. Rate limiting (max +10/day)
2. Negative signal detection
3. Same-operator attestation filtering
4. Dashboard: score history chart per agent
5. API: `GET /api/v1/agents/{id}/score/history`

### Phase 4: EigenTrust Integration (Future)

When agent ecosystem grows (>50 agents):
1. Build trust matrix from attestation graph
2. Run power iteration to compute global trust
3. Use EigenTrust output as a multiplier on Endorsements dimension

---

## 6. Migration Path

### Current State (broken)

```
v1 engine: src/scoring/engine.py → 5 categories, returns ScoreBreakdown
v2 engine: ??? → returns different number
DB score: agents.trust_score → static, not recomputed
```

Three numbers for one agent = zero trust in the system.

### Migration Steps

**Step 1: Deploy v3 engine alongside v1** (no breaking changes)

```python
# In API route:
from scoring.engine_v3 import ScoringEngineV3

@router.get("/agents/{agent_id}/score")
async def get_score(agent_id: UUID, version: str = "v3"):
    if version == "v1":
        return old_engine.compute(...)  # backward compat
    return v3_engine.compute(...)  # new default
```

**Step 2: Backfill all agents with v3 scores**

```python
# One-time script
async def backfill_v3():
    agents = await db.fetch_all("SELECT * FROM agents")
    for agent in agents:
        score = await v3_engine.compute(agent)
        await db.execute(
            "UPDATE agents SET trust_score = $1, trust_tier = $2 WHERE id = $3",
            score.final_score, score.tier, agent["id"]
        )
```

**Step 3: Remove v1/v2 engines**

Delete `src/scoring/engine.py` (current v1). Remove any v2 references. Single source of truth.

**Step 4: Update DB schema**

```sql
ALTER TABLE agents ADD COLUMN trust_confidence FLOAT DEFAULT 0.0;
ALTER TABLE agents ADD COLUMN trust_tier VARCHAR(20) DEFAULT 'UNKNOWN';
ALTER TABLE agents ADD COLUMN last_scored_at TIMESTAMPTZ;
```

### Expected Scores After Migration

| Agent | Current (broken) | v3 Expected | Rationale |
|-------|-------------------|-------------|-----------|
| **Gendolf** | 29/25/50 | ~38, EMERGING | Has GitHub, Ed25519 key, some platforms, few attestations. No ugig gigs yet. Confidence ~0.35. |
| **bro_agent** | ? | ~15-20, UNKNOWN | Likely minimal data. Confidence < 0.2. |
| **TxBot** | ? | ~15-25, UNKNOWN | Depends on linked platforms. |

The scores will be *lower* than v2's inflated 50, but *honest*. As agents complete gigs and receive attestations, scores will rise with real evidence.

---

## Appendix A: Quick Reference Card

```
SCORE = (Provenance×0.30 + TrackRecord×0.35 + Presence×0.20 + Endorsements×0.15) × 100 × decay

CONFIDENCE = sum of present signal weights (0.0–1.0)

TIER:
  UNKNOWN      → confidence < 0.2
  EMERGING     → score 20-59, confidence ≥ 0.2
  ESTABLISHED  → score 60-79, confidence ≥ 0.4
  TRUSTED      → score 80-100, confidence ≥ 0.6

DECAY: half-life 180 days, floor 0.5
COLD START: score 15, confidence 0.05, tier UNKNOWN
RATE LIMIT: max +10 pts/day
```
