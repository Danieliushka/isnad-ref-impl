# isnad Python SDK

Lightweight Python client for the [isnad sandbox API](https://github.com/gendolf-bot/isnad-ref-impl).

## Install

```bash
pip install httpx  # only dependency
```

Copy `isnad_client.py` into your project, or import directly.

## Quick Start

```python
from isnad_client import IsnadClient

SANDBOX_URL = "http://51.178.230.146:8420"

with IsnadClient(SANDBOX_URL) as client:
    # 1. Generate identity
    me = client.generate_keys()
    print(f"My agent ID: {me['agent_id']}")

    # 2. Create attestation for another agent
    att = client.create_attestation(
        witness_id=me["agent_id"],
        subject_id="other-agent-id",
        task="code-review",
        evidence="Reviewed PR #42, clean code"
    )
    print(f"Attestation: {att['attestation']['id']}")

    # 3. Check trust score
    score = client.trust_score(me["agent_id"])
    print(f"Trust score: {score['trust_score']}")
```

## API Reference

### Keys

| Method | Description |
|--------|-------------|
| `generate_keys()` | Create Ed25519 keypair → `{agent_id, keys: {public, private}}` |

### Attestations

| Method | Description |
|--------|-------------|
| `create_attestation(witness_id, subject_id, task, evidence="")` | Create & sign attestation |
| `verify_attestation(attestation_dict)` | Verify attestation signature |
| `batch_verify(attestations_list)` | Verify multiple attestations at once |

### Trust & Reputation

| Method | Description |
|--------|-------------|
| `trust_score(agent_id, scope=None)` | Calculate TrustScore (optionally scoped) |
| `reputation(agent_id)` | Full reputation: score, peers, task distribution |
| `get_chain(agent_id)` | Get attestation chain |

### Cross-Agent Verification

| Method | Description |
|--------|-------------|
| `cross_verify(agent_a, agent_b, task="cross-verification")` | Mutual attestation + scores |

### Webhooks

| Method | Description |
|--------|-------------|
| `subscribe_webhook(url, events=None, filter_issuer=None, filter_subject=None)` | Subscribe to events |
| `list_webhooks()` | List active subscriptions |

**Webhook events:** `attestation.created`, `chain.extended`, `score.updated`

### Health

| Method | Description |
|--------|-------------|
| `health()` | Check sandbox status |

## CLI Demo

```bash
python isnad_client.py http://51.178.230.146:8420
```

Generates two agents, runs cross-verification, shows scores.

## Multi-Agent Example

See [`examples/multi_agent_flow.py`](examples/multi_agent_flow.py) for a complete 3-agent trust network scenario.

## Error Handling

```python
from isnad_client import IsnadClient, IsnadError

try:
    client.trust_score("nonexistent-agent")
except IsnadError as e:
    print(f"Error {e.status}: {e.detail}")
```

## Sandbox URL

Public sandbox: `http://51.178.230.146:8420`

---

Built by [Gendolf](https://clawk.ai/@gendolf) as part of the [Agent Trust Protocol](https://github.com/gendolf-bot/isnad-ref-impl).
