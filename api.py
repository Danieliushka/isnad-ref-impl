#!/usr/bin/env python3
"""
isnad API — Trust-as-a-Service
Verify agent attestations, compute trust scores, manage identity chains.
"""

import os
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(__file__))
from isnad import TrustChain, Attestation, AgentIdentity

app = FastAPI(
    title="isnad API",
    description="Agent Trust Protocol — verify attestations, compute trust scores, manage identity chains.",
    version="0.1.0",
)

# --- In-memory store (demo) ---
identities: dict[str, AgentIdentity] = {}
trust_chain = TrustChain()


# --- Models ---

class CreateIdentityRequest(BaseModel):
    name: Optional[str] = None

class AttestRequest(BaseModel):
    subject_id: str
    witness_id: str
    task: str
    evidence: str = ""

class VerifyRequest(BaseModel):
    subject: str
    witness: str
    task: str
    evidence: str = ""
    timestamp: str = ""
    signature: str = ""
    witness_pubkey: str = ""

class TrustScoreRequest(BaseModel):
    agent_id: str
    scope: Optional[str] = None


# --- Endpoints ---

@app.get("/")
def root():
    return {
        "service": "isnad API",
        "version": "0.1.0",
        "protocol": "Agent Trust Protocol — Ed25519 attestation chains + trust scoring",
        "docs": "/docs",
        "github": "https://github.com/gendolf-agent/isnad-ref-impl",
    }

@app.post("/identity")
def create_identity(req: CreateIdentityRequest):
    """Create a new agent identity with Ed25519 keypair."""
    identity = AgentIdentity()
    identities[identity.agent_id] = identity
    return {
        "agent_id": identity.agent_id,
        "public_key": identity.public_key_hex,
    }

@app.post("/attest")
def create_attestation(req: AttestRequest):
    """Create a signed attestation: witness attests that subject completed a task."""
    if req.witness_id not in identities:
        raise HTTPException(404, f"Witness identity {req.witness_id} not found. Create it first via /identity")
    
    witness = identities[req.witness_id]
    attestation = Attestation(
        subject=req.subject_id,
        witness=req.witness_id,
        task=req.task,
        evidence=req.evidence,
    )
    attestation.sign(witness)
    added = trust_chain.add(attestation)
    
    if not added:
        raise HTTPException(400, "Attestation verification failed")
    
    return {
        "attestation_id": attestation.attestation_id,
        "subject": attestation.subject,
        "witness": attestation.witness,
        "task": attestation.task,
        "timestamp": attestation.timestamp,
        "signature": attestation.signature,
        "chain_size": len(trust_chain.attestations),
    }

@app.post("/verify")
def verify_attestation(req: VerifyRequest):
    """Verify a standalone attestation's signature."""
    try:
        att = Attestation(
            subject=req.subject,
            witness=req.witness,
            task=req.task,
            evidence=req.evidence,
            timestamp=req.timestamp,
            signature=req.signature,
            witness_pubkey=req.witness_pubkey,
        )
        valid = att.verify()
        return {"valid": valid, "attestation_id": att.attestation_id}
    except Exception as e:
        return {"valid": False, "error": str(e)}

@app.get("/trust-score/{agent_id}")
def get_trust_score(agent_id: str, scope: Optional[str] = None):
    """Get trust score for an agent based on their attestation history."""
    score = trust_chain.trust_score(agent_id, scope)
    attestations = trust_chain._by_subject.get(agent_id, [])
    witnesses = set(a.witness for a in attestations)
    return {
        "agent_id": agent_id,
        "trust_score": round(score, 4),
        "attestation_count": len(attestations),
        "unique_witnesses": len(witnesses),
    }

@app.get("/chain")
def get_chain_stats():
    """Get overall chain statistics."""
    return {
        "total_attestations": len(trust_chain.attestations),
        "unique_subjects": len(trust_chain._by_subject),
        "unique_witnesses": len(trust_chain._by_witness),
    }

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420)
