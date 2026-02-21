"""
isnad.compliance — Data Protection & Regulatory Compliance

Implements privacy-preserving trust management:
- Right to erasure (GDPR Art. 17) for trust data
- Data retention policies with automatic expiry
- Consent management for trust sharing
- Anonymization of trust chains
- Compliance audit trail
- Data portability (GDPR Art. 20)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DataBasis(Enum):
    """Legal basis for processing trust data (GDPR Art. 6)."""
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGITIMATE_INTEREST = "legitimate_interest"
    LEGAL_OBLIGATION = "legal_obligation"


class ErasureScope(Enum):
    """What to erase when right-to-erasure is exercised."""
    FULL = "full"                    # All data about the agent
    ATTESTATIONS_ONLY = "attestations"  # Only attestations (keep identity)
    DEIDENTIFY = "deidentify"        # Replace identity with pseudonym


@dataclass
class ConsentRecord:
    """Records an agent's consent for trust data processing."""
    agent_id: str
    purpose: str
    basis: DataBasis
    granted_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    revoked_at: Optional[float] = None
    scope: list[str] = field(default_factory=lambda: ["attestation", "discovery"])

    @property
    def is_valid(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True


@dataclass
class RetentionPolicy:
    """Defines how long trust data is retained."""
    name: str
    max_age_seconds: float
    applies_to: list[str] = field(default_factory=lambda: ["attestation"])
    auto_anonymize: bool = False  # Anonymize instead of delete on expiry
    review_interval_seconds: float = 86400  # Daily review by default

    def is_expired(self, created_at: float) -> bool:
        return (time.time() - created_at) > self.max_age_seconds


@dataclass
class ErasureRequest:
    """Tracks a right-to-erasure request."""
    request_id: str
    agent_id: str
    scope: ErasureScope
    requested_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    items_erased: int = 0
    items_anonymized: int = 0
    reason: str = ""
    federated: bool = False  # Propagate to federated peers


@dataclass
class ComplianceEvent:
    """Audit trail entry for compliance actions."""
    event_type: str  # consent_granted, consent_revoked, erasure_requested, etc.
    agent_id: str
    timestamp: float = field(default_factory=time.time)
    details: dict = field(default_factory=dict)


class ConsentManager:
    """Manages consent records for trust data processing."""

    def __init__(self):
        self._consents: dict[str, list[ConsentRecord]] = {}  # agent_id -> consents

    def grant(self, agent_id: str, purpose: str, basis: DataBasis = DataBasis.CONSENT,
              expires_in: Optional[float] = None, scope: Optional[list[str]] = None) -> ConsentRecord:
        expires_at = (time.time() + expires_in) if expires_in else None
        record = ConsentRecord(
            agent_id=agent_id,
            purpose=purpose,
            basis=basis,
            expires_at=expires_at,
            scope=scope or ["attestation", "discovery"],
        )
        self._consents.setdefault(agent_id, []).append(record)
        return record

    def revoke(self, agent_id: str, purpose: Optional[str] = None) -> int:
        """Revoke consent. Returns number of consents revoked."""
        records = self._consents.get(agent_id, [])
        count = 0
        now = time.time()
        for r in records:
            if r.revoked_at is None and (purpose is None or r.purpose == purpose):
                r.revoked_at = now
                count += 1
        return count

    def has_consent(self, agent_id: str, purpose: str, scope: str = "attestation") -> bool:
        for r in self._consents.get(agent_id, []):
            if r.is_valid and r.purpose == purpose and scope in r.scope:
                return True
        return False

    def get_consents(self, agent_id: str) -> list[ConsentRecord]:
        return [r for r in self._consents.get(agent_id, []) if r.is_valid]

    def get_all_consents(self, agent_id: str) -> list[ConsentRecord]:
        return list(self._consents.get(agent_id, []))

    def cleanup_expired(self) -> int:
        """Remove expired consents. Returns count removed."""
        count = 0
        for agent_id in list(self._consents.keys()):
            before = len(self._consents[agent_id])
            self._consents[agent_id] = [r for r in self._consents[agent_id]
                                         if r.revoked_at is None and
                                         (r.expires_at is None or time.time() <= r.expires_at)]
            count += before - len(self._consents[agent_id])
        return count


class DataAnonymizer:
    """Pseudonymizes agent identities in trust data."""

    def __init__(self, salt: Optional[str] = None):
        self._salt = salt or hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
        self._mapping: dict[str, str] = {}

    def pseudonymize(self, agent_id: str) -> str:
        if agent_id not in self._mapping:
            h = hashlib.sha256(f"{self._salt}:{agent_id}".encode()).hexdigest()[:16]
            self._mapping[agent_id] = f"anon-{h}"
        return self._mapping[agent_id]

    def anonymize_attestation(self, attestation: dict) -> dict:
        """Return a copy with pseudonymized identities."""
        result = dict(attestation)
        for key in ("signer", "subject", "issuer", "agent_id"):
            if key in result:
                result[key] = self.pseudonymize(result[key])
        return result

    def anonymize_chain(self, chain: list[dict]) -> list[dict]:
        return [self.anonymize_attestation(a) for a in chain]


class RetentionEnforcer:
    """Enforces data retention policies."""

    def __init__(self):
        self._policies: list[RetentionPolicy] = []
        self._data_timestamps: dict[str, float] = {}  # item_id -> created_at

    def add_policy(self, policy: RetentionPolicy) -> None:
        self._policies.append(policy)

    def register_data(self, item_id: str, created_at: Optional[float] = None,
                      data_type: str = "attestation") -> None:
        self._data_timestamps[item_id] = created_at or time.time()

    def get_expired(self, data_type: str = "attestation") -> list[str]:
        """Return item IDs that have exceeded retention period."""
        expired = []
        applicable = [p for p in self._policies if data_type in p.applies_to]
        if not applicable:
            return expired
        strictest = min(applicable, key=lambda p: p.max_age_seconds)
        for item_id, created_at in self._data_timestamps.items():
            if strictest.is_expired(created_at):
                expired.append(item_id)
        return expired

    def enforce(self, data_type: str = "attestation") -> tuple[list[str], list[str]]:
        """Enforce retention. Returns (deleted_ids, anonymized_ids)."""
        deleted, anonymized = [], []
        applicable = [p for p in self._policies if data_type in p.applies_to]
        if not applicable:
            return deleted, anonymized
        strictest = min(applicable, key=lambda p: p.max_age_seconds)
        for item_id, created_at in list(self._data_timestamps.items()):
            if strictest.is_expired(created_at):
                if strictest.auto_anonymize:
                    anonymized.append(item_id)
                else:
                    deleted.append(item_id)
                    del self._data_timestamps[item_id]
        return deleted, anonymized


class ComplianceManager:
    """
    Central compliance coordinator.
    
    Combines consent management, data retention, anonymization,
    and right-to-erasure into a unified compliance layer.
    """

    def __init__(self):
        self.consent = ConsentManager()
        self.anonymizer = DataAnonymizer()
        self.retention = RetentionEnforcer()
        self._erasure_requests: list[ErasureRequest] = []
        self._audit_trail: list[ComplianceEvent] = []
        self._trust_data: dict[str, list[dict]] = {}  # agent_id -> attestations

    def _log(self, event_type: str, agent_id: str, **details) -> None:
        self._audit_trail.append(ComplianceEvent(
            event_type=event_type,
            agent_id=agent_id,
            details=details,
        ))

    # --- Consent ---

    def grant_consent(self, agent_id: str, purpose: str,
                      basis: DataBasis = DataBasis.CONSENT,
                      expires_in: Optional[float] = None) -> ConsentRecord:
        record = self.consent.grant(agent_id, purpose, basis, expires_in)
        self._log("consent_granted", agent_id, purpose=purpose, basis=basis.value)
        return record

    def revoke_consent(self, agent_id: str, purpose: Optional[str] = None) -> int:
        count = self.consent.revoke(agent_id, purpose)
        self._log("consent_revoked", agent_id, purpose=purpose or "all", count=count)
        return count

    def check_consent(self, agent_id: str, purpose: str, scope: str = "attestation") -> bool:
        return self.consent.has_consent(agent_id, purpose, scope)

    # --- Trust Data Management ---

    def store_attestation(self, agent_id: str, attestation: dict) -> bool:
        """Store attestation if consent exists. Returns True if stored."""
        if not self.consent.has_consent(agent_id, "trust_processing"):
            self._log("store_rejected", agent_id, reason="no_consent")
            return False
        self._trust_data.setdefault(agent_id, []).append(attestation)
        item_id = attestation.get("id", f"{agent_id}:{len(self._trust_data[agent_id])}")
        self.retention.register_data(item_id)
        self._log("attestation_stored", agent_id, item_id=item_id)
        return True

    # --- Right to Erasure ---

    def request_erasure(self, agent_id: str, scope: ErasureScope = ErasureScope.FULL,
                        reason: str = "", federated: bool = False) -> ErasureRequest:
        request = ErasureRequest(
            request_id=hashlib.sha256(f"{agent_id}:{time.time()}".encode()).hexdigest()[:12],
            agent_id=agent_id,
            scope=scope,
            reason=reason,
            federated=federated,
        )
        self._erasure_requests.append(request)
        self._log("erasure_requested", agent_id, scope=scope.value, federated=federated)
        self._execute_erasure(request)
        return request

    def _execute_erasure(self, request: ErasureRequest) -> None:
        agent_id = request.agent_id
        attestations = self._trust_data.get(agent_id, [])

        if request.scope == ErasureScope.FULL:
            request.items_erased = len(attestations)
            self._trust_data.pop(agent_id, None)
            self.consent.revoke(agent_id)

        elif request.scope == ErasureScope.ATTESTATIONS_ONLY:
            request.items_erased = len(attestations)
            self._trust_data.pop(agent_id, None)

        elif request.scope == ErasureScope.DEIDENTIFY:
            if attestations:
                self._trust_data[agent_id] = self.anonymizer.anonymize_chain(attestations)
                request.items_anonymized = len(attestations)
                # Move to pseudonymized key
                pseudo_id = self.anonymizer.pseudonymize(agent_id)
                self._trust_data[pseudo_id] = self._trust_data.pop(agent_id)

        request.completed_at = time.time()
        self._log("erasure_completed", agent_id,
                  scope=request.scope.value,
                  erased=request.items_erased,
                  anonymized=request.items_anonymized)

    # --- Data Portability ---

    def export_agent_data(self, agent_id: str) -> dict:
        """Export all data about an agent (GDPR Art. 20 portability)."""
        return {
            "agent_id": agent_id,
            "exported_at": time.time(),
            "attestations": list(self._trust_data.get(agent_id, [])),
            "consents": [
                {
                    "purpose": c.purpose,
                    "basis": c.basis.value,
                    "granted_at": c.granted_at,
                    "expires_at": c.expires_at,
                    "revoked_at": c.revoked_at,
                    "scope": c.scope,
                    "valid": c.is_valid,
                }
                for c in self.consent.get_all_consents(agent_id)
            ],
            "erasure_requests": [
                {
                    "request_id": r.request_id,
                    "scope": r.scope.value,
                    "requested_at": r.requested_at,
                    "completed_at": r.completed_at,
                }
                for r in self._erasure_requests if r.agent_id == agent_id
            ],
        }

    # --- Audit ---

    def get_audit_trail(self, agent_id: Optional[str] = None,
                        event_type: Optional[str] = None,
                        since: Optional[float] = None) -> list[ComplianceEvent]:
        trail = self._audit_trail
        if agent_id:
            trail = [e for e in trail if e.agent_id == agent_id]
        if event_type:
            trail = [e for e in trail if e.event_type == event_type]
        if since:
            trail = [e for e in trail if e.timestamp >= since]
        return trail

    def get_erasure_requests(self, agent_id: Optional[str] = None) -> list[ErasureRequest]:
        if agent_id:
            return [r for r in self._erasure_requests if r.agent_id == agent_id]
        return list(self._erasure_requests)

    # --- Retention ---

    def enforce_retention(self) -> dict:
        """Run retention enforcement. Returns summary."""
        deleted, anonymized = self.retention.enforce()
        expired_consents = self.consent.cleanup_expired()
        return {
            "data_deleted": len(deleted),
            "data_anonymized": len(anonymized),
            "consents_expired": expired_consents,
            "timestamp": time.time(),
        }

    # --- Summary ---

    def compliance_summary(self) -> dict:
        """Get overall compliance status."""
        total_agents = len(self._trust_data)
        total_attestations = sum(len(a) for a in self._trust_data.values())
        return {
            "agents_tracked": total_agents,
            "attestations_stored": total_attestations,
            "active_erasure_requests": len([r for r in self._erasure_requests if not r.completed_at]),
            "completed_erasures": len([r for r in self._erasure_requests if r.completed_at]),
            "audit_events": len(self._audit_trail),
            "retention_policies": len(self.retention._policies),
        }
