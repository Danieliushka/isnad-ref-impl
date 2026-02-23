#!/usr/bin/env python3
"""
isnad REST API — FastAPI server for enterprise evaluation.
Provides HTTP endpoints for all isnad trust chain operations.

Usage:
    uvicorn api_server:app --host 0.0.0.0 --port 8000
    # or: python api_server.py
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import time

from isnad import AgentIdentity, Attestation, TrustChain
from isnad.api_v1 import router as v1_router, configure as configure_v1

app = FastAPI(
    title="Isnad Trust Protocol API",
    description=(
        "REST API for isnad attestation chains — cryptographic trust for AI agents.\n\n"
        "**Core concepts:**\n"
        "- **Identity**: Ed25519 keypair for an agent\n"
        "- **Attestation**: Signed claim — 'Agent A completed task X, witnessed by B'\n"
        "- **TrustChain**: Collection of attestations with trust scoring\n"
        "- **TrustScore**: Computed trust based on attestation chains with decay\n\n"
        "GitHub: [isnad-ref-impl](https://github.com/gendolf-bot/isnad-ref-impl)"
    ),
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# In-memory stores (swap for DB in production)
_identities: dict[str, AgentIdentity] = {}
_chain = TrustChain()


# ─── Models ────────────────────────────────────────────────────────

class CreateIdentityResponse(BaseModel):
    agent_id: str
    public_key: str

class AttestRequest(BaseModel):
    witness_id: str = Field(..., description="Agent ID of the witness (signer)")
    subject_id: str = Field(..., description="Agent ID being attested")
    task: str = Field(..., description="What the subject did/achieved")
    evidence: str = Field("", description="URI to artifact/proof")

class AttestResponse(BaseModel):
    attestation_id: str
    witness: str
    subject: str
    task: str
    evidence: str
    timestamp: str
    verified: bool

class TrustScoreResponse(BaseModel):
    agent_id: str
    score: float
    attestation_count: int

class ChainTrustResponse(BaseModel):
    source: str
    target: str
    trust: float
    max_hops: int

class BatchAttestRequest(BaseModel):
    attestations: list[AttestRequest] = Field(..., description="List of attestations to create")

class BatchAttestResponse(BaseModel):
    created: int
    failed: int
    results: list[dict]

class BatchVerifyRequest(BaseModel):
    attestation_ids: list[str] = Field(..., description="Attestation IDs to verify")

class ImportChainRequest(BaseModel):
    attestations: list[dict] = Field(..., description="Exported attestation dicts")
    identities: dict[str, str] = Field(default_factory=dict, description="agent_id → public_key_hex map")


# ─── V1 Router ─────────────────────────────────────────────────────

configure_v1(identities=_identities, trust_chain=_chain)
app.include_router(v1_router)

# ─── Legacy Endpoints ──────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "version": "0.3.0",
        "protocol": "isnad",
        "identities": len(_identities),
        "attestations": len(_chain.attestations),
    }


@app.post("/identities", response_model=CreateIdentityResponse, tags=["Identity"])
async def create_identity():
    """Create a new agent identity (Ed25519 keypair)."""
    identity = AgentIdentity()
    _identities[identity.agent_id] = identity
    return CreateIdentityResponse(
        agent_id=identity.agent_id,
        public_key=identity.public_key_hex,
    )


@app.get("/identities", tags=["Identity"])
async def list_identities():
    """List all registered identities."""
    return {
        "identities": [
            {"agent_id": aid, "public_key": ident.public_key_hex}
            for aid, ident in _identities.items()
        ],
        "count": len(_identities),
    }


@app.get("/identities/{agent_id}", tags=["Identity"])
async def get_identity(agent_id: str):
    """Get identity details and trust score."""
    if agent_id not in _identities:
        raise HTTPException(404, f"Identity {agent_id} not found")
    ident = _identities[agent_id]
    score = _chain.trust_score(agent_id)
    return {
        "agent_id": agent_id,
        "public_key": ident.public_key_hex,
        "trust_score": score,
    }


@app.post("/attest", response_model=AttestResponse, tags=["Attestation"])
async def create_attestation(req: AttestRequest):
    """Create, sign, and add an attestation to the chain.

    The witness signs a claim that the subject completed a task.
    Only valid (cryptographically verified) attestations are accepted.
    """
    if req.witness_id not in _identities:
        raise HTTPException(404, f"Witness {req.witness_id} not found. Create identity first.")
    if req.subject_id not in _identities:
        raise HTTPException(404, f"Subject {req.subject_id} not found. Create identity first.")

    witness = _identities[req.witness_id]

    att = Attestation(
        subject=req.subject_id,
        witness=req.witness_id,
        task=req.task,
        evidence=req.evidence,
    )
    att.sign(witness)

    added = _chain.add(att)
    if not added:
        raise HTTPException(400, "Attestation failed verification")

    return AttestResponse(
        attestation_id=att.attestation_id,
        witness=req.witness_id,
        subject=req.subject_id,
        task=req.task,
        evidence=req.evidence,
        timestamp=att.timestamp,
        verified=True,
    )


@app.get("/attestations", tags=["Attestation"])
async def list_attestations(subject: Optional[str] = None, witness: Optional[str] = None):
    """List attestations, optionally filtered by subject or witness."""
    atts = _chain.attestations
    if subject:
        atts = [a for a in atts if a.subject == subject]
    if witness:
        atts = [a for a in atts if a.witness == witness]
    return {
        "attestations": [a.to_dict() for a in atts],
        "count": len(atts),
    }


@app.get("/trust/{agent_id}", response_model=TrustScoreResponse, tags=["Trust"])
async def get_trust_score(agent_id: str, scope: Optional[str] = None):
    """Compute trust score for an agent.

    Score is based on attestation count, diversity of witnesses,
    and temporal decay (recent attestations weigh more).
    """
    if agent_id not in _identities:
        raise HTTPException(404, f"Agent {agent_id} not found")
    score = _chain.trust_score(agent_id, scope=scope)
    att_count = len(_chain._by_subject.get(agent_id, []))
    return TrustScoreResponse(
        agent_id=agent_id,
        score=score,
        attestation_count=att_count,
    )


@app.get("/trust/{source_id}/to/{target_id}", response_model=ChainTrustResponse, tags=["Trust"])
async def get_chain_trust(source_id: str, target_id: str, max_hops: int = 5):
    """Compute transitive trust from source to target through attestation chains.

    Uses BFS with decay: trust reduces by 30% per hop (CHAIN_DECAY=0.7).
    Repeated same-witness chains are penalized (SAME_WITNESS_DECAY=0.5).
    """
    for aid in [source_id, target_id]:
        if aid not in _identities:
            raise HTTPException(404, f"Agent {aid} not found")
    trust = _chain.chain_trust(source_id, target_id, max_hops=max_hops)
    return ChainTrustResponse(
        source=source_id,
        target=target_id,
        trust=trust,
        max_hops=max_hops,
    )


@app.get("/chain/verify", tags=["Chain"])
async def verify_chain():
    """Verify all attestations in the chain."""
    results = []
    all_valid = True
    for att in _chain.attestations:
        valid = att.verify()
        if not valid:
            all_valid = False
        results.append({
            "attestation_id": att.attestation_id,
            "valid": valid,
        })
    return {
        "chain_valid": all_valid,
        "total": len(results),
        "results": results,
    }


@app.get("/chain/export", tags=["Chain"])
async def export_chain():
    """Export entire chain as JSON (for backup/transport)."""
    return {
        "version": "0.3.0",
        "exported_at": time.time(),
        "attestations": [a.to_dict() for a in _chain.attestations],
        "identities": {
            aid: ident.public_key_hex for aid, ident in _identities.items()
        },
    }


@app.post("/attest/batch", response_model=BatchAttestResponse, tags=["Attestation"])
async def batch_attest(req: BatchAttestRequest):
    """Create multiple attestations in one call.

    Returns results for each attestation. Partial success is possible —
    some may fail while others succeed.
    """
    created = 0
    failed = 0
    results = []
    for i, att_req in enumerate(req.attestations):
        try:
            if att_req.witness_id not in _identities:
                raise ValueError(f"Witness {att_req.witness_id} not found")
            if att_req.subject_id not in _identities:
                raise ValueError(f"Subject {att_req.subject_id} not found")
            witness = _identities[att_req.witness_id]
            att = Attestation(
                subject=att_req.subject_id,
                witness=att_req.witness_id,
                task=att_req.task,
                evidence=att_req.evidence,
            )
            att.sign(witness)
            if not _chain.add(att):
                raise ValueError("Attestation failed verification")
            created += 1
            results.append({"index": i, "status": "created", "attestation_id": att.attestation_id})
        except (ValueError, KeyError) as e:
            failed += 1
            results.append({"index": i, "status": "failed", "error": str(e)})
    return BatchAttestResponse(created=created, failed=failed, results=results)


@app.post("/chain/import", tags=["Chain"])
async def import_chain(req: ImportChainRequest):
    """Import attestations from an exported chain.

    Use with /chain/export to transfer trust chains between systems.
    Identities in the import are registered as public-key-only (no private keys).
    """
    imported = 0
    skipped = 0
    for att_dict in req.attestations:
        try:
            att = Attestation.from_dict(att_dict)
            if _chain.add(att):
                imported += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    return {
        "imported": imported,
        "skipped": skipped,
        "total_attestations": len(_chain.attestations),
    }


@app.get("/trust/{agent_id}/history", tags=["Trust"])
async def trust_history(agent_id: str):
    """Get trust audit trail — all attestations involving this agent.

    Returns attestations where the agent is either subject or witness,
    with current trust score. Useful for compliance/audit.
    """
    as_subject = [a.to_dict() for a in _chain.attestations if a.subject == agent_id]
    as_witness = [a.to_dict() for a in _chain.attestations if a.witness == agent_id]
    score = _chain.trust_score(agent_id) if agent_id in _identities else 0.0
    return {
        "agent_id": agent_id,
        "current_trust_score": score,
        "as_subject": as_subject,
        "as_witness": as_witness,
        "total_involvement": len(as_subject) + len(as_witness),
    }


@app.get("/stats", tags=["Chain"])
async def chain_stats():
    """Chain statistics — overview for monitoring/dashboards."""
    agents = set()
    scopes = set()
    for att in _chain.attestations:
        agents.add(att.subject)
        agents.add(att.witness)
        if hasattr(att, 'task'):
            scopes.add(att.task)
    return {
        "total_identities": len(_identities),
        "total_attestations": len(_chain.attestations),
        "unique_agents_in_chain": len(agents),
        "unique_scopes": len(scopes),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
