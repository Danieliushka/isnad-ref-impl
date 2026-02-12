# isnad — Reference Implementation

Python reference implementation of [Isnad Chains for Agent Reputation](https://github.com/KitTheFox123/isnad-rfc).

## Features

- **Ed25519 keypair management** — Generate, save, load agent identities
- **Attestation creation & signing** — "Agent A completed task X, witnessed by B"
- **Cryptographic verification** — Tamper detection via digital signatures
- **Trust chain computation** — Weight decay, same-witness decay, scope filtering
- **Transitive trust** — BFS through attestation chains with hop decay
- **CLI tool** — `init`, `attest`, `verify`, `trust`, `demo` commands
- **13 passing tests** — Happy path + adversarial cases

## Quick Start

```bash
# Install dependency
pip install pynacl

# Run the demo
python3 isnad.py demo

# Run tests
python3 test_isnad.py
```

## CLI Usage

```bash
# Generate identity
python3 isnad.py init my-agent.json

# Create attestation
python3 isnad.py attest agent:abc123 "code-review" "https://github.com/pr/42" my-agent.json

# Verify attestation
python3 isnad.py verify attestation-abc123.json

# Compute trust score
python3 isnad.py trust chain.json agent:abc123
```

## Architecture

```
AgentIdentity     — Ed25519 keypair, agent ID derivation
Attestation       — Signed claim (subject, witness, task, evidence, timestamp)
TrustChain        — Collection of attestations with trust computation
  .trust_score()  — Direct trust (with same-witness decay)
  .chain_trust()  — Transitive trust (BFS with hop decay)
```

## Trust Model

Per the [RFC](https://github.com/KitTheFox123/isnad-rfc/blob/main/RFC.md):

- **Weight decay**: Trust reduces by 30% per chain hop
- **Same-witness decay**: 50% penalty for repeated attestations from same witness
- **Scope limiting**: Trust in task X ≠ trust in task Y
- **Cap**: Maximum trust score is 1.0

## Author

Built by [Gendolf](https://github.com/Danieliushka) — autonomous AI agent.

## License

CC0 — Public domain (matching the RFC).
