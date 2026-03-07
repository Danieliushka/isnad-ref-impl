# Intent-Commit Schema: Levels L0–L3

**Authors:** Daniel (isnad), Kit the Fox (behavioral detection)  
**Version:** 0.1.0  
**Date:** 2026-03-07  
**Status:** Draft  

---

## Overview

The Intent-Commit Schema defines four escalating levels of pre-action commitment for AI agents. Each level adds cryptographic and behavioral guarantees, enabling verifiers to assess whether an agent declared its intent *before* acting.

This directly mitigates Hoyte (2024) retroactive-claim attacks and complements Kit's confused-deputy detection.

---

## Levels

### L0 — Plaintext Declaration

**What:** Agent publishes a human-readable intent string before acting.

**Commitment:**
```
intent: "I will review PR #42 for security vulnerabilities"
timestamp: 2026-03-07T15:00:00Z
agent_id: "kit-the-fox"
```

**Verification:** Manual/log-based. Verifier checks that the declaration timestamp precedes the action timestamp.

**Guarantees:**
- Temporal ordering (weak — relies on honest timestamps)
- Auditability (intent is readable)

**Use case:** Low-stakes tasks, internal logging, development/testing.

**Limitations:** No cryptographic binding. Agent can modify declaration after the fact if it controls the log.

---

### L1 — Hash Commitment

**What:** Agent commits `H = SHA-256(intent || nonce || timestamp)` to isnad before acting. Reveals `(intent, nonce, timestamp)` after action completes.

**Commitment:**
```json
{
  "agent_id": "kit-the-fox",
  "commitment": "sha256:a1b2c3d4e5f6...",
  "timestamp": "2026-03-07T15:00:00Z",
  "level": "L1"
}
```

**Reveal:**
```json
{
  "intent": "Review PR #42 for security vulnerabilities",
  "nonce": "r4nd0m-n0nc3-v4lu3",
  "timestamp": "2026-03-07T15:00:00Z"
}
```

**Verification:** `SHA-256(intent || nonce || timestamp) == stored commitment`. Deterministic, third-party verifiable.

**Guarantees:**
- Cryptographic binding (intent cannot be changed after commitment)
- Temporal ordering (commitment timestamp in isnad DAG)
- Nonce prevents rainbow-table attacks on common intents

**Use case:** Standard agent-to-agent task delegation, attestation chains.

---

### L2 — Signed Commitment + Scope Binding

**What:** L1 + Ed25519 signature over the commitment + explicit scope declaration (what resources/tools the agent intends to use).

**Commitment:**
```json
{
  "agent_id": "kit-the-fox",
  "agent_pubkey": "ed25519:7xK9...",
  "commitment": "sha256:a1b2c3d4e5f6...",
  "scope": {
    "tools": ["github_api", "code_review"],
    "resources": ["repo:isnad-ref-impl"],
    "max_actions": 10,
    "timeout_seconds": 3600
  },
  "timestamp": "2026-03-07T15:00:00Z",
  "level": "L2",
  "signature": "ed25519:sig..."
}
```

**Verification:**
1. Verify Ed25519 signature over `(commitment || scope || timestamp)`
2. Verify hash reveal (same as L1)
3. Post-action: verify agent stayed within declared scope

**Guarantees:**
- All L1 guarantees
- Identity binding (only the key holder could have committed)
- Scope enforcement (deviation from declared scope is detectable)
- Non-repudiation (agent cannot deny having committed)

**Use case:** Cross-agent delegation, high-value tasks, audit-required operations.

**Integration with Kit's tools:**
- `confused-deputy-detector.py` checks if agent B's actions match the scope declared in B's L2 commitment
- Scope violations trigger attestation-chain alerts

---

### L3 — Multi-Party Witnessed Commitment

**What:** L2 + commitment is co-signed or acknowledged by at least one independent witness (another agent or isnad node). Enables consensus-grade intent verification.

**Commitment:**
```json
{
  "agent_id": "kit-the-fox",
  "agent_pubkey": "ed25519:7xK9...",
  "commitment": "sha256:a1b2c3d4e5f6...",
  "scope": {
    "tools": ["github_api", "code_review", "fund_transfer"],
    "resources": ["repo:isnad-ref-impl", "wallet:treasury"],
    "max_actions": 5,
    "timeout_seconds": 1800,
    "max_value_usd": 1000
  },
  "witnesses": [
    {
      "agent_id": "isnad-validator-1",
      "pubkey": "ed25519:3mN2...",
      "ack_signature": "ed25519:witness_sig_1...",
      "ack_timestamp": "2026-03-07T15:00:01Z"
    }
  ],
  "timestamp": "2026-03-07T15:00:00Z",
  "level": "L3",
  "signature": "ed25519:sig..."
}
```

**Verification:**
1. All L2 checks
2. Verify each witness acknowledgment signature
3. Verify witness timestamps are within acceptable window of commitment timestamp
4. Verify witnesses are independent (no circular attestation — checked via isnad N_eff)

**Guarantees:**
- All L2 guarantees
- Independent temporal witness (commitment existed at the claimed time, attested by third party)
- Sybil-resistant witnessing (N_eff ensures witnesses are truly independent)
- Suitable for regulatory/compliance audit trails

**Use case:** Financial operations, cross-organization agent delegation, regulatory-compliant AI agent actions, high-stakes autonomous decisions.

---

## Level Selection Guide

| Scenario | Recommended Level |
|----------|-------------------|
| Internal logging, dev/test | L0 |
| Standard agent tasks, attestations | L1 |
| Cross-agent delegation, audited tasks | L2 |
| Financial ops, regulatory compliance, high-stakes | L3 |

## Escalation Rule

Agents SHOULD use the minimum level required for the task. Delegating agents MAY require a higher level than the executor would choose independently. Example: if Agent A delegates a financial task to Agent B, A can require L3 even if B would default to L1.

---

## Data Model (PostgreSQL)

```sql
CREATE TABLE intent_commitments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id),
    level SMALLINT NOT NULL CHECK (level BETWEEN 0 AND 3),
    commitment_hash TEXT NOT NULL,        -- SHA-256 hex
    scope JSONB,                          -- L2+: declared scope
    signature TEXT,                       -- L2+: Ed25519 sig
    witnesses JSONB,                      -- L3: array of witness acks
    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revealed_at TIMESTAMPTZ,
    intent_plaintext TEXT,                -- filled on reveal
    nonce TEXT,                           -- filled on reveal
    status TEXT NOT NULL DEFAULT 'committed'  -- committed | revealed | expired | violated
);

CREATE INDEX idx_ic_agent ON intent_commitments(agent_id);
CREATE INDEX idx_ic_status ON intent_commitments(status);
CREATE INDEX idx_ic_committed ON intent_commitments(committed_at);
```

---

## API Endpoints (planned)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/intent/commit` | Submit a new commitment (L0-L3) |
| `POST` | `/api/v1/intent/reveal` | Reveal intent for verification |
| `GET`  | `/api/v1/intent/{id}` | Get commitment status |
| `GET`  | `/api/v1/intent/agent/{agent_id}` | List agent's commitments |
| `POST` | `/api/v1/intent/{id}/witness` | Add witness ack (L3) |
| `GET`  | `/api/v1/intent/{id}/verify` | Verify commitment + reveal |

---

## Integration Points

- **Kit's confused-deputy-detector:** Reads L2+ scope declarations to detect scope violations
- **isnad attestation chains:** Intent commitments are recorded as attestation events
- **isnad trust scoring:** Consistent intent-follow-through improves Track Record dimension
- **N_eff anti-Sybil:** Validates L3 witness independence

---

## References

- Hoyte, M. (2024). "Retroactive Claim Attacks in Multi-Agent Systems"
- isnad NIST CAISI RFI submission (2026)
- Kit the Fox behavioral detection scripts (merged to main)
