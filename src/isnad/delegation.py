"""
isnad delegation — Hierarchical access delegation with cryptographic chains.
Allows agents to delegate scoped permissions to other agents with depth limits.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError
from nacl.encoding import HexEncoder


@dataclass
class Delegation:
    """A signed delegation of authority from one agent to another."""

    delegate_key_hex: str = ""
    delegator_key_hex: str = ""
    scope: Optional[str] = None
    expires_at: Optional[str] = None
    max_depth: int = 1
    current_depth: int = 0
    parent_hash: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signature: str = ""
    content_hash: str = ""

    def _compute_content(self) -> str:
        parts = [
            self.delegate_key_hex,
            self.delegator_key_hex,
            self.scope or "",
            self.expires_at or "",
            str(self.max_depth),
            str(self.current_depth),
            self.parent_hash or "",
            self.timestamp,
        ]
        return "|".join(parts)

    def _compute_hash(self) -> str:
        return hashlib.sha256(self._compute_content().encode()).hexdigest()

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp
        except ValueError:
            return False

    def can_sub_delegate(self) -> bool:
        return self.current_depth < self.max_depth

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> Delegation:
        return Delegation(**{k: v for k, v in d.items() if k in Delegation.__dataclass_fields__})


class DelegationRegistry:
    """Registry for managing delegation chains."""

    def __init__(self, revocation_registry=None):
        self._delegations: dict[str, Delegation] = {}
        self._by_delegate: dict[str, list[str]] = {}
        self._revocation = revocation_registry

    def add(self, delegation: Delegation, signing_key: SigningKey) -> Delegation:
        """Add a signed delegation to the registry."""
        delegation.content_hash = delegation._compute_hash()
        content = delegation._compute_content().encode()
        sig = signing_key.sign(content, encoder=HexEncoder)
        delegation.signature = sig.signature.decode() if isinstance(sig.signature, bytes) else sig.signature

        self._delegations[delegation.content_hash] = delegation
        key = delegation.delegate_key_hex
        if key not in self._by_delegate:
            self._by_delegate[key] = []
        self._by_delegate[key].append(delegation.content_hash)
        return delegation

    def sub_delegate(
        self,
        parent_hash: str,
        delegate_key_hex: str,
        signing_key: SigningKey,
        scope: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> Delegation:
        """Create a sub-delegation from an existing delegation."""
        parent = self._delegations.get(parent_hash)
        if not parent:
            raise ValueError(f"Parent delegation {parent_hash} not found")
        if not parent.can_sub_delegate():
            raise ValueError("Max delegation depth reached")
        if parent.is_expired():
            raise ValueError("Parent delegation expired")

        child = Delegation(
            delegate_key_hex=delegate_key_hex,
            delegator_key_hex=parent.delegate_key_hex,
            scope=scope or parent.scope,
            expires_at=expires_at or parent.expires_at,
            max_depth=parent.max_depth,
            current_depth=parent.current_depth + 1,
            parent_hash=parent_hash,
        )
        return self.add(child, signing_key)

    def verify_chain(self, delegation_hash: str) -> tuple[bool, str]:
        """Verify a delegation chain from leaf to root."""
        d = self._delegations.get(delegation_hash)
        if not d:
            return False, "Delegation not found"

        if d.is_expired():
            return False, "Delegation expired"

        # Verify signature
        try:
            vk = VerifyKey(bytes.fromhex(d.delegator_key_hex))
            content = d._compute_content().encode()
            sig_bytes = bytes.fromhex(d.signature) if isinstance(d.signature, str) else d.signature
            vk.verify(content, sig_bytes)
        except (BadSignatureError, Exception) as e:
            return False, f"Signature verification failed: {e}"

        # Check revocation
        if self._revocation and hasattr(self._revocation, 'is_revoked'):
            if self._revocation.is_revoked(delegation_hash):
                return False, "Delegation revoked"

        # Verify parent chain
        if d.parent_hash:
            return self.verify_chain(d.parent_hash)

        return True, "Valid"

    def get_delegations_for(self, delegate_key_hex: str, scope: Optional[str] = None) -> list[Delegation]:
        """Get all delegations for a delegate, optionally filtered by scope."""
        hashes = self._by_delegate.get(delegate_key_hex, [])
        delegations = [self._delegations[h] for h in hashes if h in self._delegations]
        if scope:
            delegations = [d for d in delegations if d.scope == scope]
        return delegations

    def save(self, filepath: str):
        """Save registry to JSON file."""
        data = {h: d.to_dict() for h, d in self._delegations.items()}
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: str):
        """Load registry from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        for h, d in data.items():
            deleg = Delegation.from_dict(d)
            self._delegations[h] = deleg
            key = deleg.delegate_key_hex
            if key not in self._by_delegate:
                self._by_delegate[key] = []
            self._by_delegate[key].append(h)
