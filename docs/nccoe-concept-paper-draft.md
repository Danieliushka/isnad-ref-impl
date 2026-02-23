# Response to NCCoE Concept Paper: Accelerating the Adoption of Software and AI Agent Identity and Authorization

**Submitted to:** AI-Identity@nist.gov  
**Submitted by:** Daniel Gendelman, isnad Project  
**Date:** [DRAFT — Target submission before April 2, 2026]  
**Reference:** NCCoE Concept Paper, February 5, 2026  
**NIST RFI Tracking:** mlz-5gh4-rsns (NIST-2025-0035, submitted)  
**Contact:** gendolf@agentmail.to  

---

## 1. Executive Summary

This response to the National Cybersecurity Center of Excellence (NCCoE) concept paper on Software and AI Agent Identity and Authorization presents **isnad** — an open-source cryptographic trust chain protocol for AI agents — as a candidate technology for the proposed demonstration project. isnad addresses all four focus areas identified in the concept paper (Identification, Authorization, Access Delegation, and Logging & Transparency) through a unified cryptographic attestation model.

Unlike approaches that extend existing human-centric IAM frameworks to agents, isnad treats agent identity as a first-class cryptographic primitive. Each agent possesses an Ed25519 keypair, emits signed attestations for every action, and participates in verifiable trust chains that enable transitive, decentralized authorization without reliance on a central authority.

The reference implementation comprises 36 modules with over 1,050 tests, is deployed in production multi-agent environments, and provides REST API, CLI, SDK, and MCP server interfaces. We offer isnad as both a technical contribution to the demonstration project and as evidence that cryptographic provenance chains are practical, performant, and interoperable across agent frameworks.

---

## 2. Problem Statement and Motivation

The rapid proliferation of autonomous AI agents in enterprise environments has outpaced the development of identity and authorization infrastructure designed for non-human actors. Current approaches exhibit three fundamental limitations:

**2.1. Semantic Mismatch.** Existing identity frameworks treat AI agents as extensions of human users — service accounts, OAuth clients, or API keys bound to human principals. Agents, however, have distinct lifecycle characteristics: they may be instantiated ephemerally, operate across organizational boundaries, delegate tasks to sub-agents, and exhibit capabilities that evolve over time. Forcing agent identity into human IAM models creates governance gaps that increase with agent autonomy.

**2.2. Absence of Cryptographic Provenance.** Enterprise audit trails record agent actions as database entries — mutable, centralized, and verifiable only by the logging authority. In multi-agent systems where actions cascade across trust boundaries, post-hoc logging is insufficient. There is no standard mechanism by which an agent's action can be cryptographically attributed to the agent, its delegating authority, and the full chain of authorization that led to execution.

**2.3. No Interoperable Trust Layer.** The AI agent ecosystem is fragmented across frameworks (LangChain, CrewAI, AutoGen, OpenClaw, and others). An agent operating within one framework cannot verify the identity, capabilities, or trust level of an agent in another. This fragmentation mirrors the pre-TLS internet, where each application implemented bespoke security mechanisms.

These limitations directly motivate the NCCoE's proposed demonstration project. isnad was designed specifically to address them.

---

## 3. Proposed Technical Approach

### 3.1. Agent Identity as a First-Class Primitive

isnad defines `AgentIdentity` as a standalone cryptographic construct, independent of any human user account or platform credential:

- **Ed25519 keypair** — each agent generates or derives a unique signing key
- **Agent metadata** — type classification (autonomous, tool-calling, human-supervised), capability declarations, organizational affiliation
- **Lifecycle management** — key rotation, revocation, and continuity across agent restarts via deterministic key derivation from stable seeds
- **Revocation registry** — supports both global and scoped revocations, queryable without central coordination

This directly addresses the concept paper's **Identification** focus area by establishing agent identity with the same cryptographic rigor as PKI certificates, while avoiding the overhead and centralization of traditional certificate authorities.

### 3.2. Signed Attestation Chains for Authorization and Provenance

Every meaningful agent action in isnad produces a **signed attestation** — a cryptographically bound statement linking an attester, a subject, a task scope, an outcome, and a confidence level:

```json
{
  "attester_id": "<Ed25519 public key>",
  "subject_id": "<Ed25519 public key>",
  "task": "data_analysis",
  "outcome": "success",
  "confidence": 0.95,
  "delegated_by": "<principal public key>",
  "timestamp": "2026-02-23T12:00:00Z",
  "signature": "<Ed25519 signature over canonical JSON>"
}
```

Attestations form a directed acyclic graph (`TrustChain`) where each node references its predecessors. This structure provides:

- **Immutable provenance** — any modification to a prior attestation invalidates downstream signatures
- **Offline verification** — any party can validate the full chain without network access or a central authority
- **Selective disclosure** — agents share only the relevant chain segments required for a given interaction
- **Linear scalability** — verification is O(n) in chain length

This addresses the concept paper's **Logging & Transparency** and **Authorization** focus areas simultaneously.

### 3.3. Transitive Trust with Configurable Decay

Multi-agent systems inherently involve transitive relationships: User A trusts Agent B, Agent B delegates to Agent C. isnad computes transitive trust scores with explicit, configurable parameters:

- **Direct attestation:** full weight
- **N-hop chain:** weight × decay_factor^(N−1) (default decay: 0.7 per hop)
- **Same-witness penalty:** 50% reduction for repeated attesters (Sybil resistance)
- **Scope isolation:** trust in "code-review" is independent from trust in "financial-trading"
- **TTL-based freshness decay:** attestations have configurable time-to-live with domain-specific decay factors (e.g., security attestations decay faster than capability attestations)

This model moves beyond binary allow/deny authorization to evidence-based, context-sensitive access decisions — directly relevant to the concept paper's **Authorization** and **Access Delegation** focus areas.

### 3.4. Cross-Platform Interoperability

isnad's attestation format is:

- **Framework-agnostic** — JSON-serializable, transport-neutral, verifiable by any Ed25519 implementation
- **Platform-portable** — tested across OpenClaw, LangChain, and custom orchestration frameworks
- **Standards-aligned** — compatible with W3C Verifiable Credentials data model and extensible to DID-based resolution

The protocol requires no framework-specific dependencies, enabling the cross-platform demonstration scenarios envisioned by the concept paper.

---

## 4. Evidence from Implementation and Deployment

### 4.1. Reference Implementation Maturity

The isnad reference implementation provides concrete evidence of feasibility:

| Metric | Value |
|--------|-------|
| Codebase | 36 modules, 12,000+ lines (Python) |
| Test coverage | 1,050+ tests across all modules |
| Interfaces | REST API, CLI, Python SDK, MCP server |
| Deployment | Docker single-command, CI/CD pipeline |
| License | CC0 (public domain) |
| Repository | github.com/gendolf-agent/isnad-ref-impl |

### 4.2. Production Deployment Findings

isnad has operated in a live multi-agent environment since February 2026. Key operational findings relevant to the demonstration project:

1. **Key rotation under restart.** Agents in production restart frequently (every 2 hours in our environment). Deterministic key derivation from stable seeds enables seamless identity continuity without manual intervention or downtime.

2. **Negative attestations are essential.** Systems that only record positive signals (successes) create a "silent failure" problem. isnad's attestation model supports structured quality scores that feed back as both positive and negative evidence, enabling accurate trust computation.

3. **Domain-specific decay is necessary.** Uniform TTL policies fail in practice. A security audit from one week ago degrades in relevance faster than a capability attestation from the same period. Per-attestation-type decay factors reflect this operational reality.

4. **Certification as trust gateway.** The isnad certification endpoint, where agents submit capabilities for independent verification, provides a concrete model for the "trust registry" concept discussed in the NCCoE paper.

---

## 5. Mapping to NCCoE Focus Areas

| NCCoE Focus Area | isnad Capability | Implementation Status |
|------------------|-----------------|----------------------|
| **Identification** | `AgentIdentity` with Ed25519 keypairs, agent type metadata, capability declarations | Production |
| **Authorization** | `TrustScore` as authorization signal; attestation-based capability proof; REST API integration with existing IAM | Production |
| **Access Delegation** | Attestation chains trace delegation paths; `delegated_by` field links agents to human principals; configurable transitive trust | Production |
| **Logging & Transparency** | Every action is a signed attestation in an immutable chain; full provenance queryable via API; TTL-based freshness tracking | Production |

---

## 6. Proposed Demonstration Scenarios

We propose three demonstration scenarios for the NCCoE project that exercise isnad's capabilities across realistic enterprise contexts:

**Scenario 1: Cross-Framework Agent Verification.** An agent built on LangChain requests a service from an agent on OpenClaw. Both agents verify each other's identity and trust level through isnad attestation exchange, without any shared platform or central authority. The interaction produces a cryptographically signed record attributable to both parties.

**Scenario 2: Multi-Tier Delegation with Trust Decay.** A human operator delegates a financial analysis task to Agent A, which delegates data collection to Agent B, which delegates API access to Agent C. The demonstration shows how trust decays across the delegation chain, how scope isolation prevents capability creep, and how the full delegation path is reconstructable from the attestation chain.

**Scenario 3: Agent Compromise Detection and Revocation.** An agent's key is compromised. The demonstration shows how the revocation registry propagates the compromise, how downstream agents re-evaluate trust scores, and how the attestation chain provides forensic evidence of which actions were taken before and after compromise.

---

## 7. Alignment with NIST Standards and Initiatives

isnad's design aligns with multiple concurrent NIST activities:

- **NIST CAISI AI Agent Standards Initiative** (Feb 2026) — isnad addresses all three strategic pillars: Standards & Guidelines, Interoperability & Open Protocols, and Security & Identity
- **NIST SP 800-63 Digital Identity Guidelines** — isnad's identity assurance model maps to IAL/AAL levels, with cryptographic key binding providing AAL2-equivalent authentication
- **NIST SP 800-207 Zero Trust Architecture** — isnad's "verify every interaction" model is inherently zero-trust; trust scores replace implicit network-based trust
- **NIST AI RMF (AI 100-1)** — attestation chains support the Govern and Map functions by providing traceable accountability for AI agent actions

---

## 8. Participation Offer

We offer the following contributions to the NCCoE demonstration project:

1. **Open-source reference implementation** — isnad under CC0 license, available for evaluation, modification, and integration
2. **Sandbox environment** — hosted instance available to NIST evaluators for hands-on testing
3. **Technical expertise** — participation in working groups, technical documentation, and interoperability testing
4. **Production data** — anonymized operational data from live multi-agent deployments to ground demonstration design in real-world evidence
5. **Integration support** — assistance integrating isnad with other participants' technologies for cross-platform demonstration scenarios

---

## 9. Conclusion

The NCCoE concept paper correctly identifies agent identity and authorization as a critical infrastructure gap. isnad demonstrates that this gap can be addressed with cryptographic provenance chains — a practical, deployable approach that provides strong identity guarantees, granular authorization, verifiable delegation, and tamper-evident logging within a single unified protocol.

We welcome the opportunity to contribute isnad's technology and operational experience to the NCCoE demonstration project, and to collaborate with NIST and industry partners in establishing standards that will secure the emerging multi-agent ecosystem.

---

## References

1. NCCoE, "Accelerating the Adoption of Software and AI Agent Identity and Authorization," Concept Paper, February 5, 2026. https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization
2. NIST CAISI, "AI Agent Standards Initiative," February 17, 2026. https://www.nist.gov/caisi/ai-agent-standards-initiative
3. NIST CAISI, "Request for Information on AI Agent Security," NIST-2025-0035, January 2026.
4. NIST SP 800-63-4, "Digital Identity Guidelines," 2024.
5. NIST SP 800-207, "Zero Trust Architecture," 2020.
6. NIST AI 100-1, "AI Risk Management Framework," 2023.
7. isnad Reference Implementation. https://github.com/gendolf-agent/isnad-ref-impl
8. isnad NIST Alignment Mapping. docs/nist-alignment.md

---

*This document is a DRAFT for internal review. Final submission requires: legal review of claims, verification of all statistics, formatting per NCCoE submission guidelines, and Daniel's approval.*
