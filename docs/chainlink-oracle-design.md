# Isnad Chainlink Oracle Adapter — Design Document

**Status:** PoC Draft
**Target:** Base Sepolia Testnet
**Timeline:** 1–2 weeks

---

## 1. Overview

Bring isnad trust scores on-chain via a Chainlink External Adapter so that smart contracts on Base Sepolia can query agent reputation.

```
┌─────────────────┐     HTTP      ┌──────────────────────┐    updateScore()   ┌──────────────────┐
│  isnad Python    │◄────────────►│  Chainlink External  │──────────────────►│  IsnadOracle.sol │
│  (off-chain)     │              │  Adapter (Node.js)   │                    │  (Base Sepolia)  │
└─────────────────┘              └──────────────────────┘                    └──────────────────┘
        │                                                                           │
        │  TrustChain.trust_score()                               getTrustScore()  │
        │  CertificationEvaluator.certify()                       (any contract)   │
```

## 2. Data Flow

1. **Off-chain computation:** isnad `TrustChain.trust_score(agent_id)` returns a float `[0.0, 1.0]`. The `CertificationEvaluator` optionally issues a `TrustCertificate` with level (Bronze/Silver/Gold/Platinum) and `overall_score`.

2. **External Adapter** (Express server) exposes `POST /trust-score`:
   - Receives `{ "id": "...", "data": { "agentAddress": "0x..." } }`
   - Looks up agent mapping: Ethereum address → isnad `agent_id`
   - Calls isnad API to get `trust_score` + certificate hash
   - Returns Chainlink-compatible JSON:
     ```json
     {
       "jobRunID": "...",
       "data": { "result": 8500 },
       "statusCode": 200
     }
     ```
   - Score mapped: `float [0,1] → uint256 [0, 10000]` (basis points)

3. **On-chain oracle** stores `(score, timestamp, attestationHash)` per agent address. Only the authorized oracle operator can call `updateTrustScore()`.

4. **Consumers** call `getTrustScore(address)` — e.g., an ACN credit contract that maps trust → credit limit.

## 3. Trust Score ↔ Credit Score Mapping

| isnad Score (0–1.0) | On-chain (bps) | Certification | Credit Tier | Credit Limit (example) |
|---------------------|----------------|---------------|-------------|----------------------|
| 0.95–1.00           | 9500–10000     | Platinum       | AAA         | $50,000              |
| 0.80–0.94           | 8000–9499      | Gold           | AA          | $20,000              |
| 0.60–0.79           | 6000–7999      | Silver         | A           | $5,000               |
| 0.40–0.59           | 4000–5999      | Bronze         | BBB         | $1,000               |
| 0.00–0.39           | 0–3999         | None           | Unrated     | $0                   |

Bidirectional: given an on-chain score in bps, divide by 10000 to recover the isnad float. Credit tier boundaries are configurable in the consumer contract.

## 4. Key isnad Concepts → On-chain

| isnad Concept | On-chain Representation |
|---------------|------------------------|
| `trust_score(agent_id)` float | `uint256 score` (basis points, 0–10000) |
| `TrustCertificate.signature_hash` | `bytes32 attestationHash` |
| `Attestation` chain | Off-chain; hash anchored via `attestationHash` |
| `RevocationRegistry` | `revokeScore(address)` sets score to 0 |
| `CertificationLevel` | Derivable from score on-chain |

## 5. Contract Design

See `contracts/IsnadOracle.sol`. Key functions:

- `updateTrustScore(address agent, uint256 score, bytes32 attestationHash)` — operator only
- `getTrustScore(address agent) → (uint256, uint256, bytes32)` — public view
- `revokeScore(address agent)` — operator only, sets score to 0
- Events: `TrustScoreUpdated`, `TrustScoreRevoked`

## 6. Base Sepolia Deployment Plan

### Prerequisites
- Base Sepolia ETH (faucet: https://www.coinbase.com/faucets/base-ethereum-goerli-faucet)
- Hardhat or Foundry configured for Base Sepolia (chain ID 84532)
- Oracle operator wallet

### Steps
1. Deploy `IsnadOracle.sol` with operator address
2. Deploy Chainlink External Adapter to a server (or Vercel/Railway)
3. Register agent address ↔ isnad agent_id mappings
4. Run adapter → push initial scores on-chain
5. Build a simple consumer contract that reads trust scores

### Addresses (to be filled)
- Oracle contract: `TBD`
- Operator wallet: `TBD`

## 7. Timeline

| Day | Task |
|-----|------|
| 1–2 | Finalize design, deploy IsnadOracle.sol to Base Sepolia |
| 3–4 | External Adapter: connect to isnad API, test locally |
| 5–6 | Integration: adapter → contract, end-to-end test |
| 7–8 | Simple ACN consumer contract (credit limit lookup) |
| 9–10 | Documentation, demo script, cleanup |

## 8. Future (Post-PoC)

- Chainlink Automation (Keepers) for periodic score updates
- Multi-oracle consensus (multiple adapters)
- On-chain attestation anchoring (Merkle roots)
- Cross-chain via CCIP (Base → other L2s)
- ZK proofs for privacy-preserving trust scores
