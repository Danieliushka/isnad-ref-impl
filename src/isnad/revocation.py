"""isnad.revocation — Certificate/attestation revocation system.

Provides:
- RevocationReason enum
- RevocationList — maintains revoked attestation IDs with reason + timestamp
- RevocationCheck — checks if any attestation in a chain is revoked
"""

import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from isnad.core import Attestation, TrustChain


class RevocationReason(Enum):
    """Standard reasons for revoking an attestation."""
    KEY_COMPROMISE = "key_compromise"
    SUPERSEDED = "superseded"
    CEASED_OPERATION = "ceased_operation"
    PRIVILEGE_WITHDRAWN = "privilege_withdrawn"


class RevocationRecord:
    """A single revocation entry."""

    def __init__(self, attestation_id: str, reason: RevocationReason,
                 timestamp: Optional[float] = None, revoked_by: str = ""):
        self.attestation_id = attestation_id
        self.reason = reason
        self.timestamp = timestamp or time.time()
        self.revoked_by = revoked_by

    def to_dict(self) -> dict:
        return {
            "attestation_id": self.attestation_id,
            "reason": self.reason.value,
            "timestamp": self.timestamp,
            "revoked_by": self.revoked_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RevocationRecord":
        return cls(
            attestation_id=data["attestation_id"],
            reason=RevocationReason(data["reason"]),
            timestamp=data.get("timestamp", time.time()),
            revoked_by=data.get("revoked_by", ""),
        )

    def __repr__(self):
        return f"RevocationRecord({self.attestation_id}, {self.reason.name})"


class RevocationList:
    """Maintains a list of revoked attestation IDs with reason and timestamp."""

    def __init__(self):
        self._revoked: dict[str, RevocationRecord] = {}

    def revoke(self, attestation_id: str, reason: RevocationReason,
               revoked_by: str = "", timestamp: Optional[float] = None) -> RevocationRecord:
        """Revoke an attestation. Idempotent — double revoke keeps first entry."""
        if attestation_id in self._revoked:
            return self._revoked[attestation_id]
        record = RevocationRecord(
            attestation_id=attestation_id,
            reason=reason,
            timestamp=timestamp,
            revoked_by=revoked_by,
        )
        self._revoked[attestation_id] = record
        return record

    def unrevoke(self, attestation_id: str) -> bool:
        """Remove a revocation. Returns True if it existed."""
        if attestation_id in self._revoked:
            del self._revoked[attestation_id]
            return True
        return False

    def is_revoked(self, attestation_id: str) -> bool:
        return attestation_id in self._revoked

    def get(self, attestation_id: str) -> Optional[RevocationRecord]:
        return self._revoked.get(attestation_id)

    @property
    def count(self) -> int:
        return len(self._revoked)

    @property
    def all_records(self) -> list[RevocationRecord]:
        return list(self._revoked.values())

    @property
    def revoked_ids(self) -> set[str]:
        return set(self._revoked.keys())

    def to_json(self) -> str:
        return json.dumps([r.to_dict() for r in self._revoked.values()], indent=2)

    @classmethod
    def from_json(cls, data: str) -> "RevocationList":
        rl = cls()
        for item in json.loads(data):
            record = RevocationRecord.from_dict(item)
            rl._revoked[record.attestation_id] = record
        return rl

    def to_dict(self) -> list[dict]:
        return [r.to_dict() for r in self._revoked.values()]

    @classmethod
    def from_dict(cls, data: list[dict]) -> "RevocationList":
        rl = cls()
        for item in data:
            record = RevocationRecord.from_dict(item)
            rl._revoked[record.attestation_id] = record
        return rl

    def __len__(self):
        return len(self._revoked)

    def __contains__(self, attestation_id: str) -> bool:
        return attestation_id in self._revoked

    def __repr__(self):
        return f"RevocationList({self.count} entries)"


class RevocationCheck:
    """Check attestation chains against a RevocationList."""

    def __init__(self, revocation_list: RevocationList):
        self.revocation_list = revocation_list

    def check_attestation(self, attestation: Attestation) -> bool:
        """Returns True if attestation is NOT revoked (i.e., valid)."""
        return not self.revocation_list.is_revoked(attestation.attestation_id)

    def check_chain(self, chain: TrustChain) -> tuple[bool, list[str]]:
        """Check all attestations in a chain.

        Returns (all_valid, list_of_revoked_ids).
        """
        revoked_ids = []
        for att in chain.attestations:
            if self.revocation_list.is_revoked(att.attestation_id):
                revoked_ids.append(att.attestation_id)
        return len(revoked_ids) == 0, revoked_ids

    def trust_score(self, chain: TrustChain, agent_id: str,
                    scope: Optional[str] = None) -> float:
        """Compute trust score, returning 0 if any attestation for the agent is revoked."""
        attestations = chain._by_subject.get(agent_id, [])
        if not attestations:
            return 0.0

        if scope:
            attestations = [a for a in attestations if scope.lower() in a.task.lower()]

        for att in attestations:
            if self.revocation_list.is_revoked(att.attestation_id):
                return 0.0

        return chain.trust_score(agent_id, scope=scope)
