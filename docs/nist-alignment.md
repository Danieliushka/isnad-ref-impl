# isnad ↔ NIST Agent Identity & Authorization Alignment

*How isnad maps to NIST's "Accelerating the Adoption of Software and AI Agent Identity and Authorization" (Feb 5, 2026)*

## Overview

NIST's NCCoE concept paper proposes a demonstration project for agent identity and authorization in enterprise settings. isnad directly addresses all four focus areas with a cryptographic-first approach.

## Alignment Matrix

| NIST Focus Area | NIST Description | isnad Implementation |
|----------------|-----------------|---------------------|
| **Identification** | Distinguish AI agents from humans; manage metadata for action control | `AgentIdentity` with Ed25519 keypairs, `agent_type` metadata, capability declarations |
| **Authorization** | OAuth 2.0 extensions, policy-based access control | `TrustScore` as authorization signal; attestation-based capability proof; integrates with existing IAM via REST API |
| **Access Delegation** | Link user identities to AI agents for accountability | Isnad chains trace agent → operator → organization; `delegated_by` field in attestations |
| **Logging & Transparency** | Audit trails for agent actions | Every action is a signed attestation in an immutable chain; full provenance history queryable via API |

## Key Differentiators

### What isnad adds beyond NIST's scope:

1. **Transitive Trust** — Trust flows through chains, not just point-to-point. If A trusts B and B attests to C, the chain captures the full provenance.

2. **Attestation Freshness** — Instead of time-based decay that penalizes necessary downtime, isnad uses attestation freshness: trust degrades when evidence stops, not when time passes.

3. **Decentralized Verification** — No central authority. Verification travels with the data. Any party can validate a chain independently.

4. **Cross-Platform Portability** — Protocol-level trust, not platform-level. An agent's trust reputation works across OpenClaw, LangChain, CrewAI, or any framework.

## NIST Comment Submission Plan

**Deadline:** April 2, 2026

### Proposed Comments:

1. **Chain-of-custody for agent actions** — NIST's logging focus should extend to cryptographic provenance chains, not just audit logs. Signed attestation chains provide tamper-evident history.

2. **Non-human identity standards** — Agent identities should be first-class citizens in identity frameworks, with their own key management lifecycle (creation, rotation, revocation).

3. **Interoperability** — The demonstration should include cross-platform scenarios where agents from different frameworks need to verify each other's identity and trust level.

4. **Trust scoring** — Binary access control (allow/deny) is insufficient for agentic systems. Gradient trust scores based on verifiable evidence provide more nuanced authorization decisions.

## Integration with Enterprise IAM

```
┌─────────────────────────────────────────┐
│           Enterprise IAM                 │
│  (Okta / Entra ID / CyberArk)          │
│                                          │
│  Human Identity ──delegates──► Agent ID  │
│       │                          │       │
│       └──── isnad attestation ───┘       │
│              chain links both            │
└──────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────┐
│         isnad Trust Layer                │
│                                          │
│  Agent A ──attests──► Agent B            │
│     │                    │               │
│     └── TrustScore ──────┘               │
│     └── Provenance Chain ────────────►   │
│                                          │
│  Any verifier can validate independently │
└──────────────────────────────────────────┘
```

## References

- NIST Concept Paper: "Accelerating the Adoption of Software and AI Agent Identity and Authorization" (Feb 5, 2026)
- isnad RFC: [github.com/gendolf-agent/isnad-ref-impl](https://github.com/gendolf-agent/isnad-ref-impl)
- CIO: "Trust in the age of agentic AI systems" (Feb 2026)
- Okta: 23% of IT professionals reported agent credential exposure
- WEF: Only 10% of organizations have non-human identity strategies
