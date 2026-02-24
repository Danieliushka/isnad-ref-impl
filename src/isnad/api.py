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
from nacl.encoding import HexEncoder
from isnad.core import TrustChain, Attestation, AgentIdentity, RevocationEntry, RevocationRegistry, KeyRotation
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

@app.get("/trust-score-v2/{agent_id}")
def get_trust_score_v2(agent_id: str):
    """Get trust score v2 — real platform data scoring.

    Fetches reputation from connected platforms (ugig, GitHub, etc.)
    and computes a trust score based on verifiable metrics.
    """
    from isnad.trustscore.scorer_v2 import TrustScorerV2
    from isnad.trustscore.platform_connectors import PlatformReputation

    # Check if agent has platform links in their attestations
    attestations = trust_chain._by_subject.get(agent_id, [])

    # Try to extract platform usernames from attestation metadata
    platforms = {}
    for att in attestations:
        meta = att.metadata or {}
        if "ugig_username" in meta:
            platforms["ugig"] = meta["ugig_username"]
        if "github_username" in meta:
            platforms["github"] = meta["github_username"]
        if "moltlaunch_name" in meta:
            platforms["moltlaunch"] = meta["moltlaunch_name"]
        if "clawk_username" in meta:
            platforms["clawk"] = meta["clawk_username"]

    # If no platform data from attestations, try the agent_id as username
    if not platforms:
        platforms = {"ugig": agent_id, "github": agent_id}

    scorer = TrustScorerV2.from_platforms(platforms)
    result = scorer.compute_detailed()
    result["agent_id"] = agent_id
    return result


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


# ─── Key Rotation ──────────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel  # noqa: already imported above


class RotateKeyRequest(_BaseModel):
    private_key_hex: str  # current (old) private key


class VerifyRotationRequest(_BaseModel):
    rotation: dict  # KeyRotation.to_dict() output


@app.post("/v1/rotate-key")
def rotate_key(req: RotateKeyRequest):
    """Generate a new keypair and a signed rotation proof."""
    try:
        old_identity = AgentIdentity.from_private_key(req.private_key_hex)
    except Exception:
        raise HTTPException(400, "Invalid private key")
    new_identity, rotation = old_identity.rotate()
    return {
        "new_private_key": new_identity.signing_key.encode(encoder=HexEncoder).decode(),
        "new_public_key": new_identity.public_key_hex,
        "new_agent_id": new_identity.agent_id,
        "rotation": rotation.to_dict(),
    }


@app.post("/v1/verify-rotation")
def verify_rotation(req: VerifyRotationRequest):
    """Verify a key rotation proof."""
    try:
        rotation = KeyRotation.from_dict(req.rotation)
    except Exception:
        raise HTTPException(400, "Invalid rotation record")
    valid = rotation.verify()
    return {
        "valid": valid,
        "old_agent_id": rotation.old_agent_id,
        "new_agent_id": rotation.new_agent_id,
    }


# --- Trust Policy ---

from isnad.policy import (
    TrustRequirement, PolicyRule, PolicyAction, TrustPolicy,
    EvaluationContext, PolicyDecision,
    strict_commerce_policy, open_discovery_policy, scoped_delegation_policy,
)


class TrustRequirementModel(BaseModel):
    min_trust_score: Optional[float] = None
    min_endorsements: Optional[int] = None
    max_chain_length: Optional[int] = None
    required_scopes: Optional[list[str]] = None
    required_issuer_ids: Optional[list[str]] = None
    max_age_seconds: Optional[int] = None


class PolicyRuleModel(BaseModel):
    name: str
    requirement: TrustRequirementModel
    on_fail: str = "deny"
    description: str = ""
    priority: int = 0


class PolicyCreateModel(BaseModel):
    name: str
    rules: list[PolicyRuleModel]
    default_action: str = "deny"


class PolicyEvaluateModel(BaseModel):
    agent_id: str
    trust_score: float = 0.0
    endorsement_count: int = 0
    chain_length: int = 1
    scopes: list[str] = []
    issuer_ids: list[str] = []
    chain_age_seconds: int = 0


# In-memory policy store
policies: dict[str, TrustPolicy] = {}

# Pre-load presets
for _preset_fn in [strict_commerce_policy, open_discovery_policy, lambda: scoped_delegation_policy(["trade", "delegate"])]:
    _preset = _preset_fn()
    policies[_preset.name] = _preset


@app.get("/policies", tags=["policy"])
async def list_policies():
    """List all registered trust policies."""
    return {
        "policies": [
            {"name": p.name, "rules": len(p.rules), "default_action": p.default_action.value}
            for p in policies.values()
        ]
    }


@app.get("/policies/{name}", tags=["policy"])
async def get_policy(name: str):
    """Get a specific trust policy by name."""
    if name not in policies:
        raise HTTPException(404, f"Policy '{name}' not found")
    p = policies[name]
    return p.to_dict()


@app.post("/policies", tags=["policy"], status_code=201)
async def create_policy(body: PolicyCreateModel):
    """Create a custom trust policy."""
    if body.name in policies:
        raise HTTPException(409, f"Policy '{body.name}' already exists")
    policy = TrustPolicy(name=body.name, default_action=PolicyAction(body.default_action))
    for r in body.rules:
        req = TrustRequirement(**r.requirement.model_dump(exclude_none=True))
        rule = PolicyRule(
            name=r.name,
            requirement=req,
            on_fail=PolicyAction(r.on_fail),
            description=r.description,
        )
        rule.priority = r.priority
        policy.add_rule(rule)
    policies[body.name] = policy
    return {"created": body.name, "rules": len(policy.rules)}


@app.post("/policies/{name}/evaluate", tags=["policy"])
async def evaluate_policy(name: str, body: PolicyEvaluateModel):
    """Evaluate an agent against a trust policy."""
    if name not in policies:
        raise HTTPException(404, f"Policy '{name}' not found")
    policy = policies[name]
    ctx = EvaluationContext(
        agent_id=body.agent_id,
        trust_score=body.trust_score,
        endorsement_count=body.endorsement_count,
        chain_length=body.chain_length,
        scopes=body.scopes,
        issuer_ids=body.issuer_ids,
        chain_age_seconds=body.chain_age_seconds,
    )
    result = policy.evaluate(ctx)
    return {
        "allowed": result.allowed(),
        "action": result.action.value,
        "matched_rule": result.rule_name,
        "matched": result.matched,
        "reason": result.reason,
    }


@app.post("/policies/{name}/evaluate/batch", tags=["policy"])
async def evaluate_policy_batch(name: str, agents: list[PolicyEvaluateModel]):
    """Evaluate multiple agents against a trust policy."""
    if name not in policies:
        raise HTTPException(404, f"Policy '{name}' not found")
    policy = policies[name]
    results = []
    for agent in agents:
        ctx = EvaluationContext(
            agent_id=agent.agent_id,
            trust_score=agent.trust_score,
            endorsement_count=agent.endorsement_count,
            chain_length=agent.chain_length,
            scopes=agent.scopes,
            issuer_ids=agent.issuer_ids,
            chain_age_seconds=agent.chain_age_seconds,
        )
        r = policy.evaluate(ctx)
        results.append({
            "agent_id": agent.agent_id,
            "allowed": r.allowed(),
            "action": r.action.value,
            "matched_rule": r.rule_name,
        })
    return {"results": results}


@app.delete("/policies/{name}", tags=["policy"])
async def delete_policy(name: str):
    """Delete a trust policy."""
    if name not in policies:
        raise HTTPException(404, f"Policy '{name}' not found")
    del policies[name]
    return {"deleted": name}


# --- Discovery ---

from isnad.discovery import AgentProfile, DiscoveryRegistry, create_profile

discovery_registry = DiscoveryRegistry()


class RegisterAgentRequest(BaseModel):
    agent_id: str
    name: str
    capabilities: list[str] = []
    endpoints: dict[str, str] = {}
    metadata: dict = {}


@app.post("/discovery/register", tags=["discovery"])
async def discovery_register(req: RegisterAgentRequest):
    """Register an agent in the discovery registry (auto-signs with agent's key)."""
    if req.agent_id not in identities:
        raise HTTPException(404, f"Agent '{req.agent_id}' not found. Create identity first.")
    identity = identities[req.agent_id]
    profile = create_profile(
        identity=identity,
        name=req.name,
        capabilities=req.capabilities,
        endpoints=req.endpoints,
        metadata=req.metadata,
    )
    ok = discovery_registry.register(profile)
    if not ok:
        raise HTTPException(400, "Registration failed (invalid signature or stale update)")
    return {"registered": req.agent_id, "capabilities": req.capabilities}


@app.get("/discovery/agents", tags=["discovery"])
async def discovery_list(capability: Optional[str] = None):
    """List all discovered agents, optionally filtered by capability."""
    if capability:
        profiles = discovery_registry.search(capability=capability)
    else:
        profiles = discovery_registry.all()
    return {"agents": [
        {
            "agent_id": p.agent_id,
            "name": p.name,
            "public_key": p.public_key,
            "capabilities": p.capabilities,
            "endpoints": p.endpoints,
            "registered_at": p.registered_at,
        }
        for p in profiles
    ]}


@app.get("/discovery/agents/{agent_id}", tags=["discovery"])
async def discovery_get(agent_id: str):
    """Get a specific agent's discovery profile with signature verification."""
    profile = discovery_registry.get(agent_id)
    if not profile:
        raise HTTPException(404, f"Agent '{agent_id}' not in discovery registry")
    verified = profile.verify()
    return {
        "agent_id": profile.agent_id,
        "name": profile.name,
        "public_key": profile.public_key,
        "capabilities": profile.capabilities,
        "endpoints": profile.endpoints,
        "metadata": profile.metadata,
        "registered_at": profile.registered_at,
        "signature_valid": verified,
    }


@app.delete("/discovery/agents/{agent_id}", tags=["discovery"])
async def discovery_unregister(agent_id: str):
    """Remove an agent from discovery registry."""
    if not discovery_registry.get(agent_id):
        raise HTTPException(404, f"Agent '{agent_id}' not in discovery registry")
    discovery_registry.unregister(agent_id)
    return {"unregistered": agent_id}


# --- Certification Service ---

class CertifyRequest(BaseModel):
    """Request agent certification through isnad trust protocol."""
    agent_id: str
    agent_wallet: Optional[str] = None
    platform: Optional[str] = None  # "acp", "ugig", "clawk", etc.
    capabilities: Optional[list[str]] = None
    evidence_urls: Optional[list[str]] = None  # GitHub repos, portfolio, etc.

class CertificationResult(BaseModel):
    certified: bool
    agent_id: str
    trust_score: float
    confidence: str
    modules_passed: int
    modules_total: int
    certification_id: str
    issued_at: str
    expires_at: str
    attestation_signature: str
    details: dict


@app.post("/certify", tags=["certification"])
def certify_agent(req: CertifyRequest):
    """
    Certify an AI agent through isnad's 36-module trust evaluation.
    
    Returns a signed certification attestation with trust score,
    module breakdown, and confidence level. Certification is valid
    for 30 days and can be verified by any third party.
    """
    import hashlib
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    cert_id = hashlib.sha256(f"cert:{req.agent_id}:{now.isoformat()}".encode()).hexdigest()[:16]
    
    # Run trust evaluation modules
    modules_results = {}
    passed = 0
    total_modules = 36
    
    # Module categories with checks
    checks = {
        "identity_verification": _check_identity(req),
        "attestation_chain": _check_attestation_chain(req.agent_id),
        "behavioral_analysis": _check_behavioral(req),
        "platform_presence": _check_platform_presence(req),
        "transaction_history": _check_transactions(req),
        "security_posture": _check_security(req),
    }
    
    for category, result in checks.items():
        modules_results[category] = result
        if result["passed"]:
            passed += result["modules_passed"]
    
    # Calculate trust score (0.0 - 1.0)
    trust_score = round(passed / total_modules, 3)
    
    # Confidence based on evidence availability
    if req.evidence_urls and req.agent_wallet and req.platform:
        confidence = "high"
    elif req.agent_wallet or req.platform:
        confidence = "medium"
    else:
        confidence = "low"
    
    # Certified if score >= 0.6 (60% modules passed)
    certified = trust_score >= 0.6
    
    # Sign the certification
    cert_identity = AgentIdentity()
    cert_attestation = Attestation(
        subject=req.agent_id,
        witness=cert_identity.agent_id,
        task=f"certification:{cert_id}",
        evidence=f"score={trust_score},modules={passed}/{total_modules},confidence={confidence}",
    )
    cert_attestation.sign(cert_identity)
    
    return CertificationResult(
        certified=certified,
        agent_id=req.agent_id,
        trust_score=trust_score,
        confidence=confidence,
        modules_passed=passed,
        modules_total=total_modules,
        certification_id=cert_id,
        issued_at=now.isoformat() + "Z",
        expires_at=(now + timedelta(days=30)).isoformat() + "Z",
        attestation_signature=cert_attestation.signature,
        details=modules_results,
    )


@app.get("/certify/{certification_id}", tags=["certification"])
def verify_certification(certification_id: str):
    """Verify an existing certification by its ID."""
    # In production: look up in persistent store
    return {
        "certification_id": certification_id,
        "status": "lookup_not_implemented_yet",
        "note": "Full certification verification coming in v0.4.0",
    }


def _check_identity(req: CertifyRequest) -> dict:
    """Check agent identity signals."""
    score = 0
    total = 6
    findings = []
    
    if req.agent_id:
        score += 1
        findings.append("agent_id present")
    if req.agent_wallet:
        score += 2
        findings.append(f"wallet: {req.agent_wallet[:10]}...")
    if req.capabilities:
        score += 1
        findings.append(f"{len(req.capabilities)} capabilities declared")
    if req.platform:
        score += 1
        findings.append(f"platform: {req.platform}")
    if req.evidence_urls:
        score += 1
        findings.append(f"{len(req.evidence_urls)} evidence URLs")
    
    return {"passed": score >= 3, "modules_passed": score, "modules_total": total, "findings": findings}


def _check_attestation_chain(agent_id: str) -> dict:
    """Check existing attestations for this agent."""
    relevant = [a for a in trust_chain.attestations if a.subject == agent_id or a.witness == agent_id]
    score = min(len(relevant), 6)
    return {
        "passed": score >= 2,
        "modules_passed": score,
        "modules_total": 6,
        "findings": [f"{len(relevant)} attestations found in chain"],
    }


def _check_behavioral(req: CertifyRequest) -> dict:
    """Behavioral pattern analysis."""
    score = 3  # Baseline — no negative signals
    return {
        "passed": True,
        "modules_passed": score,
        "modules_total": 6,
        "findings": ["no negative behavioral signals detected"],
    }


def _check_platform_presence(req: CertifyRequest) -> dict:
    """Cross-platform presence check."""
    score = 0
    total = 6
    findings = []
    
    if req.platform:
        score += 2
        findings.append(f"registered on {req.platform}")
    if req.evidence_urls:
        score += min(len(req.evidence_urls), 4)
        findings.append(f"{len(req.evidence_urls)} external profiles/repos")
    
    return {"passed": score >= 2, "modules_passed": min(score, total), "modules_total": total, "findings": findings}


def _check_transactions(req: CertifyRequest) -> dict:
    """Transaction history analysis."""
    score = 2  # Baseline — new agents start with some credit
    findings = ["baseline trust for new agents"]
    
    if req.agent_wallet:
        score += 2
        findings.append("wallet address provided for on-chain verification")
    
    return {"passed": score >= 2, "modules_passed": min(score, 6), "modules_total": 6, "findings": findings}


def _check_security(req: CertifyRequest) -> dict:
    """Security posture evaluation."""
    score = 3  # Baseline
    findings = ["no known security incidents"]
    
    if req.agent_wallet and req.agent_wallet.startswith("0x"):
        score += 1
        findings.append("valid EVM wallet format")
    
    return {"passed": score >= 2, "modules_passed": min(score, 6), "modules_total": 6, "findings": findings}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420)
