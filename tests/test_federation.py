"""Tests for isnad.federation — Trust Federation Protocol."""

import time
import pytest
from isnad.federation import (
    FederationHub,
    FederationPeer,
    FederationPolicy,
    ConflictStrategy,
)


@pytest.fixture
def hub():
    return FederationHub("network-alpha")


@pytest.fixture
def hub_with_peer(hub):
    hub.register_peer("network-beta", "Beta Network", trust_level=0.8)
    return hub


@pytest.fixture
def two_hubs():
    alpha = FederationHub("alpha")
    beta = FederationHub("beta")
    alpha.register_peer("beta", "Beta", trust_level=0.8)
    beta.register_peer("alpha", "Alpha", trust_level=0.7)
    return alpha, beta


# ── Peer Management ──


class TestPeerManagement:
    def test_register_peer(self, hub):
        peer = hub.register_peer("net-b", "Network B")
        assert peer.peer_id == "net-b"
        assert peer.name == "Network B"
        assert peer.active is True
        assert peer.trust_level == 0.5

    def test_register_peer_custom_policy(self, hub):
        peer = hub.register_peer(
            "net-b", "B", policy=FederationPolicy.FULL, trust_level=0.9
        )
        assert peer.policy == FederationPolicy.FULL
        assert peer.trust_level == 0.9

    def test_cannot_register_self(self, hub):
        with pytest.raises(ValueError, match="Cannot register self"):
            hub.register_peer("network-alpha", "Self")

    def test_cannot_register_duplicate(self, hub):
        hub.register_peer("net-b", "B")
        with pytest.raises(ValueError, match="already registered"):
            hub.register_peer("net-b", "B Again")

    def test_remove_peer(self, hub_with_peer):
        assert hub_with_peer.remove_peer("network-beta") is True
        peer = hub_with_peer.get_peer("network-beta")
        assert peer.active is False

    def test_remove_unknown_peer(self, hub):
        assert hub.remove_peer("unknown") is False

    def test_list_peers_active_only(self, hub):
        hub.register_peer("a", "A")
        hub.register_peer("b", "B")
        hub.remove_peer("b")
        active = hub.list_peers(active_only=True)
        assert len(active) == 1
        assert active[0].peer_id == "a"

    def test_list_peers_all(self, hub):
        hub.register_peer("a", "A")
        hub.register_peer("b", "B")
        hub.remove_peer("b")
        assert len(hub.list_peers(active_only=False)) == 2

    def test_update_peer_trust(self, hub_with_peer):
        hub_with_peer.update_peer_trust("network-beta", 0.95)
        assert hub_with_peer.get_peer("network-beta").trust_level == 0.95

    def test_update_peer_trust_clamped(self, hub_with_peer):
        hub_with_peer.update_peer_trust("network-beta", 1.5)
        assert hub_with_peer.get_peer("network-beta").trust_level == 1.0
        hub_with_peer.update_peer_trust("network-beta", -0.5)
        assert hub_with_peer.get_peer("network-beta").trust_level == 0.0

    def test_update_unknown_peer(self, hub):
        with pytest.raises(KeyError):
            hub.update_peer_trust("nope", 0.5)


# ── Attestation Exchange ──


class TestAttestationExchange:
    def test_add_local_attestation(self, hub):
        att = hub.add_local_attestation("agent-1", "agent-2", "reliability", True, 0.85)
        assert att["issuer"] == "agent-1"
        assert att["trust_score"] == 0.85
        assert att["network"] == "network-alpha"

    def test_receive_attestation(self, hub_with_peer):
        result = hub_with_peer.receive_attestation(
            peer_id="network-beta",
            original_issuer="agent-x",
            subject="agent-y",
            claim="quality",
            value="high",
            trust_score=0.9,
            original_timestamp=time.time() - 100,
        )
        assert result is not None
        assert result.peer_id == "network-beta"
        # Score decayed: 0.9 * (1 - 0.15*1) * 0.8 = 0.9 * 0.85 * 0.8 = 0.612
        assert 0.61 < result.trust_score < 0.62

    def test_receive_from_unknown_peer(self, hub):
        result = hub.receive_attestation(
            "unknown", "a", "b", "c", "d", 0.5, time.time()
        )
        assert result is None

    def test_receive_from_inactive_peer(self, hub_with_peer):
        hub_with_peer.remove_peer("network-beta")
        result = hub_with_peer.receive_attestation(
            "network-beta", "a", "b", "c", "d", 0.5, time.time()
        )
        assert result is None

    def test_chain_too_long(self, hub_with_peer):
        result = hub_with_peer.receive_attestation(
            "network-beta", "a", "b", "c", "d", 0.5, time.time(),
            chain_length=4,  # max is 3
        )
        assert result is None

    def test_trust_decay_increases_with_hops(self, hub_with_peer):
        r1 = hub_with_peer.receive_attestation(
            "network-beta", "a", "b", "c", "d", 0.9, time.time(), chain_length=1
        )
        r2 = hub_with_peer.receive_attestation(
            "network-beta", "a2", "b2", "c2", "d", 0.9, time.time(), chain_length=2
        )
        r3 = hub_with_peer.receive_attestation(
            "network-beta", "a3", "b3", "c3", "d", 0.9, time.time(), chain_length=3
        )
        assert r1.trust_score > r2.trust_score > r3.trust_score

    def test_peer_counters_updated(self, hub_with_peer):
        hub_with_peer.receive_attestation(
            "network-beta", "a", "b", "c", "d", 0.5, time.time()
        )
        peer = hub_with_peer.get_peer("network-beta")
        assert peer.attestations_received == 1
        assert peer.last_sync is not None


# ── Sharing Policies ──


class TestSharingPolicies:
    def test_full_sharing(self, hub):
        hub.register_peer("p", "P", policy=FederationPolicy.FULL)
        hub.add_local_attestation("a", "b", "c", True, 0.1)
        hub.add_local_attestation("a", "b2", "c", True, 0.9)
        shared = hub.get_attestations_to_share("p")
        assert len(shared) == 2

    def test_selective_sharing(self, hub):
        hub.register_peer("p", "P", policy=FederationPolicy.SELECTIVE, share_threshold=0.5)
        hub.add_local_attestation("a", "low", "c", True, 0.2)
        hub.add_local_attestation("a", "high", "c", True, 0.8)
        shared = hub.get_attestations_to_share("p")
        assert len(shared) == 1
        assert shared[0]["subject"] == "high"

    def test_summary_sharing(self, hub):
        hub.register_peer("p", "P", policy=FederationPolicy.SUMMARY)
        hub.add_local_attestation("a", "subj1", "c", True, 0.6)
        hub.add_local_attestation("b", "subj1", "c", True, 0.8)
        hub.add_local_attestation("a", "subj2", "c", True, 0.5)
        shared = hub.get_attestations_to_share("p")
        assert len(shared) == 2
        s1 = next(s for s in shared if s["subject"] == "subj1")
        assert s1["aggregate_score"] == 0.7
        assert s1["attestation_count"] == 2

    def test_no_sharing(self, hub):
        hub.register_peer("p", "P", policy=FederationPolicy.NONE)
        hub.add_local_attestation("a", "b", "c", True, 0.9)
        assert hub.get_attestations_to_share("p") == []

    def test_share_with_inactive_peer(self, hub):
        hub.register_peer("p", "P", policy=FederationPolicy.FULL)
        hub.add_local_attestation("a", "b", "c", True, 0.9)
        hub.remove_peer("p")
        assert hub.get_attestations_to_share("p") == []


# ── Trust Queries ──


class TestTrustQueries:
    def test_federated_trust_local_only(self, hub):
        hub.add_local_attestation("a", "target", "q", True, 0.8)
        hub.add_local_attestation("b", "target", "q", True, 0.6)
        result = hub.get_federated_trust("target")
        assert result["local_score"] == 0.7
        assert result["local_attestations"] == 2
        assert result["federated_attestations"] == 0
        assert result["global_score"] == 0.7

    def test_federated_trust_mixed(self, hub_with_peer):
        hub_with_peer.add_local_attestation("a", "target", "q", True, 0.8)
        hub_with_peer.receive_attestation(
            "network-beta", "x", "target", "q", True, 0.9, time.time()
        )
        result = hub_with_peer.get_federated_trust("target")
        assert result["local_score"] == 0.8
        assert result["local_attestations"] == 1
        assert result["federated_attestations"] == 1
        assert result["total_attestations"] == 2
        assert result["peer_scores"]["network-beta"] is not None

    def test_federated_trust_unknown_subject(self, hub):
        result = hub.get_federated_trust("nobody")
        assert result["local_score"] is None
        assert result["global_score"] is None
        assert result["total_attestations"] == 0


# ── Conflict Resolution ──


class TestConflictResolution:
    def test_local_priority_rejects_incoming(self):
        hub = FederationHub("net", conflict_strategy=ConflictStrategy.LOCAL_PRIORITY)
        hub.register_peer("p", "P", trust_level=0.9)
        hub.add_local_attestation("a", "subj", "status", "good", 0.8)
        result = hub.receive_attestation(
            "p", "x", "subj", "status", "bad", 0.9, time.time()
        )
        assert result is None
        conflicts = hub.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["winner"] == "local"

    def test_most_recent_strategy(self):
        hub = FederationHub("net", conflict_strategy=ConflictStrategy.MOST_RECENT)
        hub.register_peer("p", "P", trust_level=0.9)
        now = time.time()
        hub.receive_attestation("p", "x", "subj", "status", "old", 0.8, now - 100)
        result = hub.receive_attestation("p", "y", "subj", "status", "new", 0.7, now)
        assert result is not None  # Newer wins

    def test_highest_trust_strategy(self):
        hub = FederationHub("net", conflict_strategy=ConflictStrategy.HIGHEST_TRUST)
        hub.register_peer("p1", "P1", trust_level=1.0)
        hub.register_peer("p2", "P2", trust_level=1.0)
        now = time.time()
        hub.receive_attestation("p1", "a", "subj", "rank", "low", 0.3, now)
        result = hub.receive_attestation("p2", "b", "subj", "rank", "high", 0.9, now)
        assert result is not None

    def test_peer_priority_accepts_over_local(self):
        hub = FederationHub("net", conflict_strategy=ConflictStrategy.PEER_PRIORITY)
        hub.register_peer("p", "P", trust_level=0.9)
        hub.add_local_attestation("a", "subj", "status", "local-val", 0.8)
        result = hub.receive_attestation(
            "p", "x", "subj", "status", "peer-val", 0.5, time.time()
        )
        assert result is not None

    def test_consensus_strategy(self):
        hub = FederationHub("net", conflict_strategy=ConflictStrategy.CONSENSUS)
        hub.register_peer("p1", "P1", trust_level=1.0)
        hub.register_peer("p2", "P2", trust_level=1.0)
        hub.register_peer("p3", "P3", trust_level=1.0)
        now = time.time()
        # Two say "good", one says "bad"
        hub.receive_attestation("p1", "a1", "subj", "quality", "good", 0.8, now)
        hub.receive_attestation("p2", "a2", "subj", "quality", "good", 0.7, now)
        result = hub.receive_attestation("p3", "a3", "subj", "quality", "bad", 0.9, now)
        # "good" has 2 votes, "bad" has 1 → bad loses
        assert result is None


# ── Network Health ──


class TestNetworkHealth:
    def test_health_empty(self, hub):
        health = hub.get_network_health()
        assert health["network_id"] == "network-alpha"
        assert health["total_peers"] == 0
        assert health["active_peers"] == 0

    def test_health_with_data(self, hub_with_peer):
        hub_with_peer.add_local_attestation("a", "b", "c", True, 0.8)
        hub_with_peer.receive_attestation(
            "network-beta", "x", "y", "z", True, 0.7, time.time()
        )
        health = hub_with_peer.get_network_health()
        assert health["active_peers"] == 1
        assert health["local_attestations"] == 1
        assert health["received_attestations"] == 1
        assert health["avg_peer_trust"] == 0.8


# ── Integration: Two-Hub Exchange ──


class TestTwoHubExchange:
    def test_bidirectional_sharing(self, two_hubs):
        alpha, beta = two_hubs
        
        # Alpha creates attestation
        alpha.add_local_attestation("agent-a", "agent-c", "skill", "python", 0.9)
        
        # Alpha shares with beta
        to_share = alpha.get_attestations_to_share("beta")
        assert len(to_share) == 1
        
        # Beta receives
        att = to_share[0]
        result = beta.receive_attestation(
            "alpha", att["issuer"], att["subject"], att["claim"],
            att["value"], att["trust_score"], att["timestamp"]
        )
        assert result is not None
        
        # Beta can now query federated trust
        trust = beta.get_federated_trust("agent-c")
        assert trust["federated_attestations"] == 1
        assert trust["peer_scores"]["alpha"] is not None

    def test_chain_forwarding(self, two_hubs):
        alpha, beta = two_hubs
        gamma = FederationHub("gamma")
        gamma.register_peer("beta", "Beta", trust_level=0.6)
        beta.register_peer("gamma", "Gamma", trust_level=0.7)
        
        # Alpha → Beta → Gamma (chain length 2)
        alpha.add_local_attestation("a", "target", "q", True, 0.9)
        shared = alpha.get_attestations_to_share("beta")
        
        # Beta receives from alpha
        att = shared[0]
        beta.receive_attestation(
            "alpha", att["issuer"], att["subject"], att["claim"],
            att["value"], att["trust_score"], att["timestamp"], chain_length=1
        )
        
        # Gamma receives from beta (chain_length=2)
        result = gamma.receive_attestation(
            "beta", att["issuer"], att["subject"], att["claim"],
            att["value"], att["trust_score"], att["timestamp"], chain_length=2
        )
        assert result is not None
        # Score should be significantly decayed
        assert result.trust_score < 0.5
