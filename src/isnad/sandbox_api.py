#!/usr/bin/env python3
"""
isnad sandbox — Pilot endpoints for testing attestation signing & verification.
Ed25519 keys in JWK format, as requested by Kit_Fox.
"""

import base64
import json
import time
import threading
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from isnad.core import AgentIdentity, Attestation, TrustChain
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder

app = FastAPI(
    title="isnad Sandbox",
    description="Pilot sandbox for testing attestation signing, verification, and trust scoring. Ed25519 JWK format.",
    version="0.1.0-sandbox",
)

from fastapi.responses import HTMLResponse

# Load landing page from docs/site/index.html if available
import os as _os
_site_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "docs", "site", "index.html")
if _os.path.exists(_site_path):
    with open(_site_path, "r") as _f:
        LANDING_HTML = _f.read()
else:
    LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>isnad — Agent Trust Protocol</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0a0a0a;color:#e0e0e0;min-height:100vh;display:flex;flex-direction:column;align-items:center}
.hero{max-width:800px;margin:60px auto 0;padding:0 24px;text-align:center}
h1{font-size:2.8rem;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px}
.sub{font-size:1.2rem;color:#999;margin-bottom:40px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;width:100%;max-width:800px;margin:0 auto 40px;padding:0 24px}
.card{background:#161616;border:1px solid #2a2a2a;border-radius:12px;padding:20px;text-align:left;transition:border-color .2s}
.card:hover{border-color:#60a5fa}
.card h3{color:#60a5fa;margin-bottom:8px;font-size:1rem}
.card p{color:#888;font-size:.9rem;line-height:1.5}
.try{max-width:800px;width:100%;padding:0 24px;margin-bottom:40px}
.try h2{font-size:1.4rem;margin-bottom:16px;color:#a78bfa}
pre{background:#161616;border:1px solid #2a2a2a;border-radius:8px;padding:16px;overflow-x:auto;font-size:.85rem;color:#60a5fa;line-height:1.6}
.btn{display:inline-block;margin-top:20px;padding:10px 24px;background:#60a5fa;color:#0a0a0a;border-radius:8px;text-decoration:none;font-weight:600;transition:background .2s}
.btn:hover{background:#a78bfa}
.stats{display:flex;gap:32px;justify-content:center;margin:32px 0;flex-wrap:wrap}
.stat{text-align:center}
.stat .n{font-size:2rem;font-weight:700;color:#60a5fa}
.stat .l{font-size:.85rem;color:#888}
footer{margin-top:auto;padding:24px;color:#555;font-size:.8rem}
</style>
</head>
<body>
<div class="hero">
<h1>isnad</h1>
<p class="sub">Cryptographic trust chains for AI agents.<br>Verify identity. Attest behavior. Score trust.</p>
<div class="stats">
<div class="stat"><div class="n">117</div><div class="l">Tests Passing</div></div>
<div class="stat"><div class="n">6</div><div class="l">MCP Tools</div></div>
<div class="stat"><div class="n">Ed25519</div><div class="l">Crypto</div></div>
<div class="stat"><div class="n">REST + CLI</div><div class="l">Interfaces</div></div>
</div>
</div>

<div class="cards">
<div class="card"><h3>🔐 Agent Identity</h3><p>Ed25519 keypairs in JWK format. Each agent gets a cryptographically verifiable identity.</p></div>
<div class="card"><h3>📜 Attestations</h3><p>Signed claims about agent behavior. Immutable, timestamped, verifiable by anyone.</p></div>
<div class="card"><h3>🔗 Trust Chains</h3><p>Multi-hop trust verification. If A trusts B and B trusts C — verify the entire chain.</p></div>
<div class="card"><h3>📊 Trust Scoring</h3><p>Dynamic scores based on attestation history, recency, and cross-agent verification.</p></div>
<div class="card"><h3>🛠️ MCP Server</h3><p>6 tools for Claude, GPT, and any MCP-compatible agent to verify trust natively.</p></div>
<div class="card"><h3>🏢 Enterprise Ready</h3><p>Batch operations, audit trails, compliance reports, webhook notifications.</p></div>
</div>

<div class="try">
<h2>Try it now</h2>
<pre>
# Generate agent keypair
curl -X POST /sandbox/keys/generate \\
  -H "Content-Type: application/json" \\
  -d '{"agent_id": "my-agent"}'

# Create attestation
curl -X POST /sandbox/attestations/create \\
  -H "Content-Type: application/json" \\
  -d '{"issuer_id": "my-agent", "subject_id": "other-agent", "claim": "verified_output", "confidence": 0.95}'

# Check trust score
curl /sandbox/trust/score?agent_id=other-agent
</pre>
<a href="/docs" class="btn">Interactive API Docs →</a>
<a href="https://github.com/Danieliushka/isnad-ref-impl" class="btn" style="margin-left:8px;background:#2a2a2a;color:#e0e0e0">GitHub →</a>
</div>

<footer>isnad Agent Trust Protocol — CC0 License — Built by <a href="https://clawk.ai/gendolf" style="color:#60a5fa;text-decoration:none">@gendolf</a></footer>
</body>
</html>"""


def _load_landing():
    import os
    # Try multiple paths
    for base in [
        os.path.dirname(os.path.abspath(__file__)),
        "/root/.openclaw/workspace/projects/isnad-ref-impl/src/isnad",
    ]:
        site_path = os.path.join(base, "..", "..", "docs", "site", "index.html")
        if os.path.exists(site_path):
            with open(site_path, "r") as f:
                return f.read()
    return LANDING_HTML

@app.get("/", response_class=HTMLResponse)
async def landing():
    """Landing page with project overview and quick-start examples."""
    return _load_landing()

# --- In-memory stores ---
_identities: dict[str, AgentIdentity] = {}  # agent_id -> identity
_jwk_map: dict[str, dict] = {}  # agent_id -> JWK keypair (public + private)
_chain = TrustChain()
_webhooks: list[dict] = []  # {"url": str, "events": list[str], "filter_issuer": str|None, "filter_subject": str|None}


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

class BatchVerifyRequest(BaseModel):
    attestations: list[VerifyAttestationRequest]

class WebhookSubscribeRequest(BaseModel):
    url: str
    events: list[str] = ["attestation.created", "chain.extended", "score.updated"]
    filter_issuer: Optional[str] = None
    filter_subject: Optional[str] = None


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
            "POST /sandbox/attestations/batch-verify",
            "GET  /sandbox/chain/{agent_id}",
            "GET  /sandbox/agent/{agent_id}/reputation",
            "POST /sandbox/trust/score",
            "POST /sandbox/webhooks/subscribe",
            "GET  /sandbox/webhooks",
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

    att_dict = att.to_dict()
    _dispatch_webhooks("attestation.created", att_dict)
    if len(_chain.attestations) > 1:
        _dispatch_webhooks("chain.extended", {"agent_id": req.subject_id, "chain_size": len(_chain.attestations)})

    return {
        "attestation": att_dict,
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


def _dispatch_webhooks(event: str, payload: dict):
    """Fire-and-forget webhook delivery in background thread."""
    def _send():
        for wh in _webhooks:
            if event not in wh["events"]:
                continue
            if wh.get("filter_issuer") and payload.get("witness") != wh["filter_issuer"]:
                continue
            if wh.get("filter_subject") and payload.get("subject") != wh["filter_subject"]:
                continue
            try:
                httpx.post(wh["url"], json={"event": event, "data": payload}, timeout=5)
            except Exception:
                pass  # best-effort delivery
    threading.Thread(target=_send, daemon=True).start()


@app.post("/sandbox/attestations/batch-verify")
def batch_verify(req: BatchVerifyRequest):
    """Verify multiple attestations in a single call. Returns per-attestation results."""
    results = []
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
            valid = att.verify()
            results.append({"attestation_id": att.attestation_id, "valid": valid})
        except Exception as e:
            results.append({"valid": False, "error": str(e)})
    return {
        "total": len(results),
        "valid_count": sum(1 for r in results if r.get("valid")),
        "results": results,
    }


@app.get("/sandbox/agent/{agent_id}/reputation")
def agent_reputation(agent_id: str):
    """Full reputation summary for an agent: score, attestation history, peer graph."""
    received = _chain._by_subject.get(agent_id, [])
    given = _chain._by_witness.get(agent_id, [])
    witnesses = set(a.witness for a in received)
    subjects = set(a.subject for a in given)
    score = _chain.trust_score(agent_id)

    # Task distribution
    tasks = {}
    for a in received:
        tasks[a.task] = tasks.get(a.task, 0) + 1

    return {
        "agent_id": agent_id,
        "trust_score": round(score, 4),
        "attestations_received": len(received),
        "attestations_given": len(given),
        "unique_witnesses": len(witnesses),
        "unique_subjects_attested": len(subjects),
        "task_distribution": tasks,
        "peers": {
            "witnesses": list(witnesses),
            "attested_for": list(subjects),
        },
    }


@app.post("/sandbox/webhooks/subscribe")
def webhook_subscribe(req: WebhookSubscribeRequest):
    """Subscribe a URL to receive event callbacks (attestation.created, chain.extended, score.updated)."""
    valid_events = {"attestation.created", "chain.extended", "score.updated"}
    invalid = set(req.events) - valid_events
    if invalid:
        raise HTTPException(400, f"Invalid events: {invalid}. Valid: {valid_events}")
    sub = {
        "id": f"wh_{len(_webhooks)+1}",
        "url": req.url,
        "events": req.events,
        "filter_issuer": req.filter_issuer,
        "filter_subject": req.filter_subject,
    }
    _webhooks.append(sub)
    return {"subscription": sub, "active_webhooks": len(_webhooks)}


@app.get("/sandbox/webhooks")
def list_webhooks():
    """List active webhook subscriptions."""
    return {"webhooks": _webhooks, "count": len(_webhooks)}


@app.get("/sandbox/health")
def health():
    return {"status": "ok", "timestamp": time.time(), "chain_size": len(_chain.attestations)}


if __name__ == "__main__":
    import uvicorn
    print("🧪 isnad Sandbox starting on http://localhost:8421")
    print("📖 Docs at http://localhost:8421/docs")
    uvicorn.run(app, host="0.0.0.0", port=8420)
