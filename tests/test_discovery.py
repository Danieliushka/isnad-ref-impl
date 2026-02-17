"""Tests for isnad.discovery — Agent Discovery Registry."""

import json
import time
import pytest
from isnad.core import AgentIdentity
from isnad.discovery import AgentProfile, DiscoveryRegistry, create_profile


class TestAgentProfile:
    def test_create_and_sign(self):
        identity = AgentIdentity()
        profile = create_profile(identity, "TestBot", ["code-review", "search"])
        assert profile.agent_id == identity.agent_id
        assert profile.name == "TestBot"
        assert profile.signature != ""

    def test_verify_valid(self):
        identity = AgentIdentity()
        profile = create_profile(identity, "ValidBot")
        assert profile.verify() is True

    def test_verify_tampered(self):
        identity = AgentIdentity()
        profile = create_profile(identity, "TamperedBot")
        profile.name = "EvilBot"  # tamper after signing
        assert profile.verify() is False

    def test_verify_wrong_key(self):
        id1 = AgentIdentity()
        id2 = AgentIdentity()
        profile = create_profile(id1, "Bot1")
        profile.public_key = id2.verify_key.encode().hex()  # wrong key
        assert profile.verify() is False

    def test_to_from_dict(self):
        identity = AgentIdentity()
        profile = create_profile(identity, "SerBot", ["trust"], {"rest": "http://localhost"})
        d = profile.to_dict()
        restored = AgentProfile.from_dict(d)
        assert restored.agent_id == profile.agent_id
        assert restored.capabilities == ["trust"]
        assert restored.verify() is True

    def test_capabilities_sorted_in_payload(self):
        identity = AgentIdentity()
        p1 = create_profile(identity, "Bot", ["z", "a", "m"])
        # capabilities in payload should be sorted, so signing is deterministic
        assert p1.verify() is True


class TestDiscoveryRegistry:
    def test_register_valid(self):
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        profile = create_profile(identity, "Bot1")
        assert registry.register(profile) is True
        assert registry.count == 1

    def test_register_unsigned_fails(self):
        registry = DiscoveryRegistry()
        profile = AgentProfile(agent_id="fake", public_key="aa", name="Bad")
        assert registry.register(profile) is False

    def test_register_tampered_fails(self):
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        profile = create_profile(identity, "Bot")
        profile.name = "Tampered"
        assert registry.register(profile) is False

    def test_get(self):
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        profile = create_profile(identity, "FindMe")
        registry.register(profile)
        found = registry.get(identity.agent_id)
        assert found is not None
        assert found.name == "FindMe"

    def test_get_missing(self):
        registry = DiscoveryRegistry()
        assert registry.get("nonexistent") is None

    def test_unregister(self):
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        profile = create_profile(identity, "ByeBot")
        registry.register(profile)
        assert registry.unregister(identity.agent_id) is True
        assert registry.count == 0
        assert registry.unregister(identity.agent_id) is False

    def test_search_by_capability(self):
        registry = DiscoveryRegistry()
        id1, id2 = AgentIdentity(), AgentIdentity()
        registry.register(create_profile(id1, "Coder", ["code-review"]))
        registry.register(create_profile(id2, "Searcher", ["search"]))
        results = registry.search(capability="code-review")
        assert len(results) == 1
        assert results[0].name == "Coder"

    def test_search_by_name(self):
        registry = DiscoveryRegistry()
        id1, id2 = AgentIdentity(), AgentIdentity()
        registry.register(create_profile(id1, "AlphaBot"))
        registry.register(create_profile(id2, "BetaBot"))
        results = registry.search(name_contains="alpha")
        assert len(results) == 1
        assert results[0].name == "AlphaBot"

    def test_search_limit(self):
        registry = DiscoveryRegistry()
        for _ in range(10):
            identity = AgentIdentity()
            registry.register(create_profile(identity, "Bot"))
        results = registry.search(limit=3)
        assert len(results) == 3

    def test_list_capabilities(self):
        registry = DiscoveryRegistry()
        id1, id2, id3 = AgentIdentity(), AgentIdentity(), AgentIdentity()
        registry.register(create_profile(id1, "A", ["trust", "search"]))
        registry.register(create_profile(id2, "B", ["trust"]))
        registry.register(create_profile(id3, "C", ["code"]))
        caps = registry.list_capabilities()
        assert caps["trust"] == 2
        assert caps["search"] == 1
        assert caps["code"] == 1

    def test_update_profile(self):
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        p1 = create_profile(identity, "Bot-v1", ["search"])
        registry.register(p1)

        time.sleep(0.01)
        p2 = create_profile(identity, "Bot-v2", ["search", "trust"])
        registry.register(p2)
        assert registry.get(identity.agent_id).name == "Bot-v2"

    def test_stale_update_rejected(self):
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        p1 = create_profile(identity, "Bot-new")
        registry.register(p1)

        # Create older profile
        p2 = create_profile(identity, "Bot-old")
        p2.updated_at = p1.updated_at - 1
        p2.sign(identity)
        assert registry.register(p2) is False
        assert registry.get(identity.agent_id).name == "Bot-new"

    def test_export_import_json(self):
        registry = DiscoveryRegistry()
        id1, id2 = AgentIdentity(), AgentIdentity()
        registry.register(create_profile(id1, "A", ["trust"]))
        registry.register(create_profile(id2, "B", ["code"]))

        exported = registry.export_json()
        restored = DiscoveryRegistry.from_json(exported)
        assert restored.count == 2
        assert restored.get(id1.agent_id).name == "A"

    def test_mismatched_agent_id_rejected(self):
        """Profile with agent_id not matching public key is rejected."""
        registry = DiscoveryRegistry()
        identity = AgentIdentity()
        profile = create_profile(identity, "Bot")
        profile.agent_id = "fake_id_12345678"
        profile.sign(identity)  # re-sign with fake id
        assert registry.register(profile) is False
