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
from isnad.core import TrustChain, Attestation, AgentIdentity, RevocationEntry, RevocationRegistry
from isnad.delegation import Delegation, DelegationRegistry

app = FastAPI(
    title="isnad API",
    description="Agent Trust Protocol — verify attestations, compute trust scores, manage identity chains.",
    version="0.1.0",
)

# --- In-memory store (demo) ---
identities: dict[str, AgentIdentity] = {}
revocation_registry = RevocationRegistry()
trust_chain = TrustChain(revocation_registry=revocation_registry)
delegation_registry = DelegationRegistry(revocation_registry=revocation_registry)


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

class BatchVerifyItem(BaseModel):
    subject: str
    witness: str
    task: str
    evidence: str = ""
    timestamp: str = ""
    signature: str = ""
    witness_pubkey: str = ""

class BatchVerifyRequest(BaseModel):
    attestations: list[BatchVerifyItem]

@app.post("/batch-verify")
def batch_verify(req: BatchVerifyRequest):
    """Batch verify multiple attestations in a single request."""
    results = []
    valid_count = 0
    for item in req.attestations:
        try:
            att = Attestation(
                subject=item.subject,
                witness=item.witness,
                task=item.task,
                evidence=item.evidence,
                timestamp=item.timestamp,
                signature=item.signature,
                witness_pubkey=item.witness_pubkey,
            )
            is_valid = att.verify()
            if is_valid:
                valid_count += 1
            results.append({"attestation_id": att.attestation_id, "valid": is_valid})
        except Exception as e:
            results.append({"valid": False, "error": str(e)})
    
    return {
        "total": len(req.attestations),
        "valid": valid_count,
        "invalid": len(req.attestations) - valid_count,
        "results": results,
    }

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

class RevokeRequest(BaseModel):
    target_id: str
    reason: str
    revoked_by: str
    scope: Optional[str] = None


@app.post("/revoke")
def revoke(req: RevokeRequest):
    """Revoke an agent or attestation. Revoked agents get zero trust score."""
    if req.revoked_by not in identities:
        raise HTTPException(404, f"Revoker identity {req.revoked_by} not found")
    
    entry = RevocationEntry(
        target_id=req.target_id,
        reason=req.reason,
        revoked_by=req.revoked_by,
        scope=req.scope,
    )
    entry.sign(identities[req.revoked_by])
    revocation_registry.revoke(entry)
    
    return {
        "status": "revoked",
        "target_id": req.target_id,
        "reason": req.reason,
        "scope": req.scope or "global",
        "revoked_by": req.revoked_by,
    }


@app.get("/revocations/{target_id}")
def get_revocations(target_id: str):
    """Check revocation status for an agent or attestation."""
    entries = revocation_registry.get_revocations(target_id)
    return {
        "target_id": target_id,
        "is_revoked": revocation_registry.is_revoked(target_id),
        "revocations": [e.to_dict() for e in entries],
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


# --- Atlas TrustScore Integration ---

class AtlasScoreRequest(BaseModel):
    agent_id: str
    threshold: Optional[float] = None  # For trust gate

@app.post("/atlas/score")
def atlas_score(req: AtlasScoreRequest):
    """Get combined isnad + Atlas TrustScore for an agent."""
    try:
        from isnad.trustscore.atlas import AtlasIntegration
    except ImportError:
        raise HTTPException(status_code=503, detail="httpx not installed — Atlas integration unavailable")

    with AtlasIntegration(trust_chain) as atlas:
        score = atlas.score_agent(req.agent_id)
        return score.to_dict()

@app.post("/atlas/gate")
def atlas_gate(req: AtlasScoreRequest):
    """Binary trust gate: allow/deny based on combined isnad + Atlas score."""
    try:
        from isnad.trustscore.atlas import AtlasIntegration
    except ImportError:
        raise HTTPException(status_code=503, detail="httpx not installed — Atlas integration unavailable")

    threshold = req.threshold or 0.5
    with AtlasIntegration(trust_chain) as atlas:
        result = atlas.trust_gate(req.agent_id, threshold=threshold)
        return result


# --- Delegation Models ---

class DelegationRequest(BaseModel):
    delegator_id: str  # agent_id of delegator (must have registered identity)
    delegate_pubkey: str  # public key hex of delegate
    scope: str  # e.g., "attest:code-review"
    expires_in_hours: float = 24.0
    max_depth: int = 1

class SubDelegationRequest(BaseModel):
    parent_hash: str
    delegator_id: str  # agent doing the sub-delegation
    delegate_pubkey: str
    scope: Optional[str] = None
    expires_in_hours: Optional[float] = None


# --- Delegation Endpoints ---

@app.post("/delegations")
def create_delegation(req: DelegationRequest):
    """Create a new delegation of authority."""
    if req.delegator_id not in identities:
        raise HTTPException(status_code=404, detail=f"Delegator {req.delegator_id} not found")
    
    delegator = identities[req.delegator_id]
    from datetime import datetime, timezone, timedelta
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=req.expires_in_hours)).isoformat()
    
    d = Delegation(
        delegator="", delegate=req.delegate_pubkey,
        scope=req.scope, expires_at=expires_at, max_depth=req.max_depth
    )
    d = delegation_registry.add(d, delegator.signing_key)
    return {"delegation_hash": d.content_hash, "delegation": d.to_dict()}

@app.post("/delegations/sub-delegate")
def sub_delegate(req: SubDelegationRequest):
    """Create a sub-delegation from an existing delegation."""
    if req.delegator_id not in identities:
        raise HTTPException(status_code=404, detail=f"Delegator {req.delegator_id} not found")
    
    delegator = identities[req.delegator_id]
    from datetime import datetime, timezone, timedelta
    expires_at = None
    if req.expires_in_hours:
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=req.expires_in_hours)).isoformat()
    
    try:
        d = delegation_registry.sub_delegate(
            req.parent_hash, req.delegate_pubkey,
            delegator.signing_key, scope=req.scope, expires_at=expires_at
        )
        return {"delegation_hash": d.content_hash, "delegation": d.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/delegations/verify/{delegation_hash}")
def verify_delegation_chain(delegation_hash: str):
    """Verify an entire delegation chain."""
    valid, message = delegation_registry.verify_chain(delegation_hash)
    return {"valid": valid, "message": message}

@app.get("/delegations/for/{delegate_pubkey}")
def get_delegations_for(delegate_pubkey: str, scope: Optional[str] = None):
    """Get all active delegations for a delegate."""
    delegations = delegation_registry.get_delegations_for(delegate_pubkey, scope=scope)
    return {
        "delegate": delegate_pubkey,
        "count": len(delegations),
        "delegations": [d.to_dict() for d in delegations]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420)
