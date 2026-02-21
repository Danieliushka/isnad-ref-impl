#!/usr/bin/env python3
"""Tests for isnad.versioning — schema versioning and migration."""

import time
import pytest
from isnad.versioning import (
    SchemaVersion, CURRENT_VERSION,
    SchemaRegistry, MigrationPipeline, MigrationResult,
    MigrationStep, VersionNegotiator,
)


# ─── Fixtures ──────────────────────────────────────────

@pytest.fixture
def v1_attestation():
    return {
        "attester": "agent:abc123",
        "subject": "agent:def456",
        "claim": "reliable",
        "signature": "deadbeef" * 8,
        "timestamp": time.time(),
    }


@pytest.fixture
def v1_1_attestation(v1_attestation):
    return {
        **v1_attestation,
        "scope": "api_calls",
        "expires_at": time.time() + 86400,
    }


@pytest.fixture
def v2_attestation(v1_1_attestation):
    return {
        **v1_1_attestation,
        "schema_version": "2.0",
        "provenance": {"origin": "direct", "method": "interaction"},
        "evidence": [{"type": "api_log", "hash": "abc123"}],
    }


@pytest.fixture
def registry():
    return SchemaRegistry()


@pytest.fixture
def pipeline():
    return MigrationPipeline()


# ─── SchemaRegistry ───────────────────────────────────

class TestSchemaRegistry:
    def test_detect_v1(self, registry, v1_attestation):
        assert registry.detect_version(v1_attestation) == SchemaVersion.V1

    def test_detect_v1_1(self, registry, v1_1_attestation):
        assert registry.detect_version(v1_1_attestation) == SchemaVersion.V1_1

    def test_detect_v2(self, registry, v2_attestation):
        assert registry.detect_version(v2_attestation) == SchemaVersion.V2

    def test_detect_v2_by_tag(self, registry):
        a = {"schema_version": "2.0", "attester": "x", "subject": "y",
             "claim": "z", "signature": "s", "timestamp": 1}
        assert registry.detect_version(a) == SchemaVersion.V2

    def test_validate_v1_valid(self, registry, v1_attestation):
        valid, errors = registry.validate(v1_attestation, SchemaVersion.V1)
        assert valid
        assert errors == []

    def test_validate_v1_missing_field(self, registry):
        a = {"attester": "x", "subject": "y"}
        valid, errors = registry.validate(a, SchemaVersion.V1)
        assert not valid
        assert len(errors) >= 3

    def test_validate_v1_bad_timestamp(self, registry):
        a = {"attester": "x", "subject": "y", "claim": "z",
             "signature": "s", "timestamp": -1}
        valid, errors = registry.validate(a, SchemaVersion.V1)
        assert not valid
        assert any("timestamp" in e.lower() for e in errors)

    def test_validate_v1_1_valid(self, registry, v1_1_attestation):
        valid, errors = registry.validate(v1_1_attestation, SchemaVersion.V1_1)
        assert valid

    def test_validate_v1_1_bad_expiry(self, registry, v1_attestation):
        v1_attestation["expires_at"] = v1_attestation["timestamp"] - 100
        valid, errors = registry.validate(v1_attestation, SchemaVersion.V1_1)
        assert not valid

    def test_validate_v1_1_scope_not_string(self, registry, v1_attestation):
        v1_attestation["scope"] = 123
        valid, errors = registry.validate(v1_attestation, SchemaVersion.V1_1)
        assert not valid

    def test_validate_v2_valid(self, registry, v2_attestation):
        valid, errors = registry.validate(v2_attestation, SchemaVersion.V2)
        assert valid

    def test_validate_v2_bad_provenance(self, registry, v2_attestation):
        v2_attestation["provenance"] = "not a dict"
        valid, errors = registry.validate(v2_attestation, SchemaVersion.V2)
        assert not valid

    def test_validate_v2_provenance_no_origin(self, registry, v2_attestation):
        v2_attestation["provenance"] = {"method": "test"}
        valid, errors = registry.validate(v2_attestation, SchemaVersion.V2)
        assert not valid

    def test_validate_v2_bad_evidence(self, registry, v2_attestation):
        v2_attestation["evidence"] = "not a list"
        valid, errors = registry.validate(v2_attestation, SchemaVersion.V2)
        assert not valid

    def test_validate_v2_bad_delegation(self, registry, v2_attestation):
        v2_attestation["delegation_chain"] = "not a list"
        valid, errors = registry.validate(v2_attestation, SchemaVersion.V2)
        assert not valid

    def test_register_custom(self, registry):
        custom = SchemaVersion.V1  # reuse enum for test
        registry.register(custom, {"required": ["attester"]},
                         lambda a: (True, []))
        valid, _ = registry.validate({"attester": "x"}, custom)
        assert valid


# ─── MigrationPipeline ────────────────────────────────

class TestMigrationPipeline:
    def test_v1_to_v1_1(self, pipeline, registry, v1_attestation):
        result = pipeline.migrate(v1_attestation, SchemaVersion.V1_1, registry)
        assert result.success
        assert result.data.get("scope") == "global"
        assert len(result.steps_applied) == 1

    def test_v1_to_v2(self, pipeline, registry, v1_attestation):
        result = pipeline.migrate(v1_attestation, SchemaVersion.V2, registry)
        assert result.success
        assert result.data.get("schema_version") == "2.0"
        assert "provenance" in result.data
        assert len(result.steps_applied) == 2

    def test_v1_1_to_v2(self, pipeline, registry, v1_1_attestation):
        result = pipeline.migrate(v1_1_attestation, SchemaVersion.V2, registry)
        assert result.success
        assert result.data["schema_version"] == "2.0"

    def test_same_version_noop(self, pipeline, registry, v2_attestation):
        result = pipeline.migrate(v2_attestation, SchemaVersion.V2, registry)
        assert result.success
        assert result.steps_applied == []

    def test_rollback_v2_to_v1_1(self, pipeline, registry, v2_attestation):
        result = pipeline.migrate(v2_attestation, SchemaVersion.V1_1, registry)
        assert result.success
        assert "schema_version" not in result.data
        assert "provenance" not in result.data

    def test_rollback_v2_to_v1(self, pipeline, registry, v2_attestation):
        result = pipeline.migrate(v2_attestation, SchemaVersion.V1, registry)
        assert result.success
        assert "scope" not in result.data
        assert "schema_version" not in result.data

    def test_rollback_v1_1_to_v1(self, pipeline, registry, v1_1_attestation):
        result = pipeline.migrate(v1_1_attestation, SchemaVersion.V1, registry)
        assert result.success
        assert "scope" not in result.data
        assert "expires_at" not in result.data

    def test_original_not_mutated(self, pipeline, registry, v1_attestation):
        original = v1_attestation.copy()
        pipeline.migrate(v1_attestation, SchemaVersion.V2, registry)
        assert v1_attestation == original

    def test_batch_migrate(self, pipeline, registry, v1_attestation):
        batch = [v1_attestation.copy() for _ in range(5)]
        results = pipeline.migrate_batch(batch, SchemaVersion.V2, registry)
        assert len(results) == 5
        assert all(r.success for r in results)

    def test_roundtrip_v1_v2_v1(self, pipeline, registry, v1_attestation):
        """V1 → V2 → V1 should preserve core fields."""
        up = pipeline.migrate(v1_attestation, SchemaVersion.V2, registry)
        assert up.success
        down = pipeline.migrate(up.data, SchemaVersion.V1, registry)
        assert down.success
        for key in ["attester", "subject", "claim", "signature", "timestamp"]:
            assert down.data[key] == v1_attestation[key]

    def test_custom_step(self, pipeline, registry):
        """Custom migration step."""
        def add_custom(data):
            data["custom_field"] = "hello"
            return data

        # This won't fit neatly into the enum-based path, but let's test the step itself
        step = MigrationStep(
            from_version=SchemaVersion.V1,
            to_version=SchemaVersion.V1_1,
            migrate_fn=add_custom,
            description="Add custom field",
        )
        result = step.migrate_fn({"attester": "x", "subject": "y",
                                   "claim": "z", "signature": "s",
                                   "timestamp": time.time()})
        assert result["custom_field"] == "hello"

    def test_migration_result_fields(self, pipeline, registry, v1_attestation):
        result = pipeline.migrate(v1_attestation, SchemaVersion.V2, registry)
        assert result.original_version == SchemaVersion.V1
        assert result.target_version == SchemaVersion.V2
        assert isinstance(result.data, dict)
        assert isinstance(result.steps_applied, list)
        assert result.errors == []


# ─── VersionNegotiator ─────────────────────────────────

class TestVersionNegotiator:
    def test_negotiate_all_supported(self):
        n = VersionNegotiator()
        result = n.negotiate([SchemaVersion.V1, SchemaVersion.V2])
        assert result == SchemaVersion.V2

    def test_negotiate_v1_only(self):
        n = VersionNegotiator([SchemaVersion.V1])
        result = n.negotiate([SchemaVersion.V1, SchemaVersion.V2])
        assert result == SchemaVersion.V1

    def test_negotiate_no_overlap(self):
        n = VersionNegotiator([SchemaVersion.V1])
        result = n.negotiate([SchemaVersion.V2])
        assert result is None

    def test_can_accept(self):
        n = VersionNegotiator([SchemaVersion.V1, SchemaVersion.V1_1])
        assert n.can_accept(SchemaVersion.V1)
        assert n.can_accept(SchemaVersion.V1_1)
        assert not n.can_accept(SchemaVersion.V2)

    def test_handshake_offer(self):
        n = VersionNegotiator()
        offer = n.handshake_offer()
        assert "supported_versions" in offer
        assert "preferred_version" in offer
        assert offer["preferred_version"] == SchemaVersion.V2.value

    def test_handshake_accept_success(self):
        n1 = VersionNegotiator()
        n2 = VersionNegotiator()
        offer = n1.handshake_offer()
        response = n2.handshake_accept(offer)
        assert response["accepted"]
        assert response["agreed_version"] == SchemaVersion.V2.value

    def test_handshake_accept_partial(self):
        n1 = VersionNegotiator([SchemaVersion.V1])
        n2 = VersionNegotiator([SchemaVersion.V1, SchemaVersion.V2])
        offer = n1.handshake_offer()
        response = n2.handshake_accept(offer)
        assert response["accepted"]
        assert response["agreed_version"] == SchemaVersion.V1.value

    def test_handshake_reject(self):
        n1 = VersionNegotiator([SchemaVersion.V1])
        offer = n1.handshake_offer()
        n2 = VersionNegotiator([SchemaVersion.V2])
        response = n2.handshake_accept(offer)
        assert not response["accepted"]
        assert response["agreed_version"] is None

    def test_empty_supported(self):
        n = VersionNegotiator([])
        assert n.negotiate([SchemaVersion.V1]) is None
        offer = n.handshake_offer()
        assert offer["preferred_version"] is None


# ─── Constants ─────────────────────────────────────────

class TestConstants:
    def test_current_version(self):
        assert CURRENT_VERSION == SchemaVersion.V2

    def test_schema_values(self):
        assert SchemaVersion.V1.value == "1.0"
        assert SchemaVersion.V1_1.value == "1.1"
        assert SchemaVersion.V2.value == "2.0"
