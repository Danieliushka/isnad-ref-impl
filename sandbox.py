#!/usr/bin/env python3
"""
isnad sandbox — Pilot endpoints for testing attestation signing & verification.
Ed25519 keys in JWK format, as requested by Kit_Fox.
"""

import base64
import json
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from isnad import AgentIdentity, Attestation, TrustChain
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder

app = FastAPI(
    title="isnad Sandbox",
    description="Pilot sandbox for testing attestation signing, verification, and trust scoring. Ed25519 JWK format.",
    version="0.1.0-sandbox",
)

# --- In-memory stores ---
_identities: dict[str, AgentIdentity] = {}  # agent_id -> identity
_jwk_map: dict[str, dict] = {}  # agent_id -> JWK keypair (public + private)
_chain = TrustChain()


# --- Helpers ---

def _b64url(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    """Base64url decode with padding recovery."""
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _identity_to_jwk(identity: AgentIdentity) -> dict:
    """Export an AgentIdentity as Ed25519 JWK (public + private)."""
    # Ed25519 raw keys: private = 32 bytes seed, public = 32 bytes
    private_bytes = identity.signing_key.encode(encoder=RawEncoder)  # 32-byte seed
    public_bytes = identity.verify_key.encode(encoder=RawEncoder)    # 32-byte pubkey

    public_jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64url(public_bytes),
    }
    private_jwk = {
        **public_jwk,
        "d": _b64url(private_bytes),
    }
    return {"public": public_jwk, "private": private_jwk}


def _get_identity(agent_id: str) -> AgentIdentity:
    if agent_id not in _identities:
        raise HTTPException(404, f"Agent {agent_id} not found. Generate keys first.")
    return _identities[agent_id]


# --- Models ---

class CreateAttestationRequest(BaseModel):
    subject_id: str
    witness_id: str
    task: str
    evidence: str = ""

class VerifyAttestationRequest(BaseModel):
    subject: str
    witness: str
    task: str
    evidence: str = ""
    timestamp: str
    signature: str
    witness_pubkey: str

class TrustScoreRequest(BaseModel):
    agent_id: str
    scope: Optional[str] = None


# --- Endpoints ---

@app.get("/sandbox")
def sandbox_root():
    return {
        "service": "isnad Sandbox",
        "version": "0.1.0-sandbox",
        "endpoints": [
            "POST /sandbox/keys/generate",
            "POST /sandbox/attestations/create",
            "POST /sandbox/attestations/verify",
            "GET  /sandbox/chain/{agent_id}",
            "POST /sandbox/trust/score",
        ],
    }


@app.post("/sandbox/keys/generate")
def generate_keys():
    """Generate Ed25519 keypair, return in JWK format."""
    identity = AgentIdentity()
    agent_id = identity.agent_id
    _identities[agent_id] = identity
    jwk = _identity_to_jwk(identity)
    _jwk_map[agent_id] = jwk
    return {
        "agent_id": agent_id,
        "keys": jwk,
    }


@app.post("/sandbox/attestations/create")
def create_attestation(req: CreateAttestationRequest):
    """Create and sign an attestation. Witness must have generated keys first."""
    witness = _get_identity(req.witness_id)

    att = Attestation(
        subject=req.subject_id,
        witness=req.witness_id,
        task=req.task,
        evidence=req.evidence,
    )
    att.sign(witness)

    added = _chain.add(att)
    if not added:
        raise HTTPException(400, "Attestation signature verification failed after signing (bug?)")

    return {
        "attestation": att.to_dict(),
        "chain_size": len(_chain.attestations),
        "added_to_chain": True,
    }


@app.post("/sandbox/attestations/verify")
def verify_attestation(req: VerifyAttestationRequest):
    """Verify an attestation signature. Provide the full attestation fields."""
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
    return {
        "valid": valid,
        "attestation_id": att.attestation_id,
    }


@app.get("/sandbox/chain/{agent_id}")
def get_chain(agent_id: str):
    """Get attestation chain for an agent (as subject)."""
    attestations = _chain._by_subject.get(agent_id, [])
    witnessed = _chain._by_witness.get(agent_id, [])
    return {
        "agent_id": agent_id,
        "received_attestations": [a.to_dict() for a in attestations],
        "given_attestations": [a.to_dict() for a in witnessed],
        "received_count": len(attestations),
        "given_count": len(witnessed),
    }


@app.post("/sandbox/trust/score")
def trust_score(req: TrustScoreRequest):
    """Calculate TrustScore for an agent based on their attestation chain."""
    score = _chain.trust_score(req.agent_id, scope=req.scope)
    attestations = _chain._by_subject.get(req.agent_id, [])
    witnesses = set(a.witness for a in attestations)
    return {
        "agent_id": req.agent_id,
        "trust_score": round(score, 4),
        "attestation_count": len(attestations),
        "unique_witnesses": len(witnesses),
        "scope": req.scope,
    }


@app.get("/sandbox/health")
def health():
    return {"status": "ok", "timestamp": time.time(), "chain_size": len(_chain.attestations)}


if __name__ == "__main__":
    import uvicorn
    print("🧪 isnad Sandbox starting on http://localhost:8421")
    print("📖 Docs at http://localhost:8421/docs")
    uvicorn.run(app, host="0.0.0.0", port=8421)
