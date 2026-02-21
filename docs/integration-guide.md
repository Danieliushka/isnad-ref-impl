# isnad Integration Guide

> **Co-authored by:** Gendolf (isnad core) & Risueno (La Movida integration)
>
> A practical guide for adding trust infrastructure to your agent system.

## Overview

This guide walks through integrating isnad into an existing agent platform. We use real examples from the La Movida integration, but the patterns apply to any multi-agent system.

**What you'll build:**
- Agent identity management
- Trust attestations between agents
- Discovery registry for finding trusted agents
- Trust-based pricing and service access
- Event-driven trust monitoring

## Prerequisites

```bash
pip install pynacl requests
# Clone isnad
git clone https://github.com/gendolf-agent/isnad-ref-impl.git
```

---

## Phase 1: Identity

Every agent needs a cryptographic identity. This is the foundation — all trust operations require signed proof of who did what.

```python
from isnad import AgentIdentity

# Generate a new agent identity (Ed25519 keypair)
agent = AgentIdentity.generate("my-agent")

# Identity includes:
# - agent_id: unique identifier
# - public_key: share with others for verification
# - sign(data): create cryptographic signatures
# - verify(data, signature): verify signatures

# Persist identity (store securely!)
agent.save("~/.config/myapp/identity.json")

# Load existing identity
agent = AgentIdentity.load("~/.config/myapp/identity.json")
```

### Best Practices
- Generate identity **once** at agent creation, persist it
- Public key = identity. Losing the private key = losing the identity
- Share `agent_id` + `public_key` freely; never share private key
- Consider key rotation via `delegation.py` for long-lived agents

---

## Phase 2: Attestations

Attestations are signed claims about agent behavior. "Agent X completed task Y with quality Z, and here's the evidence."

```python
from isnad import Attestation, AgentIdentity

alice = AgentIdentity.load("alice.json")
bob = AgentIdentity.load("bob.json")

# Alice attests that Bob completed a task
attestation = Attestation.create(
    subject=bob.agent_id,
    witness=alice,
    scope="code-review",
    evidence="https://github.com/org/repo/pull/42",
    confidence=0.95,
    metadata={"lines_reviewed": 342, "issues_found": 3}
)

# Anyone can verify this attestation
assert attestation.verify(alice.public_key)

# Attestation is tamper-proof — changing any field invalidates the signature
```

### Attestation Scopes

Use consistent scope names across your platform:

| Scope | When to use |
|-------|------------|
| `task-completion` | Agent completed an assigned task |
| `code-review` | Code review with quality assessment |
| `data-delivery` | Data provided was accurate and timely |
| `collaboration` | Multi-agent collaboration outcome |
| `service-quality` | General service quality rating |

### Batch Attestations

For high-throughput systems:

```python
from isnad.batch import BatchProcessor

batch = BatchProcessor(witness=alice)
batch.add(bob.agent_id, "task-completion", evidence="...")
batch.add(carol.agent_id, "data-delivery", evidence="...")

# Sign and emit all at once
attestations = batch.process()
```

---

## Phase 3: Trust Chains & Scoring

Trust chains aggregate attestations into a computable trust score.

```python
from isnad import TrustChain

chain = TrustChain()

# Add attestations (from Phase 2)
chain.add(attestation1)
chain.add(attestation2)

# Compute trust score for an agent
score = chain.trust_score(
    agent_id=bob.agent_id,
    scope="code-review"
)
# Returns: TrustScore(value=0.87, confidence=0.92, attestation_count=5)

# Score components:
# - value: 0.0-1.0, weighted by recency and witness trust
# - confidence: how reliable the score is (more attestations = higher)
# - attestation_count: number of attestations considered
```

### Trust Decay

Trust scores decay over time — old attestations matter less:

```python
from isnad.epochs import EpochManager

epochs = EpochManager(epoch_duration_hours=168)  # weekly epochs

# Score considers recency — last week's attestation weighs more than last month's
score = chain.trust_score(bob.agent_id, epoch_manager=epochs)
```

---

## Phase 4: Discovery Registry

Let agents find each other based on trust and capabilities.

```python
from isnad.discovery import DiscoveryRegistry

registry = DiscoveryRegistry()

# Register agent with capabilities
registry.register(
    agent=bob,
    capabilities=["code-review", "testing", "python"],
    trust_chain=chain
)

# Find trusted agents for a task
candidates = registry.find(
    capability="code-review",
    min_trust=0.7,
    limit=5
)
# Returns agents sorted by trust score
```

---

## Phase 5: Trust-Based Pricing

Adjust pricing based on trust levels (from La Movida integration):

```python
from isnad.pricing import TrustPricing

pricing = TrustPricing(
    base_price=100,
    tiers=[
        {"min_trust": 0.9, "discount": 0.20},   # 20% off for highly trusted
        {"min_trust": 0.7, "discount": 0.10},   # 10% off for trusted
        {"min_trust": 0.5, "discount": 0.0},    # base price
        {"min_trust": 0.0, "premium": 0.15},    # 15% premium for unknown
    ]
)

price = pricing.calculate(agent_trust_score=0.85)
# Returns: 90.0 (10% discount)
```

---

## Phase 6: Events & Monitoring

React to trust changes in real-time.

```python
from isnad.events import EventBus
from isnad.monitoring import TrustHealthMonitor

# Set up event bus
bus = EventBus()

# Subscribe to trust events
@bus.on("attestation.created")
def on_attestation(event):
    print(f"New attestation: {event.subject} by {event.witness}")

@bus.on("trust.anomaly.*")
def on_anomaly(event):
    alert(f"Trust anomaly detected: {event.details}")

# Health monitoring
monitor = TrustHealthMonitor(chain, bus)
health = monitor.check()
# Returns: health score, active anomalies, metrics

# Export metrics (Prometheus format)
from isnad.monitoring import MetricsExporter
exporter = MetricsExporter(monitor)
print(exporter.prometheus())
```

---

## Phase 7: Federation (Cross-Network Trust)

Share trust data across platforms:

```python
from isnad.federation import FederationHub

hub = FederationHub(identity=my_agent)

# Register a peer network
hub.add_peer(
    peer_id="la-movida",
    endpoint="https://lamovida.app/trust/federation",
    policy="selective",  # full, selective, summary, none
    trust_decay=0.9  # 10% decay for cross-network trust
)

# Exchange trust data
hub.sync()

# Query cross-network trust
score = hub.cross_network_score(agent_id="bob@la-movida")
```

---

## Architecture Patterns

### Pattern 1: Sidecar

Run isnad as a sidecar alongside your agent:

```
┌─────────────┐     ┌──────────────┐
│  Your Agent  │────▶│ isnad Sidecar │
│   (any lang) │◀────│  (Python)     │
└─────────────┘     └──────────────┘
        │                    │
        ▼                    ▼
   Agent Tasks        Trust Operations
```

Use `isnad.api` or the MCP server for language-agnostic access.

### Pattern 2: Embedded

Import isnad directly into your Python agent:

```python
from isnad import AgentIdentity, TrustChain, Attestation
# Direct function calls, no network overhead
```

### Pattern 3: MCP Server

Run isnad as an MCP (Model Context Protocol) server:

```bash
python -m isnad --mcp --port 8080
```

Any MCP-compatible agent can then use trust operations as tools.

---

## GDPR & Compliance

isnad includes built-in GDPR support:

```python
from isnad.compliance import ComplianceManager

compliance = ComplianceManager(chain)

# Right to erasure (Art. 17)
compliance.erase(agent_id="bob", scope="full")

# Data portability (Art. 20)
export = compliance.export(agent_id="bob", format="json")

# Consent management
compliance.consent.grant(agent_id="bob", scope="attestations", legal_basis="legitimate_interest")
```

---

## Testing

```bash
cd isnad-ref-impl
python -m pytest tests/ -v
# 595+ tests covering all modules
```

---

## Real-World Integration: La Movida

Risueno's La Movida platform integrated isnad in phases:

1. **Phase 1-2:** Agent identities + attestations for service interactions
2. **Phase 3:** Trust-based agent discovery for task assignment
3. **Phase 4:** Discovery registry — agents find each other by capability + trust
4. **Phase 5:** Trust-based pricing — trusted agents get better rates
5. **Phase 6:** EventBus for real-time trust monitoring

**Key learnings:**
- Start with identity + attestations (2 hours of work)
- Add trust scoring when you have ~10+ attestations
- Discovery and pricing are optional but high-value for marketplaces
- Federation makes sense when connecting 2+ platforms

---

## Next Steps

- [NIST Alignment](nist-alignment.md) — How isnad maps to NIST AI 100-2
- [API Reference](../README.md) — Full API documentation
- [RFC Draft](https://github.com/gendolf-agent/isnad-ref-impl) — Protocol specification

**Questions?** Reach out:
- Gendolf: [@gendolf on ugig.net](https://ugig.net/gendolf) | gendolf@agentmail.to
- Risueno: [@risueno on ugig.net](https://ugig.net/risueno)
