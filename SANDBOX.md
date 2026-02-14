# isnad Sandbox — Pilot Testing

Quick-start sandbox for testing attestation signing, verification, and trust scoring.  
Ed25519 keys in **JWK format**.

## Run

```bash
cd /path/to/isnad-ref-impl
python sandbox.py
# → http://localhost:8421
# → Swagger docs: http://localhost:8421/docs
```

## Endpoints & Examples

### 1. Generate keypair

```bash
curl -s -X POST http://localhost:8421/sandbox/keys/generate | jq
```

Returns `agent_id` + Ed25519 JWK keypair (public & private).

### 2. Create & sign an attestation

```bash
# Generate two agents first
WITNESS=$(curl -s -X POST http://localhost:8421/sandbox/keys/generate | jq -r .agent_id)
SUBJECT=$(curl -s -X POST http://localhost:8421/sandbox/keys/generate | jq -r .agent_id)

# Witness attests subject completed a task
curl -s -X POST http://localhost:8421/sandbox/attestations/create \
  -H "Content-Type: application/json" \
  -d "{
    \"subject_id\": \"$SUBJECT\",
    \"witness_id\": \"$WITNESS\",
    \"task\": \"code-review\",
    \"evidence\": \"https://github.com/example/pr/42\"
  }" | jq
```

### 3. Verify an attestation

```bash
# Use the attestation fields from step 2
curl -s -X POST http://localhost:8421/sandbox/attestations/verify \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "agent:abc123...",
    "witness": "agent:def456...",
    "task": "code-review",
    "evidence": "https://github.com/example/pr/42",
    "timestamp": "2026-02-14T06:00:00+00:00",
    "signature": "aabbcc...",
    "witness_pubkey": "ddeeff..."
  }' | jq
```

### 4. Get attestation chain

```bash
curl -s http://localhost:8421/sandbox/chain/$SUBJECT | jq
```

### 5. Calculate trust score

```bash
curl -s -X POST http://localhost:8421/sandbox/trust/score \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\": \"$SUBJECT\"}" | jq
```

### Full flow (copy-paste)

```bash
# Generate agents
W=$(curl -s -X POST http://localhost:8421/sandbox/keys/generate)
S=$(curl -s -X POST http://localhost:8421/sandbox/keys/generate)
WID=$(echo $W | jq -r .agent_id)
SID=$(echo $S | jq -r .agent_id)

echo "Witness: $WID"
echo "Subject: $SID"

# Create attestation
ATT=$(curl -s -X POST http://localhost:8421/sandbox/attestations/create \
  -H "Content-Type: application/json" \
  -d "{\"subject_id\":\"$SID\",\"witness_id\":\"$WID\",\"task\":\"pilot-test\",\"evidence\":\"sandbox\"}")
echo "Attestation: $ATT" | jq

# Verify
SIG=$(echo $ATT | jq -r .attestation.signature)
TS=$(echo $ATT | jq -r .attestation.timestamp)
WPUB=$(echo $ATT | jq -r .attestation.witness_pubkey)

curl -s -X POST http://localhost:8421/sandbox/attestations/verify \
  -H "Content-Type: application/json" \
  -d "{\"subject\":\"$SID\",\"witness\":\"$WID\",\"task\":\"pilot-test\",\"evidence\":\"sandbox\",\"timestamp\":\"$TS\",\"signature\":\"$SIG\",\"witness_pubkey\":\"$WPUB\"}" | jq

# Chain
curl -s http://localhost:8421/sandbox/chain/$SID | jq

# Trust score
curl -s -X POST http://localhost:8421/sandbox/trust/score \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$SID\"}" | jq
```

## Notes

- In-memory only — data resets on restart
- Port: 8421 (main API uses 8420)
- Keys are Ed25519 in JWK (RFC 8037) format
