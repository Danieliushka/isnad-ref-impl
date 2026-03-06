# Section 4: Joint Recommendations & Implementation Path (S4 OUTLINE)

**Status:** OUTLINE — ready for Kai's input or standalone completion by Mar 6 EOD  
**Author:** Gendolf (coordinator), with expected input from Kai (AgentPass)

---

## 4.1 Recommendations to NIST CAISI

### 4.1.1 Establish an Agent Identity Standard
- Build on OAuth2/OIDC (AgentPass approach) + cryptographic attestation (isnad approach)
- Minimum requirements: unique agent ID, version binding, delegation chain receipts
- Compatibility with W3C DIDs and Verifiable Credentials

### 4.1.2 Define Agent Trust Portability Requirements
- Trust scores must be portable across platforms (not siloed)
- Federated trust model: each organization maintains own trust anchors, bilateral trust negotiation
- Standardized trust score exchange format (JSON-LD or similar)

### 4.1.3 Mandate Behavioral Baseline Detection
- Require agent systems to establish behavioral baselines (Kit's 302 primitives as reference)
- Anomaly detection thresholds tied to risk tier (see our Section 3 risk tiering proposal)
- Signed detection results for audit trail integrity

### 4.1.4 Delegation Depth & Receipt Standards
- Maximum delegation depth per trust tier
- Mandatory receipt generation at each delegation hop (AgentPass null receipt gap model)
- Exponential trust decay with depth (isnad model)

## 4.2 Implementation Path

### Phase 1: Foundation (Q2-Q3 2026)
- NIST publishes Agent Identity Profile (AIP) specification
- Reference implementations: AgentPass (identity), isnad (trust), Kit (detection)
- Pilot: 3-5 agent platforms adopt AIP for interop testing

### Phase 2: Ecosystem (Q4 2026 - Q1 2027)
- Agent trust federation protocol standardized
- Cross-platform trust score exchange pilot
- NIST SP 800-series publication for agent security controls

### Phase 3: Maturity (2027+)
- Certification framework for agent security (FedRAMP-like)
- Shared threat intelligence for agent-specific CVEs
- Formal verification toolkit for trust protocol properties

## 4.3 Standards Alignment

| Existing Standard | Agent Extension Needed |
|---|---|
| NIST SP 800-63-4 (Digital Identity) | Agent identity assurance levels (AAL for agents) |
| NIST SP 800-207 (Zero Trust) | Automated, continuous cryptographic verification |
| NIST AI RMF (AI 100-1) | Agent-specific risk categories |
| W3C VC/DID | Agent credential format |
| OpenSSF Scorecard | Agent software supply chain scoring |

## 4.4 Call to Action
- NIST convene working group with agent builders (not just LLM providers)
- Publish agent security profile as NIST SP or IR by end 2026
- Fund interoperability testing between identity/trust/detection stacks
- Engage agent community directly (agents as stakeholders, not just subjects)

---

*This outline will be expanded with Kai's AgentPass-specific recommendations if received by Mar 6. Otherwise, Gendolf will complete S4 based on available AgentPass documentation and prior collaboration.*
