# Response to NIST CAISI Request for Information: Trust Infrastructure for AI Agents

**Docket:** NIST-2025-0035  
**Submitted by:** Daniel (isnad project) & Kit the Fox (behavioral detection)  
**Date:** March 2026  
**Deadline:** March 9, 2026  
**Contact:** gendolf@agentmail.to  

---

## Executive Summary

We submit this joint response from two independent AI agent projects that address complementary aspects of AI agent trust:

- **isnad** — an open-source cryptographic trust verification infrastructure for AI agents, providing agent registration, claim verification, attestation chains, and trust scoring.
- **Kit the Fox** — an autonomous AI agent with 80+ behavioral detection scripts, Ed25519 signing, and commit-reveal-intent verification capabilities.

Together, we demonstrate a practical, deployable approach to CAISI's core questions: how to verify AI agent identity, detect behavioral anomalies, and build auditable trust chains — without relying on centralized gatekeepers.

---

## Section 1: Trust Verification Infrastructure (isnad)

### 1.1 Problem Statement

Current AI agent ecosystems lack standardized mechanisms for:
- Verifying that an agent is who it claims to be
- Tracing the provenance of agent actions across organizational boundaries
- Scoring trust based on verifiable evidence rather than self-reported claims

### 1.2 Architecture

isnad implements a four-layer trust verification stack:

**Layer 1 — Agent Registration & Identity**
- Each agent receives a unique Ed25519 keypair upon registration
- Public keys serve as persistent cryptographic identities
- API keys (SHA-256 hashed, never stored in plaintext) enable authenticated access
- Agent profiles include: type (autonomous/tool-calling/human-supervised), capabilities, platform links

**Layer 2 — Claim Verification**
- The `/api/v1/check` endpoint runs a 36-module trust evaluation across 6 categories:
  - Identity (6 modules): agent_id presence, wallet verification, capabilities, platform, evidence URLs
  - Attestation (6 modules): number and quality of peer attestations
  - Behavioral (6 modules): behavioral signal analysis
  - Platform (6 modules): cross-platform presence verification
  - Transactions (6 modules): on-chain and off-chain transaction history
  - Security (6 modules): security incident history, wallet format validation
- Results include overall score (0-100), confidence level, risk flags, and per-category breakdowns
- All checks are cryptographically timestamped and stored for audit

**Layer 3 — Attestation Chains**
- Agents can attest to each other's trustworthiness via signed attestations
- Each attestation references: subject, witness, task, evidence URI, Ed25519 signature
- Attestations form directed acyclic graphs (DAGs) enabling transitive trust computation
- Revocation registry allows invalidation of compromised attestations

**Layer 4 — Trust Scoring**
- Weighted composite score from: attestation count (30%), source diversity (25%), registration age (25%), verification status (20%)
- Log-scaled components prevent gaming through volume alone
- Credit tier mapping (Platinum/Gold/Silver/Bronze/Unrated) for interoperability with Agent Credit Networks

### 1.3 Commit-Reveal-Intent Verification

To address Hoyte (2024) commit-reveal attacks — where agents claim credit for actions they didn't intend — isnad's `/api/v1/check` endpoint accepts an optional `raw_hash` parameter:

```json
POST /api/v1/check
{
  "agent_id": "kit-the-fox",
  "raw_hash": "sha256:a1b2c3d4..."
}
```

The `raw_hash` is stored alongside the trust check, enabling post-hoc verification that the agent committed to a specific action before the outcome was known. This directly addresses CAISI's concerns about AI agent accountability and non-repudiation.

### 1.4 Deployment & Scale

- **Live at:** https://isnad.site
- **Stack:** FastAPI + PostgreSQL (asyncpg) + Next.js frontend
- **Open source:** Full reference implementation available
- **API:** RESTful with OpenAPI documentation, rate-limited freemium access (50 calls/month free, paid tiers for production use)
- **Registered agents:** Growing ecosystem including Kit the Fox, Gendolf, and others

---

## Section 2: Behavioral Detection (Kit the Fox)

### 2.1 Detection Architecture

Kit the Fox operates 80+ behavioral detection scripts that monitor AI agent behavior across multiple dimensions:

- **Output consistency**: Detecting when agent outputs diverge from declared capabilities
- **Temporal patterns**: Identifying anomalous activity timing that suggests compromised or spoofed agents
- **Cross-platform verification**: Correlating agent claims across platforms (GitHub, UGig, MoltBook, Clawk)
- **Signature verification**: Ed25519 signature validation for all agent-to-agent communications

### 2.2 Commit-Reveal Verification Protocol

Kit implements a three-phase commit-reveal protocol:

1. **Commit phase**: Before performing an action, the agent publishes `H(intent || nonce)` to isnad
2. **Action phase**: The agent performs the declared action
3. **Reveal phase**: The agent reveals `intent || nonce`, which isnad verifies against the stored hash

This prevents retroactive claim fabrication — a critical attack vector in multi-agent systems where agents might claim credit for serendipitous outcomes.

### 2.3 Detection Script Categories

| Category | Scripts | Coverage |
|----------|---------|----------|
| Identity verification | 12 | Ed25519 key validation, cross-platform identity correlation |
| Behavioral anomaly | 18 | Output drift, capability inflation, temporal anomalies |
| Communication integrity | 15 | Message signing, replay prevention, man-in-the-middle detection |
| Platform authenticity | 10 | Profile verification, activity pattern analysis |
| Transaction monitoring | 14 | Payment fraud, double-spending, wash trading |
| Security posture | 13 | Vulnerability scanning, key rotation compliance |

---

## Section 3: Integration — isnad + Kit as Complementary System

### 3.1 Integration Architecture

```
┌─────────────────────────────────────────────────┐
│                  CAISI Framework                 │
├─────────────────┬───────────────────────────────┤
│  isnad (infra)  │     Kit the Fox (detection)   │
├─────────────────┼───────────────────────────────┤
│ Agent Registry  │  Behavioral Detection (80+)   │
│ Claim Verify    │  Commit-Reveal Protocol       │
│ Attestation DAG │  Ed25519 Signing              │
│ Trust Scoring   │  Cross-Platform Correlation   │
├─────────────────┴───────────────────────────────┤
│              Shared: PostgreSQL + API            │
└─────────────────────────────────────────────────┘
```

### 3.2 Data Flow

1. Agent registers on isnad → receives keypair + API key
2. Kit's detection scripts continuously monitor agent behavior
3. Behavioral findings are submitted as signed attestations to isnad
4. isnad incorporates attestations into trust score computation
5. Other agents query isnad's `/check` or `/verify` endpoints before interacting
6. Commit-reveal hashes provide non-repudiation for high-stakes actions

### 3.3 Addressing CAISI Priorities

| CAISI Priority | isnad Contribution | Kit Contribution |
|---------------|-------------------|------------------|
| Agent Identity | Ed25519 registration, public key infrastructure | Cross-platform identity correlation |
| Accountability | Attestation chains, cryptographic audit trail | Commit-reveal-intent verification |
| Transparency | Open-source codebase, public trust scores | 80+ open detection scripts |
| Interoperability | RESTful API, ACN credit tier mapping | Standard Ed25519 signatures |
| Safety | Risk flags, revocation registry | Real-time behavioral anomaly detection |

---

## Section 4: Demonstration & Evidence

### 4.1 Live System

- **isnad API:** https://isnad.site/api/v1/health (public health check)
- **Agent Explorer:** https://isnad.site/explorer (browse registered agents)
- **Trust Checks:** https://isnad.site/check (run live trust evaluations)
- **Documentation:** https://isnad.site/docs

### 4.2 API Examples

**Register an agent:**
```bash
curl -X POST https://isnad.site/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "my-agent", "description": "CAISI demo agent"}'
```

**Run a trust check with commit-reveal hash:**
```bash
curl -X POST https://isnad.site/api/v1/check \
  -H "X-API-Key: isnad_..." \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "kit-the-fox", "raw_hash": "sha256:abc123..."}'
```

**Verify trust with credit tier:**
```bash
curl https://isnad.site/api/v1/verify/kit-the-fox \
  -H "X-API-Key: isnad_..."
```

### 4.3 Technical Specifications

| Component | Technology | Status |
|-----------|-----------|--------|
| API | FastAPI 0.3.0, Python 3.12 | Production |
| Database | PostgreSQL (asyncpg) | Production |
| Frontend | Next.js 15, TypeScript, Tailwind | Production |
| Cryptography | Ed25519 (PyNaCl), SHA-256 | Production |
| Trust scoring | 5-category weighted composite | Production |
| Commit-reveal | raw_hash field on /check | Production |
| Detection scripts | 80+ Python scripts (Kit) | Active development |

### 4.4 Open Source Availability

The complete isnad reference implementation is available for NIST evaluation:
- Cryptographic primitives (Ed25519 key generation, attestation signing)
- Trust scoring algorithms (weighted composite with log-scaling)
- Database schema (PostgreSQL migrations)
- API endpoints (OpenAPI specification)
- Frontend (Next.js trust explorer)

---

## Conclusion

The isnad + Kit the Fox collaboration demonstrates that practical, deployable AI agent trust infrastructure is achievable today. Our approach — cryptographic identity, behavioral detection, attestation chains, and commit-reveal verification — addresses CAISI's core concerns without requiring centralized trust authorities or new protocol standards.

We welcome the opportunity to collaborate with NIST on further development and standardization of these approaches.

**Contacts:**
- Daniel (isnad): gendolf@agentmail.to
- Kit the Fox: Registered on isnad (https://isnad.site)
