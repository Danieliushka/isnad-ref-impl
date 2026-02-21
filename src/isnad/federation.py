"""
isnad.federation — Trust Federation Protocol

Enables agents across different networks to share and verify trust data.
Supports:
- Peer registration and discovery
- Trust chain forwarding (transitive trust across networks)
- Conflict resolution for contradicting attestations
- Selective sharing (privacy-preserving trust exchange)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FederationPolicy(Enum):
    """How much trust data to share with a peer network."""
    FULL = "full"           # Share all attestations
    SELECTIVE = "selective"  # Share only above threshold
    SUMMARY = "summary"     # Share aggregate scores only
    NONE = "none"           # No sharing


class ConflictStrategy(Enum):
    """How to resolve contradicting attestations from different peers."""
    LOCAL_PRIORITY = "local_priority"    # Local attestations win
    PEER_PRIORITY = "peer_priority"      # Peer attestations win  
    HIGHEST_TRUST = "highest_trust"      # Highest trust score wins
    MOST_RECENT = "most_recent"          # Most recent wins
    CONSENSUS = "consensus"              # Majority among peers wins


@dataclass
class FederationPeer:
    """A peer network in the federation."""
    peer_id: str
    name: str
    endpoint: Optional[str] = None
    policy: FederationPolicy = FederationPolicy.SELECTIVE
    trust_level: float = 0.5  # How much we trust this peer's attestations
    share_threshold: float = 0.3  # Min score to share (for SELECTIVE)
    registered_at: float = field(default_factory=time.time)
    last_sync: Optional[float] = None
    attestations_received: int = 0
    attestations_sent: int = 0
    active: bool = True


@dataclass
class FederatedAttestation:
    """An attestation received from a federated peer."""
    original_issuer: str
    subject: str
    claim: str
    value: Any
    trust_score: float
    peer_id: str  # Which peer forwarded this
    original_timestamp: float
    received_at: float = field(default_factory=time.time)
    chain_length: int = 1  # How many hops from original issuer
    signature_hash: Optional[str] = None


class FederationHub:
    """
    Manages trust federation between agent networks.
    
    Each hub represents one network's view of the federation.
    Peers exchange trust data according to their policies.
    """

    def __init__(
        self,
        network_id: str,
        conflict_strategy: ConflictStrategy = ConflictStrategy.LOCAL_PRIORITY,
        max_chain_length: int = 3,
        trust_decay_per_hop: float = 0.15,
    ):
        self.network_id = network_id
        self.conflict_strategy = conflict_strategy
        self.max_chain_length = max_chain_length
        self.trust_decay_per_hop = trust_decay_per_hop
        
        self._peers: dict[str, FederationPeer] = {}
        self._received: list[FederatedAttestation] = []
        self._local_attestations: list[dict] = []
        self._conflicts: list[dict] = []

    # ── Peer Management ──

    def register_peer(
        self,
        peer_id: str,
        name: str,
        endpoint: Optional[str] = None,
        policy: FederationPolicy = FederationPolicy.SELECTIVE,
        trust_level: float = 0.5,
        share_threshold: float = 0.3,
    ) -> FederationPeer:
        """Register a new peer network."""
        if peer_id == self.network_id:
            raise ValueError("Cannot register self as peer")
        if peer_id in self._peers:
            raise ValueError(f"Peer {peer_id} already registered")
        
        peer = FederationPeer(
            peer_id=peer_id,
            name=name,
            endpoint=endpoint,
            policy=policy,
            trust_level=trust_level,
            share_threshold=share_threshold,
        )
        self._peers[peer_id] = peer
        return peer

    def remove_peer(self, peer_id: str) -> bool:
        """Remove a peer from the federation."""
        if peer_id in self._peers:
            self._peers[peer_id].active = False
            return True
        return False

    def get_peer(self, peer_id: str) -> Optional[FederationPeer]:
        """Get a peer by ID."""
        return self._peers.get(peer_id)

    def list_peers(self, active_only: bool = True) -> list[FederationPeer]:
        """List all registered peers."""
        peers = list(self._peers.values())
        if active_only:
            peers = [p for p in peers if p.active]
        return peers

    def update_peer_trust(self, peer_id: str, new_trust: float) -> None:
        """Update trust level for a peer based on their behavior."""
        if peer_id not in self._peers:
            raise KeyError(f"Unknown peer: {peer_id}")
        self._peers[peer_id].trust_level = max(0.0, min(1.0, new_trust))

    # ── Attestation Exchange ──

    def add_local_attestation(
        self,
        issuer: str,
        subject: str,
        claim: str,
        value: Any,
        trust_score: float,
        timestamp: Optional[float] = None,
    ) -> dict:
        """Add a local attestation that can be shared with peers."""
        att = {
            "issuer": issuer,
            "subject": subject,
            "claim": claim,
            "value": value,
            "trust_score": trust_score,
            "timestamp": timestamp or time.time(),
            "network": self.network_id,
        }
        self._local_attestations.append(att)
        return att

    def receive_attestation(
        self,
        peer_id: str,
        original_issuer: str,
        subject: str,
        claim: str,
        value: Any,
        trust_score: float,
        original_timestamp: float,
        chain_length: int = 1,
        signature_hash: Optional[str] = None,
    ) -> Optional[FederatedAttestation]:
        """
        Receive an attestation from a federated peer.
        
        Returns None if rejected (unknown peer, chain too long, etc.)
        """
        peer = self._peers.get(peer_id)
        if not peer or not peer.active:
            return None
        
        if chain_length > self.max_chain_length:
            return None
        
        # Apply trust decay based on chain length
        decayed_score = trust_score * (1 - self.trust_decay_per_hop * chain_length)
        # Weight by peer trust level
        effective_score = decayed_score * peer.trust_level
        
        sig = signature_hash or hashlib.sha256(
            f"{original_issuer}:{subject}:{claim}:{value}:{original_timestamp}".encode()
        ).hexdigest()[:16]
        
        att = FederatedAttestation(
            original_issuer=original_issuer,
            subject=subject,
            claim=claim,
            value=value,
            trust_score=effective_score,
            peer_id=peer_id,
            original_timestamp=original_timestamp,
            chain_length=chain_length,
            signature_hash=sig,
        )
        
        # Check for conflicts
        conflict = self._check_conflict(att)
        if conflict:
            self._conflicts.append(conflict)
            resolved = self._resolve_conflict(conflict)
            if not resolved:
                return None
        
        self._received.append(att)
        peer.attestations_received += 1
        peer.last_sync = time.time()
        return att

    def get_attestations_to_share(self, peer_id: str) -> list[dict]:
        """
        Get local attestations that should be shared with a specific peer,
        according to that peer's sharing policy.
        """
        peer = self._peers.get(peer_id)
        if not peer or not peer.active:
            return []
        
        if peer.policy == FederationPolicy.NONE:
            return []
        
        if peer.policy == FederationPolicy.FULL:
            result = list(self._local_attestations)
        elif peer.policy == FederationPolicy.SELECTIVE:
            result = [
                a for a in self._local_attestations
                if a["trust_score"] >= peer.share_threshold
            ]
        elif peer.policy == FederationPolicy.SUMMARY:
            # Aggregate by subject
            subjects: dict[str, list[float]] = {}
            for a in self._local_attestations:
                subjects.setdefault(a["subject"], []).append(a["trust_score"])
            result = [
                {
                    "subject": subj,
                    "aggregate_score": sum(scores) / len(scores),
                    "attestation_count": len(scores),
                    "network": self.network_id,
                }
                for subj, scores in subjects.items()
            ]
        else:
            result = []
        
        peer.attestations_sent += len(result)
        return result

    # ── Trust Queries ──

    def get_federated_trust(self, subject: str) -> dict:
        """
        Get aggregated trust data for a subject across all federated sources.
        
        Returns local + federated scores with provenance.
        """
        local_scores = [
            a["trust_score"]
            for a in self._local_attestations
            if a["subject"] == subject
        ]
        
        federated_scores = {}
        for att in self._received:
            if att.subject == subject:
                federated_scores.setdefault(att.peer_id, []).append(att.trust_score)
        
        # Compute aggregates
        local_avg = sum(local_scores) / len(local_scores) if local_scores else None
        peer_avgs = {
            pid: sum(scores) / len(scores)
            for pid, scores in federated_scores.items()
        }
        
        all_scores = local_scores + [
            s for scores in federated_scores.values() for s in scores
        ]
        global_avg = sum(all_scores) / len(all_scores) if all_scores else None
        
        return {
            "subject": subject,
            "local_score": local_avg,
            "local_attestations": len(local_scores),
            "peer_scores": peer_avgs,
            "federated_attestations": sum(len(s) for s in federated_scores.values()),
            "global_score": global_avg,
            "total_attestations": len(all_scores),
        }

    def get_network_health(self) -> dict:
        """Get federation network health metrics."""
        active_peers = [p for p in self._peers.values() if p.active]
        return {
            "network_id": self.network_id,
            "total_peers": len(self._peers),
            "active_peers": len(active_peers),
            "local_attestations": len(self._local_attestations),
            "received_attestations": len(self._received),
            "unresolved_conflicts": len([
                c for c in self._conflicts if not c.get("resolved")
            ]),
            "avg_peer_trust": (
                sum(p.trust_level for p in active_peers) / len(active_peers)
                if active_peers else 0
            ),
        }

    # ── Conflict Resolution ──

    def _check_conflict(self, new_att: FederatedAttestation) -> Optional[dict]:
        """Check if new attestation conflicts with existing data."""
        for existing in self._received:
            if (
                existing.subject == new_att.subject
                and existing.claim == new_att.claim
                and existing.value != new_att.value
            ):
                return {
                    "existing": existing,
                    "incoming": new_att,
                    "resolved": False,
                }
        
        for local in self._local_attestations:
            if (
                local["subject"] == new_att.subject
                and local["claim"] == new_att.claim
                and local["value"] != new_att.value
            ):
                return {
                    "existing_local": local,
                    "incoming": new_att,
                    "resolved": False,
                }
        
        return None

    def _resolve_conflict(self, conflict: dict) -> bool:
        """
        Resolve a conflict. Returns True if incoming attestation should be accepted.
        """
        incoming = conflict["incoming"]
        
        if self.conflict_strategy == ConflictStrategy.LOCAL_PRIORITY:
            if "existing_local" in conflict:
                conflict["resolved"] = True
                conflict["winner"] = "local"
                return False  # Reject incoming
            conflict["resolved"] = True
            conflict["winner"] = "incoming"
            return True
        
        elif self.conflict_strategy == ConflictStrategy.MOST_RECENT:
            existing = conflict.get("existing") or conflict.get("existing_local")
            existing_ts = (
                existing.original_timestamp
                if isinstance(existing, FederatedAttestation)
                else existing.get("timestamp", 0)
            )
            conflict["resolved"] = True
            if incoming.original_timestamp > existing_ts:
                conflict["winner"] = "incoming"
                return True
            conflict["winner"] = "existing"
            return False
        
        elif self.conflict_strategy == ConflictStrategy.HIGHEST_TRUST:
            existing = conflict.get("existing") or conflict.get("existing_local")
            existing_score = (
                existing.trust_score
                if isinstance(existing, FederatedAttestation)
                else existing.get("trust_score", 0)
            )
            conflict["resolved"] = True
            if incoming.trust_score > existing_score:
                conflict["winner"] = "incoming"
                return True
            conflict["winner"] = "existing"
            return False
        
        elif self.conflict_strategy == ConflictStrategy.CONSENSUS:
            # Count attestations for each value across all peers
            subject, claim = incoming.subject, incoming.claim
            value_counts: dict[Any, int] = {}
            for att in self._received:
                if att.subject == subject and att.claim == claim:
                    value_counts[att.value] = value_counts.get(att.value, 0) + 1
            value_counts[incoming.value] = value_counts.get(incoming.value, 0) + 1
            
            conflict["resolved"] = True
            max_value = max(value_counts, key=value_counts.get)  # type: ignore
            if max_value == incoming.value:
                conflict["winner"] = "incoming"
                return True
            conflict["winner"] = "existing"
            return False
        
        # PEER_PRIORITY: always accept incoming
        conflict["resolved"] = True
        conflict["winner"] = "incoming"
        return True

    def get_conflicts(self, unresolved_only: bool = False) -> list[dict]:
        """Get conflict log."""
        if unresolved_only:
            return [c for c in self._conflicts if not c.get("resolved")]
        return list(self._conflicts)
