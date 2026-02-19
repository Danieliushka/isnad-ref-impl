#!/usr/bin/env python3
"""
isnad.portable — Portable Trust Chain Export/Import

Export trust chains as self-contained JSON bundles that can be verified
independently. This enables cross-platform agent reputation portability.

Format: Isnad Portable Trust Bundle (IPTB) v1
"""

import json
import time
import hashlib
from typing import Optional
from dataclasses import dataclass, field, asdict

from isnad.core import (
    TrustChain, Attestation, AgentIdentity,
    RevocationRegistry,
)


IPTB_VERSION = "1.0"


@dataclass
class PortableAttestation:
    """Attestation in portable format (no objects, just data)."""
    subject: str
    witness: str
    witness_pubkey: str
    task: str
    evidence: str
    timestamp: str
    signature: str
    attestation_id: str

    @classmethod
    def from_attestation(cls, att: Attestation) -> "PortableAttestation":
        return cls(
            subject=att.subject,
            witness=att.witness,
            witness_pubkey=att.witness_pubkey or "",
            task=att.task,
            evidence=att.evidence,
            timestamp=att.timestamp,
            signature=att.signature or "",
            attestation_id=att.attestation_id,
        )


@dataclass
class PortableRevocation:
    """Revocation entry in portable format."""
    target_id: str
    reason: str
    revoker: str
    timestamp: str


@dataclass
class TrustBundle:
    """
    Isnad Portable Trust Bundle (IPTB).
    
    Self-contained package of an agent's trust chain that can be
    verified by any isnad-compatible system.
    """
    version: str = IPTB_VERSION
    agent_id: str = ""
    agent_pubkey: str = ""
    exported_at: float = 0.0
    attestations: list[PortableAttestation] = field(default_factory=list)
    revocations: list[PortableRevocation] = field(default_factory=list)
    trust_score: Optional[float] = None
    metadata: dict = field(default_factory=dict)
    bundle_hash: str = ""

    def compute_hash(self) -> str:
        """Compute deterministic hash of bundle contents."""
        content = json.dumps({
            "version": self.version,
            "agent_id": self.agent_id,
            "agent_pubkey": self.agent_pubkey,
            "attestations": [asdict(a) for a in self.attestations],
            "revocations": [asdict(r) for r in self.revocations],
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def seal(self) -> "TrustBundle":
        """Compute and set bundle hash."""
        self.bundle_hash = self.compute_hash()
        return self

    def verify_integrity(self) -> bool:
        """Check that bundle hasn't been tampered with."""
        return self.bundle_hash == self.compute_hash()


def export_chain(
    trust_chain: TrustChain,
    agent_id: str,
    agent_pubkey: str = "",
    rev_reg: Optional[RevocationRegistry] = None,
    metadata: Optional[dict] = None,
) -> TrustBundle:
    """
    Export an agent's trust chain as a portable bundle.
    
    Args:
        trust_chain: The TrustChain containing attestations
        agent_id: Agent whose chain to export
        agent_pubkey: Agent's public key hex
        rev_reg: Optional revocation registry
        metadata: Optional metadata dict
        
    Returns:
        Sealed TrustBundle
    """
    attestations = []
    for att in trust_chain.attestations:
        if att.subject == agent_id:
            attestations.append(PortableAttestation.from_attestation(att))

    revocations = []
    # TODO: extract relevant revocations when rev_reg API is extended

    score = trust_chain.trust_score(agent_id)

    bundle = TrustBundle(
        agent_id=agent_id,
        agent_pubkey=agent_pubkey,
        exported_at=time.time(),
        attestations=attestations,
        revocations=revocations,
        trust_score=score,
        metadata=metadata or {},
    )
    return bundle.seal()


def bundle_to_json(bundle: TrustBundle) -> str:
    """Serialize bundle to JSON string."""
    return json.dumps(asdict(bundle), indent=2)


def bundle_from_json(data: str) -> TrustBundle:
    """Deserialize bundle from JSON string."""
    raw = json.loads(data)
    bundle = TrustBundle(
        version=raw["version"],
        agent_id=raw["agent_id"],
        agent_pubkey=raw.get("agent_pubkey", ""),
        exported_at=raw["exported_at"],
        attestations=[PortableAttestation(**a) for a in raw.get("attestations", [])],
        revocations=[PortableRevocation(**r) for r in raw.get("revocations", [])],
        trust_score=raw.get("trust_score"),
        metadata=raw.get("metadata", {}),
        bundle_hash=raw.get("bundle_hash", ""),
    )
    return bundle


def verify_bundle(bundle: TrustBundle) -> dict:
    """
    Verify a portable trust bundle.
    
    Returns dict with verification results.
    """
    revoked_ids = {r.target_id for r in bundle.revocations}
    effective = sum(
        1 for a in bundle.attestations
        if a.attestation_id not in revoked_ids
    )

    return {
        "integrity": bundle.verify_integrity(),
        "version_ok": bundle.version == IPTB_VERSION,
        "attestation_count": len(bundle.attestations),
        "revocation_count": len(bundle.revocations),
        "effective_attestations": effective,
        "trust_score": bundle.trust_score,
        "agent_id": bundle.agent_id,
    }
