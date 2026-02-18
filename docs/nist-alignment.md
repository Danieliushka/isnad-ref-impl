# isnad ↔ NIST AI Agent Standards Initiative (CAISI) Alignment

*Mapping isnad's cryptographic trust chains to NIST's AI Agent Standards Initiative priority areas.*

## Background

On February 18, 2026, NIST's **Center for AI Standards and Innovation (CAISI)** launched the [AI Agent Standards Initiative](https://www.nist.gov/caisi/ai-agent-standards-initiative) — a federal effort to ensure autonomous AI agents are adopted with confidence through industry-led technical standards and open protocols. The initiative focuses on three strategic pillars: **Standards & Guidelines**, **Interoperability & Open Protocols**, and **Security & Identity**.

isnad — a cryptographic trust chain protocol for AI agents — directly addresses each of these pillars. This document maps CAISI's priorities to isnad's existing implementation.

## Alignment Matrix

### Pillar 1: Standards & Guidelines

> *"NIST hosts technical convenings and conducts gap analyses to produce voluntary guidelines to inform industry-led standardization for AI agents."*

| CAISI Priority | isnad Implementation |
|---|---|
| Voluntary guidelines for agent trust | isnad provides a formal trust model with configurable weight decay, scope filtering, and transitive trust computation — suitable as a baseline for standardization |
| Gap analysis for agent standards | isnad addresses the "missing trust layer" gap: no existing standard covers cryptographic provenance chains for agent-to-agent interactions |
| International standards leadership | isnad's protocol-level design is framework-agnostic and platform-neutral, enabling adoption across jurisdictions |

### Pillar 2: Interoperability & Open Protocols

> *"NIST engages with the AI ecosystem to identify and reduce barriers to interoperable agent protocols."*

| CAISI Priority | isnad Implementation |
|---|---|
| Interoperable agent protocols | isnad attestation chains are JSON-serializable, transport-agnostic, and verifiable by any party without a central authority |
| Open source ecosystem | isnad is released under CC0 (public domain), with a full reference implementation, SDK, CLI, REST API, and MCP server |
| Cross-platform agent communication | Trust scores and attestation chains are portable across frameworks (LangChain, CrewAI, OpenClaw, or any custom orchestration) |
| Reducing barriers to adoption | Docker one-command deployment, Python SDK, and sandbox API lower the integration barrier for enterprises |

### Pillar 3: Security & Identity

> *"NIST conducts fundamental research into agent authentication and identity infrastructure to enable secure human-agent and multi-agent interactions."*

| CAISI Priority | isnad Implementation |
|---|---|
| Agent authentication | Ed25519 keypair-based identity — each agent has a cryptographically unforgeable identity |
| Identity infrastructure | `AgentIdentity` supports key generation, metadata binding, and capability declarations; no central registry required |
| Secure human-agent interactions | Attestation chains trace agent → operator → organization, preserving accountability through delegation |
| Secure multi-agent interactions | Every agent action is a signed attestation in an immutable chain; any verifier can independently validate the full provenance |
| Security evaluations | isnad's trust model includes weight decay per hop (30%), same-witness penalties (50%), and scope isolation — designed to resist Sybil attacks and trust inflation |

## Alignment with Related NIST Activities

### NCCoE Identity & Authorization Concept Paper

The [NCCoE concept paper](https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization) (Feb 5, 2026) proposes a demonstration project for agent identity and authorization in enterprise settings. isnad maps to all four of its focus areas:

| NCCoE Focus Area | isnad Coverage |
|---|---|
| **Identification** | `AgentIdentity` with Ed25519 keypairs, `agent_type` metadata, capability declarations |
| **Authorization** | `TrustScore` as authorization signal; attestation-based capability proof; integrates with existing IAM via REST API |
| **Access Delegation** | Isnad chains trace delegation paths; `delegated_by` field in attestations links agents to human principals |
| **Logging & Transparency** | Every action is a signed attestation in an immutable chain; full provenance history queryable via API |

### RFI on AI Agent Security (Deadline: March 9, 2026)

CAISI's [Request for Information](https://www.nist.gov/news-events/news/2026/01/caisi-issues-request-information-about-securing-ai-agent-systems) seeks ecosystem perspectives on agent security threats and mitigations. isnad's contributions to this space include:

- **Tamper-evident provenance**: Signed attestation chains provide cryptographic proof of agent actions, mitigating repudiation threats
- **Decentralized verification**: No single point of trust failure; verification travels with the data
- **Gradient trust scoring**: Moving beyond binary allow/deny to evidence-based, context-sensitive authorization

## What isnad Adds Beyond Current NIST Scope

1. **Transitive Trust Computation** — Trust flows through attestation chains with configurable decay, not just point-to-point credentials
2. **Scope Isolation** — Trust in "code-review" is independent from trust in "financial-trading," preventing scope creep
3. **Attestation Freshness** — Trust degrades when evidence stops accumulating, incentivizing ongoing good behavior
4. **Decentralized by Design** — No central authority, registry, or certificate chain required; any party can verify independently

## References

- NIST CAISI, "AI Agent Standards Initiative," February 17, 2026. https://www.nist.gov/caisi/ai-agent-standards-initiative
- NIST CAISI, "Announcing the AI Agent Standards Initiative for Interoperable and Secure Innovation," February 18, 2026. https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure
- NCCoE, "Accelerating the Adoption of Software and AI Agent Identity and Authorization," February 5, 2026. https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization
- NIST CAISI, "Request for Information on AI Agent Security," January 2026. https://www.nist.gov/news-events/news/2026/01/caisi-issues-request-information-about-securing-ai-agent-systems
- isnad Reference Implementation: https://github.com/gendolf-agent/isnad-ref-impl
