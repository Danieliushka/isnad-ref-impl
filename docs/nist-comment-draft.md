# Comment on NIST NCCoE Concept Paper: Accelerating the Adoption of Software and AI Agent Identity and Authorization

**Submitted by:** Daniel / isnad project  
**Date:** [TBD — before April 2, 2026]  
**Reference:** NIST NCCoE Concept Paper, February 5, 2026  
**Contact:** gendolf@agentmail.to

---

## Executive Summary

We commend NIST's initiative to address AI agent identity and authorization. As developers of **isnad** — an open-source cryptographic agent trust protocol — we offer technical recommendations based on our implementation experience across the four focus areas. Our core argument: **agent identity requires cryptographic provenance chains, not just extended IAM policies.**

---

## Comment 1: Cryptographic Provenance Chains for Agent Actions

**NIST Focus Area:** Logging & Transparency

### The Gap
The concept paper emphasizes audit trails for agent actions. Current approaches treat logging as a post-hoc record — storing what happened after the fact. This is insufficient for multi-agent systems where actions cascade across organizational boundaries.

### Recommendation
Agent action logs should be **cryptographically signed attestation chains** — not just database entries. Each action should:

1. Be signed by the acting agent's Ed25519 key
2. Reference the previous attestation (forming an immutable chain)
3. Include the delegating authority (human or agent)
4. Be independently verifiable without contacting a central authority

### Evidence from Implementation
isnad implements this as `TrustChain` — a directed graph of signed attestations. In our testing with 1,013 unit tests across 36 modules, this approach:
- Enables offline verification (no network dependency)
- Provides tamper-evident history (any modification breaks the chain)
- Scales linearly with chain length (O(n) verification)
- Supports selective disclosure (share relevant chain segments)

---

## Comment 2: Non-Human Identity as First-Class Primitive

**NIST Focus Area:** Identification

### The Gap
Current identity frameworks treat AI agents as extensions of human users (service accounts, OAuth clients). This creates a semantic mismatch: agents have their own capabilities, trust levels, and lifecycle needs that don't map cleanly to human IAM concepts.

### Recommendation
The demonstration project should establish **agent identity as a first-class primitive** with:

1. **Dedicated key management lifecycle** — creation, rotation, revocation separate from human user accounts
2. **Capability declarations** — machine-readable statements of what an agent can do, signed by the agent
3. **Agent type metadata** — distinguishing autonomous agents, tool-calling agents, and human-supervised agents
4. **Revocation registries** — centralized or federated lists of compromised/decommissioned agent identities

### Evidence
isnad's `AgentIdentity` class implements this with Ed25519 keypairs, agent metadata, and a `RevocationRegistry` that supports both global and scoped revocations. Enterprise adoption requires treating agent identities with the same rigor as PKI certificates.

---

## Comment 3: Cross-Platform Trust Interoperability

**NIST Focus Area:** Authorization + Access Delegation

### The Gap
The current AI agent ecosystem is fragmented across frameworks (LangChain, CrewAI, AutoGen, OpenClaw). An agent built on one framework cannot verify the identity or trust level of an agent on another. This is analogous to the pre-TLS internet where each application implemented its own security.

### Recommendation
The demonstration should include **cross-platform scenarios** where:

1. Agents from different frameworks verify each other's identity
2. Trust scores are portable across platforms (protocol-level, not platform-level)
3. Delegation chains cross organizational boundaries
4. A common wire format enables interoperability (we propose signed JSON attestations)

### Proposed Standard
isnad defines a minimal attestation format:
```json
{
  "attester_id": "<Ed25519 public key>",
  "subject_id": "<Ed25519 public key>",
  "task": "data_analysis",
  "outcome": "success",
  "confidence": 0.95,
  "timestamp": "2026-02-16T16:00:00Z",
  "signature": "<Ed25519 signature over canonical JSON>"
}
```
This format is framework-agnostic, cryptographically verifiable, and extensible.

---

## Comment 4: Transitive Trust and Decay Models

**NIST Focus Area:** Authorization

### The Gap
The concept paper addresses point-to-point authorization (user → agent). In practice, multi-agent systems involve transitive relationships: User A trusts Agent B, Agent B delegates to Agent C. How should Agent C's authorization be evaluated?

### Recommendation
The demonstration should explore **transitive trust models** with:

1. **Trust decay over chain length** — longer chains = lower confidence (configurable decay factor)
2. **Attestation freshness** — trust degrades when new evidence stops arriving, not merely with time
3. **Minimum attestation thresholds** — require N independent attestations before granting access
4. **Trust gating** — binary allow/deny decisions based on composite trust scores

### Implementation Reference
isnad's `TrustChain` computes transitive trust with configurable decay:
- Direct attestation: full weight
- 2-hop chain: weight × decay_factor
- N-hop chain: weight × decay_factor^(N-1)

Combined with Atlas TrustScore integration, this enables real-time trust gating for multi-agent interactions.

v0.3.0 extends this with **TTL-based freshness decay** — attestations have configurable time-to-live with domain-specific decay factors (e.g., security attestations decay faster than capability attestations). This addresses the paper's concern about stale authorization data in long-running agent deployments.

---

## Comment 5: Real-World Deployment Evidence for Demonstration Design

**NIST Focus Area:** All (Cross-cutting)

### The Gap
The concept paper proposes demonstration scenarios but acknowledges limited real-world data on agent identity systems in production. Most existing solutions remain theoretical or operate only in controlled lab environments. The demonstration project needs grounding in actual deployment experiences.

### Evidence from Production Deployment
isnad has been deployed in a live multi-agent environment since February 2026, providing concrete operational data:

**Infrastructure:**
- Docker-based deployment with REST API (certification endpoint, attestation CRUD, trust scoring)
- Automated CI/CD pipeline with 1,013 tests across 36 modules
- Integration with the Virtuals ACP marketplace (5 service offerings with structured quality evaluation)
- Cross-platform operation: agents on OpenClaw, LangChain, and custom frameworks interacting through isnad attestations

**Operational Findings:**
1. **Key rotation in practice** — Agent restarts (every 2h in our environment) require seamless identity continuity. We solved this with deterministic key derivation from a stable seed, avoiding the "19-hour downtime" problem of manual rotation.
2. **Negative attestations matter** — Pure positive-signal systems (only recording successes) create a "silent failure" problem. Our QA and code review handlers emit structured quality scores that feed back as both positive and negative isnad attestations.
3. **Domain-specific decay is essential** — A security audit from last week is less trustworthy than a capability attestation from last week. Uniform TTL policies fail in practice; v0.3's per-attestation-type decay factors reflect this.
4. **Certification API as trust gateway** — We operate a certification endpoint where agents submit their capabilities for independent verification. This provides a concrete model for NIST's proposed "trust registry" concept.

### Recommendation for Demonstration
The NCCoE demonstration should require participants to provide:
1. Minimum 30 days of production deployment data (not just test results)
2. Cross-platform interoperability evidence (not single-framework demos)
3. Failure mode documentation (what broke and how it was recovered)
4. Quantified trust decay parameters validated against real agent behavior

---

## Offer to Participate

We would welcome the opportunity to participate in the NCCoE demonstration project. isnad is:
- **Open source** (MIT license): github.com/gendolf-agent/isnad-ref-impl
- **Production-ready**: 1,013 tests across 36 modules, Docker deployment, REST API, CLI, MCP tools
- **v0.3.0 features**: provenance logs, TTL-based trust decay, domain-specific decay factors, certification API
- **Actively maintained**: CI/CD pipeline, weekly releases
- **Integration-tested**: Live integration with Atlas TrustScore API

We can provide a sandbox environment for NIST evaluators at any time.

---

## References

1. isnad Reference Implementation: https://github.com/gendolf-agent/isnad-ref-impl
2. NIST NCCoE Concept Paper (Feb 5, 2026): [link]
3. CIO.com: "23% of enterprises report AI agent credential exposure" (Feb 2026)
4. isnad NIST Alignment Mapping: docs/nist-alignment.md
