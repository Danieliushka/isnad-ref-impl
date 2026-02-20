#!/usr/bin/env python3
"""
isnad — Reference implementation of Isnad Chains for Agent Reputation
Based on RFC: github.com/KitTheFox123/isnad-rfc

Core module: keypairs, attestations, chain validation.
"""

import json
import time
import hashlib
import os
from datetime import datetime, timezone
from typing import Optional

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError


# ─── Identity ──────────────────────────────────────────────────────

class AgentIdentity:
    """Ed25519 keypair for an agent."""
    
    def __init__(self, signing_key: Optional[SigningKey] = None):
        self.signing_key = signing_key or SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
    
    @property
    def agent_id(self) -> str:
        """Derive agent ID from public key hash."""
        pubkey_hex = self.verify_key.encode(encoder=HexEncoder).decode()
        return f"agent:{hashlib.sha256(pubkey_hex.encode()).hexdigest()[:16]}"
    
    @property
    def public_key_hex(self) -> str:
        return self.verify_key.encode(encoder=HexEncoder).decode()
    
    def sign(self, data: bytes) -> bytes:
        """Sign data with private key."""
        return self.signing_key.sign(data).signature
    
    def export_keys(self) -> dict:
        """Export keypair for storage."""
        return {
            "agent_id": self.agent_id,
            "public_key": self.public_key_hex,
            "private_key": self.signing_key.encode(encoder=HexEncoder).decode(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    @classmethod
    def from_private_key(cls, hex_key: str) -> "AgentIdentity":
        """Load from private key hex string."""
        sk = SigningKey(hex_key.encode(), encoder=HexEncoder)
        return cls(signing_key=sk)
    
    @classmethod
    def load(cls, filepath: str) -> "AgentIdentity":
        """Load identity from JSON file."""
        with open(filepath) as f:
            data = json.load(f)
        return cls.from_private_key(data["private_key"])
    
    def save(self, filepath: str):
        """Save identity to JSON file."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(self.export_keys(), f, indent=2)
        os.chmod(filepath, 0o600)

    def rotate(self) -> tuple["AgentIdentity", "KeyRotation"]:
        """Generate new keypair and a signed rotation proof linking old → new.

        Returns (new_identity, rotation_record).
        The rotation is signed by the OLD key to prove continuity.
        """
        new_identity = AgentIdentity()
        rotation = KeyRotation.create(old_identity=self, new_identity=new_identity)
        return new_identity, rotation


class KeyRotation:
    """Signed proof that an agent rotated from one key to another.

    The old key signs a message binding (old_pubkey, new_pubkey, timestamp),
    proving the holder of the old key authorised the transition.
    Enterprise compliance requires periodic key rotation; this record
    preserves chain-of-custody across rotations.
    """

    def __init__(self, old_pubkey: str, new_pubkey: str,
                 timestamp: str, signature: str,
                 old_agent_id: str = "", new_agent_id: str = ""):
        self.old_pubkey = old_pubkey
        self.new_pubkey = new_pubkey
        self.timestamp = timestamp
        self.signature = signature
        self.old_agent_id = old_agent_id
        self.new_agent_id = new_agent_id

    # ── factory ──

    @classmethod
    def create(cls, old_identity: AgentIdentity,
               new_identity: AgentIdentity) -> "KeyRotation":
        ts = datetime.now(timezone.utc).isoformat()
        payload = cls._payload(old_identity.public_key_hex,
                               new_identity.public_key_hex, ts)
        sig = old_identity.sign(payload)
        return cls(
            old_pubkey=old_identity.public_key_hex,
            new_pubkey=new_identity.public_key_hex,
            timestamp=ts,
            signature=sig.hex(),
            old_agent_id=old_identity.agent_id,
            new_agent_id=new_identity.agent_id,
        )

    # ── verification ──

    def verify(self) -> bool:
        """Verify the rotation was signed by the old key."""
        try:
            vk = VerifyKey(bytes.fromhex(self.old_pubkey))
            payload = self._payload(self.old_pubkey, self.new_pubkey,
                                    self.timestamp)
            vk.verify(payload, bytes.fromhex(self.signature))
            return True
        except (BadSignatureError, Exception):
            return False

    # ── serialisation ──

    def to_dict(self) -> dict:
        return {
            "type": "key_rotation",
            "old_pubkey": self.old_pubkey,
            "new_pubkey": self.new_pubkey,
            "old_agent_id": self.old_agent_id,
            "new_agent_id": self.new_agent_id,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KeyRotation":
        return cls(
            old_pubkey=d["old_pubkey"],
            new_pubkey=d["new_pubkey"],
            timestamp=d["timestamp"],
            signature=d["signature"],
            old_agent_id=d.get("old_agent_id", ""),
            new_agent_id=d.get("new_agent_id", ""),
        )

    # ── internal ──

    @staticmethod
    def _payload(old_pk: str, new_pk: str, ts: str) -> bytes:
        return json.dumps({
            "action": "key_rotation",
            "old_pubkey": old_pk,
            "new_pubkey": new_pk,
            "timestamp": ts,
        }, sort_keys=True, separators=(",", ":")).encode()


# ─── Attestation ───────────────────────────────────────────────────

class Attestation:
    """A signed claim: 'Agent A completed task X at time T, witnessed by B'."""
    
    def __init__(self, subject: str, witness: str, task: str,
                 evidence: str = "", timestamp: Optional[str] = None,
                 signature: Optional[str] = None, witness_pubkey: Optional[str] = None):
        self.subject = subject        # Who did the work
        self.witness = witness         # Who observed/verified
        self.task = task               # What was completed
        self.evidence = evidence       # URI to artifact/proof
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.signature = signature     # Witness's signature (hex)
        self.witness_pubkey = witness_pubkey  # Witness's public key (hex)
    
    @property
    def claim_data(self) -> bytes:
        """Canonical bytes for signing (deterministic)."""
        claim = {
            "subject": self.subject,
            "witness": self.witness,
            "task": self.task,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }
        return json.dumps(claim, sort_keys=True, separators=(",", ":")).encode()
    
    @property
    def attestation_id(self) -> str:
        """Unique ID derived from claim content."""
        return hashlib.sha256(self.claim_data).hexdigest()[:16]
    
    def sign(self, witness_identity: AgentIdentity) -> "Attestation":
        """Sign this attestation as the witness."""
        assert witness_identity.agent_id == self.witness, \
            f"Signer {witness_identity.agent_id} != witness {self.witness}"
        self.signature = witness_identity.sign(self.claim_data).hex()
        self.witness_pubkey = witness_identity.public_key_hex
        return self
    
    def verify(self) -> bool:
        """Verify the witness's signature."""
        if not self.signature or not self.witness_pubkey:
            return False
        try:
            vk = VerifyKey(self.witness_pubkey.encode(), encoder=HexEncoder)
            vk.verify(self.claim_data, bytes.fromhex(self.signature))
            return True
        except (BadSignatureError, Exception):
            return False
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "attestation_id": self.attestation_id,
            "subject": self.subject,
            "witness": self.witness,
            "task": self.task,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "witness_pubkey": self.witness_pubkey,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Attestation":
        """Deserialize from dict."""
        return cls(
            subject=data["subject"],
            witness=data["witness"],
            task=data["task"],
            evidence=data.get("evidence", ""),
            timestamp=data.get("timestamp"),
            signature=data.get("signature"),
            witness_pubkey=data.get("witness_pubkey"),
        )
    
    def __repr__(self):
        status = "✅" if self.verify() else "❌"
        return f"Attestation({status} {self.witness} → {self.subject}: {self.task})"


# ─── Trust Chain ───────────────────────────────────────────────────

class TrustChain:
    """Collection of attestations with trust computation."""
    
    # Decay constants (from RFC)
    CHAIN_DECAY = 0.7       # Trust reduces by 30% per hop
    SAME_WITNESS_DECAY = 0.5  # 50% penalty for repeated same witness
    
    def __init__(self, revocation_registry: Optional["RevocationRegistry"] = None):
        self.attestations: list[Attestation] = []
        self._by_subject: dict[str, list[Attestation]] = {}
        self._by_witness: dict[str, list[Attestation]] = {}
        self.revocations = revocation_registry
    
    def add(self, attestation: Attestation) -> bool:
        """Add attestation if valid and not revoked. Returns True if added."""
        if not attestation.verify():
            return False
        if self.revocations and self.revocations.is_revoked(attestation.attestation_id):
            return False
        self.attestations.append(attestation)
        self._by_subject.setdefault(attestation.subject, []).append(attestation)
        self._by_witness.setdefault(attestation.witness, []).append(attestation)
        return True
    
    def trust_score(self, agent_id: str, scope: Optional[str] = None) -> float:
        """
        Compute trust score for an agent (0.0 to 1.0).
        
        Score = sum of attestation weights, capped at 1.0
        Each attestation: base_weight * chain_decay^hops * same_witness_penalty
        Revoked agents always return 0.0.
        """
        # Revoked agents get zero trust
        if self.revocations and self.revocations.is_revoked(agent_id, scope=scope):
            return 0.0

        attestations = self._by_subject.get(agent_id, [])
        if not attestations:
            return 0.0
        
        # Filter by scope (task type) if specified
        if scope:
            attestations = [a for a in attestations if scope.lower() in a.task.lower()]
        
        score = 0.0
        witness_counts: dict[str, int] = {}
        
        for att in attestations:
            # Base weight per attestation
            base_weight = 0.2
            
            # Same-witness decay
            witness_counts[att.witness] = witness_counts.get(att.witness, 0) + 1
            count = witness_counts[att.witness]
            witness_penalty = self.SAME_WITNESS_DECAY ** (count - 1)
            
            score += base_weight * witness_penalty
        
        return min(score, 1.0)
    
    def chain_trust(self, source: str, target: str, max_hops: int = 5) -> float:
        """
        Compute transitive trust from source to target through attestation chains.
        Uses BFS with decay per hop.
        """
        if source == target:
            return 1.0
        
        # BFS
        visited = {source}
        queue = [(source, 1.0, 0)]  # (agent, trust, hops)
        best_trust = 0.0
        
        while queue:
            current, trust, hops = queue.pop(0)
            if hops >= max_hops:
                continue
            
            # Find agents attested by current
            for att in self._by_witness.get(current, []):
                next_agent = att.subject
                next_trust = trust * self.CHAIN_DECAY
                
                if next_agent == target:
                    best_trust = max(best_trust, next_trust)
                elif next_agent not in visited:
                    visited.add(next_agent)
                    queue.append((next_agent, next_trust, hops + 1))
        
        return best_trust
    
    def save(self, filepath: str):
        """Save chain to JSON file."""
        data = [a.to_dict() for a in self.attestations]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> "TrustChain":
        """Load chain from JSON file."""
        chain = cls()
        with open(filepath) as f:
            data = json.load(f)
        for item in data:
            att = Attestation.from_dict(item)
            chain.attestations.append(att)
            chain._by_subject.setdefault(att.subject, []).append(att)
            chain._by_witness.setdefault(att.witness, []).append(att)
        return chain

    def export_bundle(self, signer: Optional["AgentIdentity"] = None,
                      metadata: Optional[dict] = None) -> dict:
        """
        Export chain as a portable signed bundle for cross-system sharing.
        
        Bundle format (isnad-bundle/v1):
        {
            "version": "isnad-bundle/v1",
            "created_at": ISO timestamp,
            "metadata": { ... },
            "attestations": [ ... ],
            "stats": { subjects, witnesses, count },
            "signature": hex (optional, if signer provided)
        }
        """
        attestation_data = [a.to_dict() for a in self.attestations]
        
        bundle = {
            "version": "isnad-bundle/v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "attestations": attestation_data,
            "stats": {
                "count": len(self.attestations),
                "subjects": len(self._by_subject),
                "witnesses": len(self._by_witness),
            },
        }
        
        if signer:
            # Sign the canonical JSON of attestations + metadata
            payload = json.dumps(
                {"attestations": attestation_data, "metadata": bundle["metadata"]},
                sort_keys=True, separators=(",", ":")
            ).encode()
            bundle["signed_by"] = signer.agent_id
            bundle["signer_pubkey"] = signer.public_key_hex
            bundle["signature"] = signer.sign(payload).hex()
        
        return bundle

    @classmethod
    def from_bundle(cls, bundle: dict,
                    verify_signature: bool = True) -> "TrustChain":
        """
        Import chain from a portable bundle.
        
        Validates bundle version and optionally verifies signature.
        Raises ValueError on invalid/tampered bundles.
        """
        version = bundle.get("version", "")
        if version != "isnad-bundle/v1":
            raise ValueError(f"Unsupported bundle version: {version}")
        
        # Verify signature if present and requested
        if verify_signature and "signature" in bundle:
            pubkey_hex = bundle.get("signer_pubkey")
            if not pubkey_hex:
                raise ValueError("Bundle signed but missing signer_pubkey")
            
            verify_key = VerifyKey(pubkey_hex.encode(), encoder=HexEncoder)
            payload = json.dumps(
                {"attestations": bundle["attestations"],
                 "metadata": bundle.get("metadata", {})},
                sort_keys=True, separators=(",", ":")
            ).encode()
            signature = bytes.fromhex(bundle["signature"])
            
            try:
                verify_key.verify(payload, signature)
            except BadSignatureError:
                raise ValueError("Bundle signature verification failed — data may be tampered")
        
        chain = cls()
        for item in bundle.get("attestations", []):
            att = Attestation.from_dict(item)
            if att.verify():
                chain.attestations.append(att)
                chain._by_subject.setdefault(att.subject, []).append(att)
                chain._by_witness.setdefault(att.witness, []).append(att)
        
        return chain


# ─── Revocation Registry ──────────────────────────────────────────

class RevocationEntry:
    """A signed revocation of an agent or attestation."""

    def __init__(self, target_id: str, reason: str, revoked_by: str,
                 scope: Optional[str] = None, timestamp: Optional[float] = None,
                 signature: Optional[str] = None):
        self.target_id = target_id  # agent_id or attestation_id
        self.reason = reason
        self.revoked_by = revoked_by
        self.scope = scope  # None = revoke all scopes
        self.timestamp = timestamp or time.time()
        self.signature = signature

    def payload(self) -> bytes:
        data = {
            "action": "revoke",
            "target_id": self.target_id,
            "reason": self.reason,
            "revoked_by": self.revoked_by,
            "scope": self.scope,
            "timestamp": self.timestamp,
        }
        return json.dumps(data, sort_keys=True).encode()

    def sign(self, identity: AgentIdentity) -> "RevocationEntry":
        sig = identity.sign(self.payload())
        self.signature = sig.hex()
        return self

    def verify(self, public_key_hex: str) -> bool:
        if not self.signature:
            return False
        try:
            vk = VerifyKey(bytes.fromhex(public_key_hex))
            vk.verify(self.payload(), bytes.fromhex(self.signature))
            return True
        except (BadSignatureError, Exception):
            return False

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "reason": self.reason,
            "revoked_by": self.revoked_by,
            "scope": self.scope,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RevocationEntry":
        return cls(
            target_id=data["target_id"],
            reason=data["reason"],
            revoked_by=data["revoked_by"],
            scope=data.get("scope"),
            timestamp=data.get("timestamp", time.time()),
            signature=data.get("signature"),
        )


# ─── Delegation ────────────────────────────────────────────────────

class Delegation:
    """A signed delegation token: principal grants scoped authority to delegate.

    Supports:
    - Time-bounded access (expires_at)
    - Scope constraints (list of allowed task types)
    - Sub-delegation depth limits (max_depth)
    - Chained delegations (parent_id links to granting delegation)

    NIST Focus Area: "Facilitating access delegation and ensuring auditability"
    """

    def __init__(self, principal: str, delegate: str, scopes: list[str],
                 expires_at: Optional[float] = None, max_depth: int = 0,
                 parent_id: Optional[str] = None, depth: int = 0,
                 timestamp: Optional[float] = None,
                 signature: Optional[str] = None,
                 principal_pubkey: Optional[str] = None):
        self.principal = principal        # Who grants authority
        self.delegate = delegate          # Who receives authority
        self.scopes = sorted(scopes)      # Allowed task types
        self.expires_at = expires_at      # Unix timestamp, None = no expiry
        self.max_depth = max_depth        # How many sub-delegations allowed (0 = none)
        self.parent_id = parent_id        # If sub-delegated, links to parent
        self.depth = depth                # Current depth in delegation chain
        self.timestamp = timestamp or time.time()
        self.signature = signature
        self.principal_pubkey = principal_pubkey

    @property
    def delegation_id(self) -> str:
        return hashlib.sha256(self.payload()).hexdigest()[:16]

    def payload(self) -> bytes:
        data = {
            "action": "delegate",
            "principal": self.principal,
            "delegate": self.delegate,
            "scopes": self.scopes,
            "expires_at": self.expires_at,
            "max_depth": self.max_depth,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "timestamp": self.timestamp,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, identity: AgentIdentity) -> "Delegation":
        assert identity.agent_id == self.principal, \
            f"Signer {identity.agent_id} != principal {self.principal}"
        self.signature = identity.sign(self.payload()).hex()
        self.principal_pubkey = identity.public_key_hex
        return self

    def verify(self) -> bool:
        if not self.signature or not self.principal_pubkey:
            return False
        try:
            vk = VerifyKey(bytes.fromhex(self.principal_pubkey))
            vk.verify(self.payload(), bytes.fromhex(self.signature))
            return True
        except (BadSignatureError, Exception):
            return False

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) > self.expires_at

    def can_sub_delegate(self) -> bool:
        return self.depth < self.max_depth

    def sub_delegate(self, new_delegate: str, scopes: list[str],
                     signer: AgentIdentity, expires_at: Optional[float] = None,
                     max_depth: Optional[int] = None) -> "Delegation":
        """Create a sub-delegation from this delegation.

        Constraints enforced:
        - Cannot exceed parent max_depth
        - Scopes must be subset of parent scopes
        - Expiry cannot exceed parent expiry
        - Signer must be the delegate of this delegation
        """
        if not self.can_sub_delegate():
            raise ValueError("Delegation depth limit reached")
        if signer.agent_id != self.delegate:
            raise ValueError(f"Only delegate {self.delegate} can sub-delegate")

        # Scopes must be subset
        invalid = set(scopes) - set(self.scopes)
        if invalid:
            raise ValueError(f"Scopes {invalid} not in parent delegation")

        # Expiry cannot exceed parent
        if self.expires_at is not None:
            if expires_at is None or expires_at > self.expires_at:
                expires_at = self.expires_at

        # Sub-delegation depth
        child_max = min(max_depth if max_depth is not None else self.max_depth - 1,
                        self.max_depth - self.depth - 1)

        child = Delegation(
            principal=self.delegate,
            delegate=new_delegate,
            scopes=scopes,
            expires_at=expires_at,
            max_depth=child_max,
            parent_id=self.delegation_id,
            depth=self.depth + 1,
            )
        return child.sign(signer)

    def to_dict(self) -> dict:
        return {
            "delegation_id": self.delegation_id,
            "principal": self.principal,
            "delegate": self.delegate,
            "scopes": self.scopes,
            "expires_at": self.expires_at,
            "max_depth": self.max_depth,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "principal_pubkey": self.principal_pubkey,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Delegation":
        return cls(
            principal=data["principal"],
            delegate=data["delegate"],
            scopes=data["scopes"],
            expires_at=data.get("expires_at"),
            max_depth=data.get("max_depth", 0),
            parent_id=data.get("parent_id"),
            depth=data.get("depth", 0),
            timestamp=data.get("timestamp"),
            signature=data.get("signature"),
            principal_pubkey=data.get("principal_pubkey"),
        )

    def __repr__(self):
        status = "✅" if self.verify() else "❌"
        exp = f" exp:{self.expires_at}" if self.expires_at else ""
        return f"Delegation({status} {self.principal} → {self.delegate} [{','.join(self.scopes)}]{exp})"


class DelegationRegistry:
    """Manages delegation chains with validation.

    Verifies full chain integrity: every delegation in the chain must be
    valid, not expired, and scopes must narrow (never widen).
    """

    def __init__(self, revocation_registry: Optional["RevocationRegistry"] = None):
        self._delegations: dict[str, Delegation] = {}  # id → delegation
        self._by_delegate: dict[str, list[Delegation]] = {}
        self._by_principal: dict[str, list[Delegation]] = {}
        self.revocations = revocation_registry

    def add(self, delegation: Delegation) -> bool:
        """Add delegation if valid signature. Returns True if added."""
        if not delegation.verify():
            return False
        if self.revocations and self.revocations.is_revoked(delegation.delegation_id):
            return False
        self._delegations[delegation.delegation_id] = delegation
        self._by_delegate.setdefault(delegation.delegate, []).append(delegation)
        self._by_principal.setdefault(delegation.principal, []).append(delegation)
        return True

    def get(self, delegation_id: str) -> Optional[Delegation]:
        return self._delegations.get(delegation_id)

    def delegations_for(self, agent_id: str) -> list[Delegation]:
        """All active (non-expired, non-revoked) delegations for an agent."""
        now = time.time()
        result = []
        for d in self._by_delegate.get(agent_id, []):
            if d.is_expired(now):
                continue
            if self.revocations and self.revocations.is_revoked(d.delegation_id):
                continue
            result.append(d)
        return result

    def is_authorized(self, agent_id: str, scope: str, now: Optional[float] = None) -> bool:
        """Check if agent has active delegation for a given scope."""
        now = now or time.time()
        for d in self._by_delegate.get(agent_id, []):
            if d.is_expired(now):
                continue
            if self.revocations and self.revocations.is_revoked(d.delegation_id):
                continue
            if scope in d.scopes:
                return True
        return False

    def verify_chain(self, delegation_id: str, now: Optional[float] = None) -> tuple[bool, str]:
        """Verify full delegation chain from leaf to root.

        Returns (valid, reason).
        """
        now = now or time.time()
        visited = set()
        current_id = delegation_id

        while current_id:
            if current_id in visited:
                return False, "Circular delegation chain"
            visited.add(current_id)

            d = self._delegations.get(current_id)
            if d is None:
                return False, f"Missing delegation {current_id}"
            if not d.verify():
                return False, f"Invalid signature on {current_id}"
            if d.is_expired(now):
                return False, f"Expired delegation {current_id}"
            if self.revocations and self.revocations.is_revoked(current_id):
                return False, f"Revoked delegation {current_id}"

            current_id = d.parent_id

        return True, "Chain valid"

    def save(self, filepath: str):
        data = [d.to_dict() for d in self._delegations.values()]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "DelegationRegistry":
        registry = cls()
        with open(filepath) as f:
            data = json.load(f)
        for item in data:
            d = Delegation.from_dict(item)
            registry._delegations[d.delegation_id] = d
            registry._by_delegate.setdefault(d.delegate, []).append(d)
            registry._by_principal.setdefault(d.principal, []).append(d)
        return registry


class RevocationRegistry:
    """Registry for revoked agents and attestations.

    Enterprise use case: instantly invalidate compromised agent credentials
    or fraudulent attestations across the trust network.
    """

    def __init__(self):
        self._revoked: dict[str, list[RevocationEntry]] = {}

    def revoke(self, entry: RevocationEntry) -> None:
        """Add a signed revocation entry."""
        self._revoked.setdefault(entry.target_id, []).append(entry)

    def is_revoked(self, target_id: str, scope: Optional[str] = None) -> bool:
        """Check if a target (agent or attestation) is revoked."""
        entries = self._revoked.get(target_id, [])
        for e in entries:
            if e.scope is None:  # global revocation
                return True
            if scope and e.scope == scope:
                return True
        return False

    def get_revocations(self, target_id: str) -> list[RevocationEntry]:
        """Get all revocation entries for a target."""
        return self._revoked.get(target_id, [])

    @property
    def all_entries(self) -> list[RevocationEntry]:
        """All revocation entries in the registry."""
        return [e for entries in self._revoked.values() for e in entries]

    def save(self, filepath: str):
        data = [e.to_dict() for e in self.all_entries]
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "RevocationRegistry":
        registry = cls()
        with open(filepath) as f:
            data = json.load(f)
        for item in data:
            registry.revoke(RevocationEntry.from_dict(item))
        return registry


# ─── CLI ───────────────────────────────────────────────────────────

def cli():
    """Command-line interface."""
    import sys
    
    if len(sys.argv) < 2:
        print("isnad — Attestation chains for agent reputation")
        print()
        print("Commands:")
        print("  init [keyfile]          Generate new agent identity")
        print("  show [keyfile]          Show agent ID and public key")
        print("  attest <subject> <task> <evidence> [keyfile]  Create attestation")
        print("  verify <attestation.json>    Verify attestation signature")
        print("  trust <chain.json> <agent-id> [scope]  Compute trust score")
        print("  demo                    Run interactive demo")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        keyfile = sys.argv[2] if len(sys.argv) > 2 else "identity.json"
        identity = AgentIdentity()
        identity.save(keyfile)
        print(f"✅ Generated identity: {identity.agent_id}")
        print(f"   Public key: {identity.public_key_hex[:16]}...")
        print(f"   Saved to: {keyfile}")
    
    elif cmd == "show":
        keyfile = sys.argv[2] if len(sys.argv) > 2 else "identity.json"
        identity = AgentIdentity.load(keyfile)
        print(f"Agent ID:    {identity.agent_id}")
        print(f"Public key:  {identity.public_key_hex}")
    
    elif cmd == "attest":
        if len(sys.argv) < 5:
            print("Usage: isnad attest <subject-id> <task> <evidence-uri> [keyfile]")
            return
        subject = sys.argv[2]
        task = sys.argv[3]
        evidence = sys.argv[4]
        keyfile = sys.argv[5] if len(sys.argv) > 5 else "identity.json"
        
        witness = AgentIdentity.load(keyfile)
        att = Attestation(subject=subject, witness=witness.agent_id, task=task, evidence=evidence)
        att.sign(witness)
        
        outfile = f"attestation-{att.attestation_id}.json"
        with open(outfile, "w") as f:
            json.dump(att.to_dict(), f, indent=2)
        
        print(f"✅ Attestation created: {att.attestation_id}")
        print(f"   {witness.agent_id} attests {subject}: {task}")
        print(f"   Saved to: {outfile}")
    
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("Usage: isnad verify <attestation.json>")
            return
        with open(sys.argv[2]) as f:
            data = json.load(f)
        att = Attestation.from_dict(data)
        if att.verify():
            print(f"✅ Valid: {att.witness} → {att.subject}: {att.task}")
        else:
            print(f"❌ INVALID signature!")
    
    elif cmd == "trust":
        if len(sys.argv) < 4:
            print("Usage: isnad trust <chain.json> <agent-id> [scope]")
            return
        chain = TrustChain.load(sys.argv[2])
        agent_id = sys.argv[3]
        scope = sys.argv[4] if len(sys.argv) > 4 else None
        score = chain.trust_score(agent_id, scope=scope)
        print(f"Trust score for {agent_id}: {score:.3f}")
        atts = chain._by_subject.get(agent_id, [])
        print(f"  Based on {len(atts)} attestation(s)")
    
    elif cmd == "demo":
        demo()
    
    else:
        print(f"Unknown command: {cmd}")


def demo():
    """Interactive demo of the attestation system."""
    print("=" * 60)
    print("isnad — Attestation Chain Demo")
    print("=" * 60)
    print()
    
    # Create three agents
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()
    
    print(f"👤 Alice:   {alice.agent_id}")
    print(f"👤 Bob:     {bob.agent_id}")
    print(f"👤 Charlie: {charlie.agent_id}")
    print()
    
    # Alice attests Bob completed a code review
    att1 = Attestation(
        subject=bob.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://github.com/example/pr/42"
    ).sign(alice)
    
    print(f"📜 {att1}")
    
    # Bob attests Charlie completed data analysis
    att2 = Attestation(
        subject=charlie.agent_id,
        witness=bob.agent_id,
        task="data-analysis",
        evidence="https://example.com/report.pdf"
    ).sign(bob)
    
    print(f"📜 {att2}")
    
    # Alice also attests Charlie (direct)
    att3 = Attestation(
        subject=charlie.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://github.com/example/pr/99"
    ).sign(alice)
    
    print(f"📜 {att3}")
    print()
    
    # Build trust chain
    chain = TrustChain()
    for att in [att1, att2, att3]:
        added = chain.add(att)
        print(f"Chain add {att.attestation_id[:8]}: {'✅' if added else '❌'}")
    
    print()
    
    # Compute trust scores
    print("📊 Trust Scores:")
    print(f"  Bob (direct):     {chain.trust_score(bob.agent_id):.3f}")
    print(f"  Charlie (direct): {chain.trust_score(charlie.agent_id):.3f}")
    print()
    
    # Transitive trust
    print("🔗 Transitive Trust (Alice → ?):")
    print(f"  Alice → Bob:     {chain.chain_trust(alice.agent_id, bob.agent_id):.3f}")
    print(f"  Alice → Charlie: {chain.chain_trust(alice.agent_id, charlie.agent_id):.3f}")
    print()
    
    # Verify all attestations
    print("🔍 Verification:")
    for att in chain.attestations:
        status = "✅ VALID" if att.verify() else "❌ INVALID"
        print(f"  {att.attestation_id[:8]}: {status}")
    
    # Test tampered attestation
    print()
    print("🧪 Tamper test:")
    att_tampered = Attestation.from_dict(att1.to_dict())
    att_tampered.task = "TAMPERED-task"
    print(f"  Original:  {att1.verify()}")
    print(f"  Tampered:  {att_tampered.verify()}")
    
    print()
    print("Demo complete! ✅")


if __name__ == "__main__":
    cli()
