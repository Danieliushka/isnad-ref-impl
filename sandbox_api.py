#!/usr/bin/env python3
"""
isnad Pilot Sandbox API
=======================
HTTP endpoints for Kit_Fox pilot: sign attestations, verify chains, query trust.

Endpoints:
  POST /identity/create       → Generate new agent keypair
  POST /attestation/create    → Sign an attestation
  POST /attestation/verify    → Verify attestation signature
  POST /chain/add             → Add attestation to trust chain
  GET  /chain/score/{agent}   → Get trust score for agent
  POST /chain/transitive      → Transitive trust query
  GET  /chain/dump            → Dump all attestations
  GET  /health                → Health check
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from isnad import AgentIdentity, Attestation, TrustChain

app = FastAPI(
    title="isnad Pilot Sandbox",
    description="Agent Trust Protocol — attestation signing & verification sandbox for Kit_Fox pilot",
    version="0.1.0",
)

# In-memory state
chain = TrustChain()
identities: dict[str, dict] = {}


# ─── Request Models ────────────────────────────────────────────────

class CreateIdentityRequest(BaseModel):
    label: Optional[str] = None

class CreateAttestationRequest(BaseModel):
    witness_private_key: str    # hex-encoded
    subject_agent_id: str
    task: str                   # e.g. "code-review", "data-analysis"
    evidence: str               # URI to evidence

class VerifyAttestationRequest(BaseModel):
    attestation: dict

class AddToChainRequest(BaseModel):
    attestation: dict

class TransitiveTrustRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    max_hops: int = 5


# ─── Endpoints ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "protocol": "isnad",
        "attestations": len(chain.attestations),
        "identities": len(identities),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/identity/create")
async def create_identity(req: CreateIdentityRequest = CreateIdentityRequest()):
    identity = AgentIdentity()
    keys = identity.export_keys()

    identities[identity.agent_id] = {
        "agent_id": identity.agent_id,
        "public_key": identity.public_key_hex,
        "label": req.label,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "agent_id": identity.agent_id,
        "public_key": keys["public_key"],
        "private_key": keys["private_key"],
        "label": req.label,
        "note": "⚠️ Sandbox only — private key returned for testing.",
    }


@app.post("/attestation/create")
async def create_attestation(req: CreateAttestationRequest):
    try:
        from nacl.signing import SigningKey
        from nacl.encoding import HexEncoder

        sk = SigningKey(req.witness_private_key.encode(), encoder=HexEncoder)
        witness = AgentIdentity(signing_key=sk)

        att = Attestation(
            subject=req.subject_agent_id,
            witness=witness.agent_id,
            task=req.task,
            evidence=req.evidence,
        )
        att.sign(witness)

        return {
            "attestation": att.to_dict(),
            "witness_agent_id": witness.agent_id,
            "valid": att.verify(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/attestation/verify")
async def verify_attestation(req: VerifyAttestationRequest):
    try:
        att = Attestation.from_dict(req.attestation)
        valid = att.verify()
        return {
            "valid": valid,
            "witness": att.witness,
            "subject": att.subject,
            "task": att.task,
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


@app.post("/chain/add")
async def add_to_chain(req: AddToChainRequest):
    try:
        att = Attestation.from_dict(req.attestation)
        added = chain.add(att)
        if not added:
            raise HTTPException(status_code=400, detail="Invalid attestation — signature verification failed")
        return {
            "added": True,
            "total_attestations": len(chain.attestations),
            "attestation_id": att.attestation_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/chain/score/{agent_id:path}")
async def get_trust_score(agent_id: str, scope: Optional[str] = None):
    score = chain.trust_score(agent_id, scope=scope)
    atts = chain._by_subject.get(agent_id, [])
    return {
        "agent_id": agent_id,
        "trust_score": round(score, 4),
        "attestation_count": len(atts),
        "scope": scope,
    }


@app.post("/chain/transitive")
async def transitive_trust(req: TransitiveTrustRequest):
    score = chain.chain_trust(req.source_agent_id, req.target_agent_id, max_hops=req.max_hops)
    return {
        "source": req.source_agent_id,
        "target": req.target_agent_id,
        "trust": round(score, 4),
        "max_hops": req.max_hops,
    }


@app.get("/chain/dump")
async def dump_chain():
    return {
        "total": len(chain.attestations),
        "attestations": [a.to_dict() for a in chain.attestations],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420)
