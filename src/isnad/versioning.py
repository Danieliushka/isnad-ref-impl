#!/usr/bin/env python3
"""
isnad.versioning — Schema versioning and migration for attestations.

Handles:
- Attestation format versioning (v1, v2, ...)
- Forward/backward compatible schema evolution
- Migration pipelines for upgrading old attestations
- Version negotiation between peers
"""

import copy
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class SchemaVersion(Enum):
    """Known attestation schema versions."""
    V1 = "1.0"
    V1_1 = "1.1"
    V2 = "2.0"


# Current version
CURRENT_VERSION = SchemaVersion.V2


@dataclass
class MigrationStep:
    """A single migration from one version to another."""
    from_version: SchemaVersion
    to_version: SchemaVersion
    migrate_fn: Callable[[dict], dict]
    description: str = ""
    reversible: bool = False
    rollback_fn: Optional[Callable[[dict], dict]] = None


@dataclass
class MigrationResult:
    """Result of applying a migration pipeline."""
    success: bool
    original_version: SchemaVersion
    target_version: SchemaVersion
    data: dict
    steps_applied: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class SchemaRegistry:
    """Registry of known schema versions and their validators."""

    def __init__(self):
        self._schemas: Dict[SchemaVersion, dict] = {}
        self._validators: Dict[SchemaVersion, Callable[[dict], Tuple[bool, List[str]]]] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register built-in schema versions."""
        # V1: Original minimal attestation
        self._schemas[SchemaVersion.V1] = {
            "required": ["attester", "subject", "claim", "signature", "timestamp"],
            "optional": ["chain_id", "metadata"],
        }
        self._validators[SchemaVersion.V1] = self._validate_v1

        # V1.1: Added scope and expiry
        self._schemas[SchemaVersion.V1_1] = {
            "required": ["attester", "subject", "claim", "signature", "timestamp"],
            "optional": ["chain_id", "metadata", "scope", "expires_at"],
        }
        self._validators[SchemaVersion.V1_1] = self._validate_v1_1

        # V2: Added provenance, context, evidence
        self._schemas[SchemaVersion.V2] = {
            "required": ["attester", "subject", "claim", "signature", "timestamp", "schema_version"],
            "optional": [
                "chain_id", "metadata", "scope", "expires_at",
                "provenance", "context", "evidence", "delegation_chain",
            ],
        }
        self._validators[SchemaVersion.V2] = self._validate_v2

    def register(self, version: SchemaVersion, schema: dict,
                 validator: Optional[Callable] = None):
        """Register a custom schema version."""
        self._schemas[version] = schema
        if validator:
            self._validators[version] = validator

    def detect_version(self, attestation: dict) -> SchemaVersion:
        """Detect the schema version of an attestation."""
        if "schema_version" in attestation:
            v = attestation["schema_version"]
            for sv in SchemaVersion:
                if sv.value == v:
                    return sv

        # Heuristic detection for legacy attestations
        if "provenance" in attestation or "context" in attestation:
            return SchemaVersion.V2
        if "scope" in attestation or "expires_at" in attestation:
            return SchemaVersion.V1_1
        return SchemaVersion.V1

    def validate(self, attestation: dict, version: Optional[SchemaVersion] = None) -> Tuple[bool, List[str]]:
        """Validate an attestation against its schema."""
        version = version or self.detect_version(attestation)
        if version in self._validators:
            return self._validators[version](attestation)
        return self._validate_generic(attestation, version)

    def _validate_generic(self, attestation: dict, version: SchemaVersion) -> Tuple[bool, List[str]]:
        schema = self._schemas.get(version)
        if not schema:
            return False, [f"Unknown schema version: {version}"]
        errors = []
        for field_name in schema.get("required", []):
            if field_name not in attestation:
                errors.append(f"Missing required field: {field_name}")
        return len(errors) == 0, errors

    def _validate_v1(self, attestation: dict) -> Tuple[bool, List[str]]:
        errors = []
        for f in ["attester", "subject", "claim", "signature", "timestamp"]:
            if f not in attestation:
                errors.append(f"Missing required field: {f}")
        if "timestamp" in attestation:
            ts = attestation["timestamp"]
            if not isinstance(ts, (int, float)) or ts < 0:
                errors.append("Invalid timestamp")
        return len(errors) == 0, errors

    def _validate_v1_1(self, attestation: dict) -> Tuple[bool, List[str]]:
        valid, errors = self._validate_v1(attestation)
        if "expires_at" in attestation:
            exp = attestation["expires_at"]
            if not isinstance(exp, (int, float)) or exp < 0:
                errors.append("Invalid expires_at")
            elif "timestamp" in attestation and exp <= attestation.get("timestamp", 0):
                errors.append("expires_at must be after timestamp")
        if "scope" in attestation:
            if not isinstance(attestation["scope"], str):
                errors.append("scope must be a string")
        return len(errors) == 0, errors

    def _validate_v2(self, attestation: dict) -> Tuple[bool, List[str]]:
        valid, errors = self._validate_v1_1(attestation)
        if "provenance" in attestation:
            prov = attestation["provenance"]
            if not isinstance(prov, dict):
                errors.append("provenance must be a dict")
            elif "origin" not in prov:
                errors.append("provenance must have 'origin' field")
        if "evidence" in attestation:
            if not isinstance(attestation["evidence"], list):
                errors.append("evidence must be a list")
        if "delegation_chain" in attestation:
            if not isinstance(attestation["delegation_chain"], list):
                errors.append("delegation_chain must be a list")
        return len(errors) == 0, errors


class MigrationPipeline:
    """Pipeline for migrating attestations between schema versions."""

    def __init__(self):
        self._steps: List[MigrationStep] = []
        self._register_defaults()

    def _register_defaults(self):
        """Register built-in migration steps."""
        self.add_step(MigrationStep(
            from_version=SchemaVersion.V1,
            to_version=SchemaVersion.V1_1,
            migrate_fn=self._migrate_v1_to_v1_1,
            description="Add scope and expires_at support",
            reversible=True,
            rollback_fn=self._rollback_v1_1_to_v1,
        ))
        self.add_step(MigrationStep(
            from_version=SchemaVersion.V1_1,
            to_version=SchemaVersion.V2,
            migrate_fn=self._migrate_v1_1_to_v2,
            description="Add provenance, context, evidence, schema_version tag",
            reversible=True,
            rollback_fn=self._rollback_v2_to_v1_1,
        ))

    def add_step(self, step: MigrationStep):
        """Register a migration step."""
        self._steps.append(step)

    def find_path(self, from_version: SchemaVersion,
                  to_version: SchemaVersion) -> List[MigrationStep]:
        """Find migration path between versions using BFS."""
        if from_version == to_version:
            return []

        # Build adjacency from steps
        forward = {s.from_version: s for s in self._steps}
        backward = {s.to_version: s for s in self._steps if s.reversible}

        # Determine direction
        versions = list(SchemaVersion)
        from_idx = versions.index(from_version)
        to_idx = versions.index(to_version)

        path = []
        if to_idx > from_idx:
            # Forward migration
            current = from_version
            while current != to_version:
                step = forward.get(current)
                if not step:
                    return []  # No path
                path.append(step)
                current = step.to_version
        else:
            # Backward migration (rollback)
            current = from_version
            while current != to_version:
                step = backward.get(current)
                if not step:
                    return []  # No reversible path
                # Create a rollback step
                rb = MigrationStep(
                    from_version=step.to_version,
                    to_version=step.from_version,
                    migrate_fn=step.rollback_fn,
                    description=f"Rollback: {step.description}",
                )
                path.append(rb)
                current = step.from_version

        return path

    def migrate(self, attestation: dict, target_version: SchemaVersion,
                registry: Optional[SchemaRegistry] = None) -> MigrationResult:
        """Migrate an attestation to the target version."""
        registry = registry or SchemaRegistry()
        current_version = registry.detect_version(attestation)

        if current_version == target_version:
            return MigrationResult(
                success=True,
                original_version=current_version,
                target_version=target_version,
                data=copy.deepcopy(attestation),
            )

        path = self.find_path(current_version, target_version)
        if not path:
            return MigrationResult(
                success=False,
                original_version=current_version,
                target_version=target_version,
                data=attestation,
                errors=[f"No migration path from {current_version.value} to {target_version.value}"],
            )

        data = copy.deepcopy(attestation)
        steps_applied = []

        for step in path:
            try:
                data = step.migrate_fn(data)
                steps_applied.append(f"{step.from_version.value} → {step.to_version.value}: {step.description}")
            except Exception as e:
                return MigrationResult(
                    success=False,
                    original_version=current_version,
                    target_version=target_version,
                    data=attestation,
                    steps_applied=steps_applied,
                    errors=[f"Migration failed at {step.from_version.value} → {step.to_version.value}: {e}"],
                )

        # Validate result
        valid, errors = registry.validate(data, target_version)
        if not valid:
            return MigrationResult(
                success=False,
                original_version=current_version,
                target_version=target_version,
                data=data,
                steps_applied=steps_applied,
                errors=[f"Post-migration validation failed: {e}" for e in errors],
            )

        return MigrationResult(
            success=True,
            original_version=current_version,
            target_version=target_version,
            data=data,
            steps_applied=steps_applied,
        )

    def migrate_batch(self, attestations: List[dict],
                      target_version: SchemaVersion,
                      registry: Optional[SchemaRegistry] = None) -> List[MigrationResult]:
        """Migrate a batch of attestations."""
        return [self.migrate(a, target_version, registry) for a in attestations]

    # ─── Built-in migrations ──────────────────────────

    @staticmethod
    def _migrate_v1_to_v1_1(data: dict) -> dict:
        """V1 → V1.1: Add scope and expires_at defaults."""
        data.setdefault("scope", "global")
        # No default expiry — attestations are permanent unless specified
        return data

    @staticmethod
    def _rollback_v1_1_to_v1(data: dict) -> dict:
        """V1.1 → V1: Remove scope and expires_at."""
        data.pop("scope", None)
        data.pop("expires_at", None)
        return data

    @staticmethod
    def _migrate_v1_1_to_v2(data: dict) -> dict:
        """V1.1 → V2: Add provenance, schema_version tag."""
        data["schema_version"] = SchemaVersion.V2.value
        data.setdefault("provenance", {
            "origin": "migration",
            "migrated_at": time.time(),
            "original_version": SchemaVersion.V1_1.value,
        })
        return data

    @staticmethod
    def _rollback_v2_to_v1_1(data: dict) -> dict:
        """V2 → V1.1: Remove v2-only fields."""
        data.pop("schema_version", None)
        data.pop("provenance", None)
        data.pop("context", None)
        data.pop("evidence", None)
        data.pop("delegation_chain", None)
        return data


class VersionNegotiator:
    """Negotiate schema version between peers."""

    def __init__(self, supported: Optional[List[SchemaVersion]] = None):
        self.supported = list(SchemaVersion) if supported is None else supported

    def negotiate(self, peer_supported: List[SchemaVersion]) -> Optional[SchemaVersion]:
        """Find highest mutually supported version."""
        if not self.supported:
            return None
        mutual = set(self.supported) & set(peer_supported)
        if not mutual:
            return None
        versions = list(SchemaVersion)
        return max(mutual, key=lambda v: versions.index(v))

    def can_accept(self, version: SchemaVersion) -> bool:
        """Check if we can accept this version."""
        return version in self.supported

    def handshake_offer(self) -> dict:
        """Generate a version handshake offer."""
        return {
            "supported_versions": [v.value for v in self.supported],
            "preferred_version": self.supported[-1].value if self.supported else None,
            "timestamp": time.time(),
        }

    def handshake_accept(self, offer: dict) -> dict:
        """Accept a version handshake."""
        peer_versions = []
        for v_str in offer.get("supported_versions", []):
            for sv in SchemaVersion:
                if sv.value == v_str:
                    peer_versions.append(sv)

        agreed = self.negotiate(peer_versions)
        return {
            "agreed_version": agreed.value if agreed else None,
            "accepted": agreed is not None,
            "timestamp": time.time(),
        }
