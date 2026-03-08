"""
L3 Provenance — Full cryptographic chain linking intent → execution → verification.

A ProvenanceChain is a Merkle-like DAG of ProvenanceNodes.
Each node references its parent(s), creating an auditable trail:

  Intent(L0) → Endorsement(L1)* → Commit(L0.committed) → PostEndorsement(L1)*

The chain root hash is the trust anchor — if any node is tampered,
the root changes, making forgery detectable.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class ProvenanceNode(BaseModel):
    """
    Single node in a provenance chain.

    node_type:  "intent" | "endorsement" | "commit" | "rejection"
    ref_id:     The L0 intent_id or L1 endorsement_id this node wraps
    parent_ids: Hash(es) of parent node(s) — empty for root
    payload_hash: SHA-256 of the referenced object's canonical payload
    actor_id:   Agent who created this node
    node_hash:  Computed hash of this node (includes parent_ids + payload_hash)
    timestamp:  ISO 8601
    """
    node_type: str = Field(..., description="intent | endorsement | commit | rejection")
    ref_id: str = Field(..., description="Referenced L0/L1 object ID")
    parent_ids: List[str] = Field(default_factory=list)
    payload_hash: str = Field(..., description="SHA-256 of referenced object's canonical payload")
    actor_id: str = Field(...)
    node_hash: str = Field(default="")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def model_post_init(self, __context) -> None:
        if not self.node_hash:
            self.node_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        obj = {
            "node_type": self.node_type,
            "ref_id": self.ref_id,
            "parent_ids": sorted(self.parent_ids),
            "payload_hash": self.payload_hash,
            "actor_id": self.actor_id,
        }
        data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(data).hexdigest()


class ProvenanceChain(BaseModel):
    """
    L3 Provenance chain — ordered list of ProvenanceNodes forming a DAG.

    The chain tracks the full lifecycle of an intent:
    1. Intent declared (root node)
    2. Pre-endorsements (optional)
    3. Commit (agent marks intent fulfilled)
    4. Post-endorsements / rejections

    root_hash is recomputed as the Merkle root of all node hashes.
    """
    chain_id: str = Field(..., description="Usually matches the intent_id")
    nodes: List[ProvenanceNode] = Field(default_factory=list)
    root_hash: str = Field(default="")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def _compute_root(self) -> str:
        """Compute Merkle-style root hash from all node hashes."""
        if not self.nodes:
            return hashlib.sha256(b"empty").hexdigest()
        hashes = [n.node_hash for n in self.nodes]
        # Simple iterative hashing (not a full Merkle tree — sufficient for chains)
        combined = ":".join(sorted(hashes))
        return hashlib.sha256(combined.encode()).hexdigest()

    def add_node(self, node: ProvenanceNode) -> None:
        """Append a node and recompute root hash."""
        self.nodes.append(node)
        self.root_hash = self._compute_root()

    def verify_integrity(self) -> bool:
        """Check that all node hashes are valid and root matches."""
        for node in self.nodes:
            expected = node._compute_hash()
            if node.node_hash != expected:
                return False
        return self.root_hash == self._compute_root()

    @classmethod
    def from_intent(cls, intent) -> "ProvenanceChain":
        """Bootstrap a chain from an L0 Intent."""
        payload_hash = hashlib.sha256(intent.canonical_payload()).hexdigest()
        root_node = ProvenanceNode(
            node_type="intent",
            ref_id=intent.intent_id,
            parent_ids=[],
            payload_hash=payload_hash,
            actor_id=intent.agent_id,
        )
        chain = cls(chain_id=intent.intent_id)
        chain.add_node(root_node)
        return chain

    def add_endorsement(self, endorsement) -> None:
        """Add an L1 Endorsement as a node linked to the intent root."""
        payload_hash = hashlib.sha256(endorsement.canonical_payload()).hexdigest()
        parent = self.nodes[0].node_hash if self.nodes else ""
        node = ProvenanceNode(
            node_type="endorsement" if endorsement.endorsement_type.value != "rejection" else "rejection",
            ref_id=endorsement.endorsement_id,
            parent_ids=[parent] if parent else [],
            payload_hash=payload_hash,
            actor_id=endorsement.endorser_id,
        )
        self.add_node(node)

    def add_commit(self, intent, evidence_hash: str = "") -> None:
        """Record the commit event as a node."""
        commit_data = {
            "intent_id": intent.intent_id,
            "status": "committed",
            "evidence_hash": evidence_hash,
        }
        payload_hash = hashlib.sha256(
            json.dumps(commit_data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        parent_hashes = [n.node_hash for n in self.nodes]
        node = ProvenanceNode(
            node_type="commit",
            ref_id=f"{intent.intent_id}:commit",
            parent_ids=parent_hashes,
            payload_hash=payload_hash,
            actor_id=intent.agent_id,
        )
        self.add_node(node)

    def summary(self) -> dict:
        return {
            "chain_id": self.chain_id,
            "root_hash": self.root_hash,
            "node_count": len(self.nodes),
            "node_types": [n.node_type for n in self.nodes],
            "integrity": self.verify_integrity(),
        }
