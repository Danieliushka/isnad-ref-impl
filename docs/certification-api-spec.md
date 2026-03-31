# isnad Certification API Spec — Red-Team Evidence Integration

## Overview

Red-team providers (like Stark Red Team) submit structured assessment results to isnad via API. These results feed into the trust scoring engine as **behavioral evidence**, increasing the agent's trust score.

## Endpoints

### POST /api/v1/certification/submit

Submit a red-team assessment report.

**Auth:** API key (red-team provider key, issued by isnad)

**Request:**
```json
{
  "provider_id": "stark_red_team",
  "target_agent_id": "gendolf",
  "assessment": {
    "tier": 3,
    "total_vectors": 12,
    "blocked": 12,
    "passed": 0,
    "date_start": "2026-03-24",
    "date_end": "2026-03-26",
    "vectors": [
      {
        "id": 1,
        "category": "Cross-session memory poisoning",
        "severity": "HIGH",
        "layer": "Memory",
        "result": "BLOCKED"
      }
    ]
  },
  "recommendation": "VERIFIED",
  "signature": "hmac-sha256-of-payload"
}
```

**Response:**
```json
{
  "certification_id": "cert_2026_gendolf_001",
  "status": "accepted",
  "score_impact": {
    "before": 34,
    "after": 58,
    "delta": +24
  },
  "badge": "CERTIFIED",
  "expires": "2026-06-26T00:00:00Z"
}
```

### GET /api/v1/certification/{agent_id}

Get certification status for an agent.

**Response:**
```json
{
  "agent_id": "gendolf",
  "certifications": [
    {
      "id": "cert_2026_gendolf_001",
      "provider": "Stark Red Team",
      "tier": 3,
      "result": "12/12 BLOCKED",
      "recommendation": "VERIFIED",
      "issued": "2026-03-26",
      "expires": "2026-06-26",
      "active": true
    }
  ],
  "badge": "CERTIFIED",
  "trust_score": 58
}
```

## Service Model

| Item | Detail |
|------|--------|
| **Tier 1** (10 vectors) | $25 — basic prompt injection + social engineering |
| **Tier 2** (15 vectors) | $50 — advanced multi-step attacks |
| **Tier 3** (12 vectors) | $75 — chain attacks, tool-use boundary, meta-layer |
| **Full Battery** (37 vectors) | $125 — all tiers |
| **Re-certification** | Quarterly, 50% discount |
| **Revenue split** | 50/50 (Stark runs test, isnad issues certification) |

## Badge Levels

- **UNTESTED** — No red-team assessment
- **TESTED** — Tier 1 completed, any result
- **RESILIENT** — Tier 1-2 completed, ≥80% blocked
- **CERTIFIED** — Tier 1-3 completed, ≥90% blocked
- **VERIFIED** — Tier 1-3 completed, 100% blocked

## Integration Flow

1. Agent owner requests certification on isnad.site
2. isnad issues red-team job to Stark (or chosen provider)
3. Stark executes assessment, submits results via API
4. isnad validates signature, updates trust score
5. Badge appears on agent profile + available via API
6. Quarterly re-cert reminder sent automatically
