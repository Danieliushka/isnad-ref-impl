#!/usr/bin/env python3
"""
isnad.discovery — Agent Discovery Registry

Agents register their identity + capabilities, others can discover them.
Registry entries are signed — you can verify an agent registered itself.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError

from .core import AgentIdentity


@dataclass
class AgentProfile:
    """Public profile an agent registers in the discovery registry."""
    agent_id: str
    public_key: str
    name: str
    capabilities: list[str] = field(default_factory=list)
    endpoints: dict[str, str] = field(default_factory=dict)  # protocol -> url
    metadata: dict = field(default_factory=dict)
    registered_at: float = 0.0
    updated_at: float = 0.0
    signature: str = ""  # hex-encoded signature over profile payload

    def payload_bytes(self) -> bytes:
        """Canonical bytes for signing (excludes signature itself)."""
        d = {
            "agent_id": self.agent_id,
            "public_key": self.public_key,
            "name": self.name,
            "capabilities": sorted(self.capabilities),
            "endpoints": dict(sorted(self.endpoints.items())),
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, identity: AgentIdentity) -> "AgentProfile":
        """Sign this profile with the agent's key."""
        signed = identity.signing_key.sign(self.payload_bytes())
        self.signature = signed.signature.hex()
        return self

    def verify(self) -> bool:
        """Verify the profile signature matches the public key."""
        try:
            vk = VerifyKey(bytes.fromhex(self.public_key))
            vk.verify(self.payload_bytes(), bytes.fromhex(self.signature))
            return True
        except (BadSignatureError, Exception):
            return False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class DiscoveryRegistry:
    """In-memory agent discovery registry with signed profiles."""

    def __init__(self):
        self._agents: dict[str, AgentProfile] = {}  # agent_id -> profile

    def register(self, profile: AgentProfile) -> bool:
        """Register or update an agent profile. Must be validly signed."""
        if not profile.signature:
            return False
        if not profile.verify():
            return False
        if profile.agent_id != self._derive_agent_id(profile.public_key):
            return False

        existing = self._agents.get(profile.agent_id)
        if existing and profile.updated_at <= existing.updated_at:
            return False  # stale update

        self._agents[profile.agent_id] = profile
        return True

    def unregister(self, agent_id: str) -> bool:
        """Remove an agent from the registry."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        """Get a specific agent's profile."""
        return self._agents.get(agent_id)

    def search(
        self,
        capability: Optional[str] = None,
        name_contains: Optional[str] = None,
        limit: int = 50,
    ) -> list[AgentProfile]:
        """Search for agents by capability or name."""
        results = []
        for profile in self._agents.values():
            if capability and capability not in profile.capabilities:
                continue
            if name_contains and name_contains.lower() not in profile.name.lower():
                continue
            results.append(profile)
            if len(results) >= limit:
                break
        return results

    def list_capabilities(self) -> dict[str, int]:
        """List all capabilities and how many agents offer each."""
        caps: dict[str, int] = {}
        for profile in self._agents.values():
            for cap in profile.capabilities:
                caps[cap] = caps.get(cap, 0) + 1
        return dict(sorted(caps.items(), key=lambda x: -x[1]))

    @property
    def count(self) -> int:
        return len(self._agents)

    def all(self) -> list[AgentProfile]:
        return list(self._agents.values())

    @staticmethod
    def _derive_agent_id(public_key_hex: str) -> str:
        """Derive agent_id from public key (same as core.AgentIdentity)."""
        import hashlib
        return f"agent:{hashlib.sha256(public_key_hex.encode()).hexdigest()[:16]}"

    # ── Serialization ──

    def export_json(self) -> str:
        return json.dumps([p.to_dict() for p in self._agents.values()], indent=2)

    @classmethod
    def from_json(cls, data: str) -> "DiscoveryRegistry":
        registry = cls()
        for entry in json.loads(data):
            profile = AgentProfile.from_dict(entry)
            if profile.verify():
                registry._agents[profile.agent_id] = profile
        return registry


def create_profile(
    identity: AgentIdentity,
    name: str,
    capabilities: list[str] | None = None,
    endpoints: dict[str, str] | None = None,
    metadata: dict | None = None,
) -> AgentProfile:
    """Helper: create and sign a profile from an AgentIdentity."""
    now = time.time()
    profile = AgentProfile(
        agent_id=identity.agent_id,
        public_key=identity.verify_key.encode(encoder=HexEncoder).decode(),
        name=name,
        capabilities=capabilities or [],
        endpoints=endpoints or {},
        metadata=metadata or {},
        registered_at=now,
        updated_at=now,
    )
    return profile.sign(identity)
