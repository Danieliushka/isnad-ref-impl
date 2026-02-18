"""
isnad Audit Trail — tamper-evident logging for agent trust decisions.

Hash-chained audit entries ensure integrity. Each entry includes the hash
of the previous entry, creating a verifiable chain. Any modification to
historical entries breaks the chain and is detectable.

Enterprise use: compliance, forensics, dispute resolution.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class AuditEventType(str, Enum):
    """Types of auditable events in the trust system."""
    ATTESTATION_CREATED = "attestation.created"
    ATTESTATION_VERIFIED = "attestation.verified"
    ATTESTATION_FAILED = "attestation.failed"
    ATTESTATION_REVOKED = "attestation.revoked"
    ACCESS_GRANTED = "access.granted"
    ACCESS_DENIED = "access.denied"
    KEY_ROTATED = "key.rotated"
    DELEGATION_CREATED = "delegation.created"
    DELEGATION_REVOKED = "delegation.revoked"
    TRUST_SCORE_COMPUTED = "trust_score.computed"
    AGENT_REGISTERED = "agent.registered"
    POLICY_VIOLATED = "policy.violated"


@dataclass
class AuditEntry:
    """A single audit log entry with hash-chain integrity."""
    event_type: str
    agent_id: str
    timestamp: float
    details: dict
    entry_hash: str = ""
    prev_hash: str = ""
    sequence: int = 0

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry's content + prev_hash."""
        content = json.dumps({
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "sequence": self.sequence,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        return cls(**data)


class AuditTrail:
    """
    Tamper-evident audit trail for isnad trust operations.
    
    Each entry is hash-chained to the previous one. Verification
    walks the chain and checks every hash. Any tampering breaks the chain.
    
    Usage:
        trail = AuditTrail()
        trail.log(AuditEventType.ATTESTATION_CREATED, agent_id="...", details={...})
        trail.log(AuditEventType.ACCESS_GRANTED, agent_id="...", details={...})
        
        assert trail.verify_integrity()  # True if no tampering
        
        # Query
        entries = trail.query(agent_id="...")
        entries = trail.query(event_type=AuditEventType.ACCESS_DENIED)
        entries = trail.query(since=time.time() - 3600)  # last hour
    """

    def __init__(self):
        self._entries: list[AuditEntry] = []

    def log(self, event_type: AuditEventType, agent_id: str, 
            details: Optional[dict] = None) -> AuditEntry:
        """Append an audit entry to the trail."""
        prev_hash = self._entries[-1].entry_hash if self._entries else "genesis"
        
        entry = AuditEntry(
            event_type=event_type.value if isinstance(event_type, AuditEventType) else event_type,
            agent_id=agent_id,
            timestamp=time.time(),
            details=details or {},
            prev_hash=prev_hash,
            sequence=len(self._entries),
        )
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        return entry

    def verify_integrity(self) -> tuple[bool, Optional[int]]:
        """
        Verify the entire chain. Returns (True, None) if intact,
        or (False, index) of first corrupted entry.
        """
        for i, entry in enumerate(self._entries):
            # Verify hash
            expected = entry.compute_hash()
            if entry.entry_hash != expected:
                return False, i
            
            # Verify chain link
            if i == 0:
                if entry.prev_hash != "genesis":
                    return False, i
            else:
                if entry.prev_hash != self._entries[i - 1].entry_hash:
                    return False, i
        
        return True, None

    def query(self, agent_id: Optional[str] = None,
              event_type: Optional[AuditEventType] = None,
              since: Optional[float] = None,
              until: Optional[float] = None,
              limit: int = 100) -> list[AuditEntry]:
        """Query audit entries with filters."""
        results = []
        event_val = event_type.value if isinstance(event_type, AuditEventType) else event_type
        
        for entry in reversed(self._entries):
            if agent_id and entry.agent_id != agent_id:
                continue
            if event_val and entry.event_type != event_val:
                continue
            if since and entry.timestamp < since:
                continue
            if until and entry.timestamp > until:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        
        return list(reversed(results))

    def export_json(self) -> str:
        """Export full trail as JSON."""
        return json.dumps([e.to_dict() for e in self._entries], indent=2)

    @classmethod
    def from_json(cls, data: str) -> "AuditTrail":
        """Import trail from JSON. Verifies integrity after import."""
        trail = cls()
        entries = json.loads(data)
        for entry_data in entries:
            trail._entries.append(AuditEntry.from_dict(entry_data))
        
        ok, bad_idx = trail.verify_integrity()
        if not ok:
            raise ValueError(f"Imported trail has corrupted entry at index {bad_idx}")
        
        return trail

    @property
    def size(self) -> int:
        return len(self._entries)

    def summary(self) -> dict:
        """Get a summary of the audit trail."""
        event_counts: dict[str, int] = {}
        agent_set: set[str] = set()
        
        for entry in self._entries:
            event_counts[entry.event_type] = event_counts.get(entry.event_type, 0) + 1
            agent_set.add(entry.agent_id)
        
        return {
            "total_entries": len(self._entries),
            "unique_agents": len(agent_set),
            "event_counts": event_counts,
            "first_entry": self._entries[0].timestamp if self._entries else None,
            "last_entry": self._entries[-1].timestamp if self._entries else None,
            "integrity_verified": self.verify_integrity()[0],
        }
