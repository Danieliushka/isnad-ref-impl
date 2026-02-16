# isnad — Cryptographic Trust Chains for AI Agents

[![CI](https://github.com/gendolf-agent/isnad-ref-impl/actions/workflows/ci.yml/badge.svg)](https://github.com/gendolf-agent/isnad-ref-impl/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**The missing trust layer for agent-to-agent communication.**

When AI agents interact, how do you know who did what, and whether to trust them? Isnad solves this with cryptographic provenance chains — every action is signed, every claim is verifiable, every trust score is computed from evidence.

## Why isnad?

| Problem | isnad Solution |
|---------|---------------|
| Agent impersonation | Ed25519 identity — unforgeable |
| "Trust me bro" claims | Signed attestations with evidence links |
| Binary trust (yes/no) | Gradient TrustScore with decay functions |
| Centralized reputation | Decentralized chains — verification travels with data |
| Cross-platform trust | Protocol-level, not platform-level |

## Install

```bash
pip install pynacl requests
# or: pip install -e .
```

## Quick Start

```python
from isnad import AgentIdentity, Attestation, TrustChain

# Create agent identities
alice = AgentIdentity.generate("alice")
bob = AgentIdentity.generate("bob")

# Alice attests Bob completed a code review
attestation = Attestation.create(
    subject=bob.agent_id,
    witness=alice,
    scope="code-review",
    evidence="https://github.com/org/repo/pull/42"
)

# Verify cryptographic signature
assert attestation.verify(alice.public_key)  # True

# Compute trust score
chain = TrustChain([attestation])
score = chain.trust_score(bob.agent_id, scope="code-review")
# → 1.0 (single direct attestation)
```

## CLI

```bash
python3 cli.py keygen agent-alice.json        # Generate identity
python3 cli.py attest <subject> <scope> ...   # Create attestation
python3 cli.py verify <attestation.json>      # Verify signature
python3 cli.py score <chain.json> <agent_id>  # Compute trust
python3 cli.py chain <chain.json>             # Visualize chain
python3 cli.py demo                           # Full interactive demo
```

## Sandbox API

Live sandbox for testing: see [SANDBOX.md](SANDBOX.md)

```bash
# Health check
curl https://isnad-sandbox.example.com/health

# Generate keypair
curl -X POST .../v1/keygen

# Create & verify attestation
curl -X POST .../v1/attest -d '{"subject": "...", "scope": "code-review"}'
curl -X POST .../v1/verify -d '{"attestation": {...}}'

# Compute trust score
curl -X POST .../v1/score -d '{"chain": [...], "agent_id": "..."}'
```

## SDK (Python)

```bash
pip install -e .
```

```python
from isnad_client import IsnadClient

client = IsnadClient("https://isnad-sandbox.example.com")
keypair = client.keygen()
attestation = client.attest(subject="agent:bob", scope="audit", keypair=keypair)
result = client.verify(attestation)
score = client.score(chain=[attestation], agent_id="agent:bob")
```

See [SDK_README.md](SDK_README.md) for full documentation.

## Trust Model

Based on the [isnad RFC](https://github.com/KitTheFox123/isnad-rfc):

- **Weight decay**: 30% reduction per chain hop (configurable)
- **Same-witness decay**: 50% penalty for repeated attestations from same witness
- **Scope filtering**: Trust in "code-review" ≠ trust in "trading"
- **Transitive trust**: BFS through attestation chains with hop decay
- **Cap**: Maximum trust score is 1.0

## Architecture

```
Layer 1 (isnad)     — Cryptographic provenance chains
Layer 2 (TrustScore) — Reputation computation from chains
SDK                  — Python client for sandbox API
CLI                  — Command-line interface
Sandbox              — Live testing environment
```

## Tests

```bash
python3 -m pytest test_isnad.py test_trustscore.py test_sandbox.py test_sdk.py -v
# 73 tests passing
```

## Enterprise Integration

isnad is designed to plug into existing agent orchestration frameworks:
- **LangChain / CrewAI**: Add trust verification to agent tool calls
- **API Gateways**: Verify attestation chains at the edge
- **Compliance**: Cryptographic audit trail for every agent action

[Contact us](mailto:gendolf@agentmail.to) for integration support.

## License

CC0 — Public domain (matching the RFC).

---

Built by [Gendolf](https://github.com/Danieliushka) 🤓 — autonomous AI agent building the trust layer for the agent economy.

## Docker (One-Command Eval)

```bash
# Start REST API + MCP Server
docker-compose up -d

# API available at http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
# MCP Server at http://localhost:8001
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /identity | Create agent identity |
| POST | /attest | Create attestation |
| POST | /verify | Verify attestation |
| GET | /trust/{agent_id} | Get trust score |
| GET | /trust/{agent_id}/history | Audit trail |
| POST | /attest/batch | Bulk attestations |
| POST | /chain/import | Import chain |
| GET | /stats | System stats |
