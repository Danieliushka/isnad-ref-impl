"""Tests for isnad.events — Trust Event Notification System."""
import time
import json
import pytest
from unittest.mock import MagicMock, patch

from isnad.events import Event, EventBus, EventType, Subscription, get_event_bus


class TestEvent:
    def test_create_event(self):
        e = Event(event_type="attestation.created", data={"from": "a", "to": "b"})
        assert e.event_type == "attestation.created"
        assert e.data == {"from": "a", "to": "b"}
        assert e.timestamp > 0
        assert len(e.event_id) == 16

    def test_event_id_deterministic(self):
        """Same type + timestamp + data = same ID."""
        ts = 1700000000.0
        e1 = Event(event_type="test", data={"x": 1}, timestamp=ts)
        e2 = Event(event_type="test", data={"x": 1}, timestamp=ts)
        assert e1.event_id == e2.event_id

    def test_event_id_unique(self):
        e1 = Event(event_type="test", data={"x": 1})
        time.sleep(0.001)
        e2 = Event(event_type="test", data={"x": 2})
        assert e1.event_id != e2.event_id

    def test_to_dict_roundtrip(self):
        e = Event(event_type="score.updated", data={"score": 0.95}, source_agent="agent:abc")
        d = e.to_dict()
        e2 = Event.from_dict(d)
        assert e2.event_type == e.event_type
        assert e2.data == e.data
        assert e2.source_agent == e.source_agent
        assert e2.event_id == e.event_id

    def test_event_types_enum(self):
        assert EventType.ATTESTATION_CREATED == "attestation.created"
        assert EventType.SCORE_UPDATED == "score.updated"


class TestSubscription:
    def test_exact_match(self):
        s = Subscription(subscriber_id="s1", patterns=["attestation.created"])
        assert s.matches("attestation.created")
        assert not s.matches("attestation.revoked")

    def test_glob_match(self):
        s = Subscription(subscriber_id="s1", patterns=["attestation.*"])
        assert s.matches("attestation.created")
        assert s.matches("attestation.revoked")
        assert not s.matches("score.updated")

    def test_multi_pattern(self):
        s = Subscription(subscriber_id="s1", patterns=["attestation.*", "score.*"])
        assert s.matches("attestation.created")
        assert s.matches("score.updated")
        assert not s.matches("agent.registered")

    def test_wildcard_all(self):
        s = Subscription(subscriber_id="s1", patterns=["*"])
        assert s.matches("anything")
        assert s.matches("attestation.created")


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []
        bus.subscribe("attestation.created", callback=lambda e: received.append(e))
        bus.emit("attestation.created", {"from": "a", "to": "b"})
        assert len(received) == 1
        assert received[0].data == {"from": "a", "to": "b"}

    def test_pattern_filtering(self):
        bus = EventBus()
        att_events = []
        all_events = []
        bus.subscribe("attestation.*", callback=lambda e: att_events.append(e))
        bus.subscribe("*", callback=lambda e: all_events.append(e))

        bus.emit("attestation.created", {"x": 1})
        bus.emit("score.updated", {"x": 2})

        assert len(att_events) == 1
        assert len(all_events) == 2

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        sid = bus.subscribe("*", callback=lambda e: received.append(e))
        bus.emit("test", {})
        assert len(received) == 1

        bus.unsubscribe(sid)
        bus.emit("test", {})
        assert len(received) == 1  # no new events

    def test_unsubscribe_nonexistent(self):
        bus = EventBus()
        assert not bus.unsubscribe("nonexistent")

    def test_history(self):
        bus = EventBus()
        bus.emit("a", {"n": 1})
        bus.emit("b", {"n": 2})
        bus.emit("a", {"n": 3})

        assert len(bus.history()) == 3
        assert len(bus.history(event_type="a")) == 2
        assert len(bus.history(event_type="b")) == 1

    def test_history_limit(self):
        bus = EventBus()
        for i in range(10):
            bus.emit("test", {"i": i})
        assert len(bus.history(limit=3)) == 3

    def test_history_since(self):
        bus = EventBus()
        bus.emit("old", {})
        cutoff = time.time()
        time.sleep(0.01)
        bus.emit("new", {})
        recent = bus.history(since=cutoff)
        assert len(recent) == 1
        assert recent[0].event_type == "new"

    def test_history_max_cap(self):
        bus = EventBus(max_history=5)
        for i in range(10):
            bus.emit("test", {"i": i})
        assert len(bus.history()) == 5
        assert bus.history()[0].data["i"] == 5  # oldest kept

    def test_emit_returns_event(self):
        bus = EventBus()
        e = bus.emit("test", {"k": "v"}, source_agent="agent:x")
        assert isinstance(e, Event)
        assert e.source_agent == "agent:x"

    def test_callback_error_doesnt_crash(self):
        bus = EventBus()
        ok_received = []

        def bad_callback(e):
            raise ValueError("boom")

        bus.subscribe("test", callback=bad_callback)
        bus.subscribe("test", callback=lambda e: ok_received.append(e))

        bus.emit("test", {})
        assert len(ok_received) == 1  # second subscriber still gets it

    def test_subscriber_count(self):
        bus = EventBus()
        assert bus.subscriber_count == 0
        bus.subscribe("a")
        bus.subscribe("b")
        assert bus.subscriber_count == 2

    def test_list_subscriptions(self):
        bus = EventBus()
        bus.subscribe("attestation.*", subscriber_id="my-sub")
        bus.add_webhook("https://example.com/hook", ["score.*"], subscriber_id="my-wh")

        subs = bus.list_subscriptions()
        assert len(subs) == 2
        ids = {s["subscriber_id"] for s in subs}
        assert "my-sub" in ids
        assert "my-wh" in ids

    def test_webhook_dispatch(self):
        bus = EventBus()
        bus.add_webhook("https://example.com/hook", ["test.*"])

        with patch("urllib.request.urlopen") as mock_urlopen:
            bus.emit("test.event", {"key": "value"})
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data.decode())
            assert body["event_type"] == "test.event"
            assert body["data"] == {"key": "value"}

    def test_webhook_failure_silent(self):
        bus = EventBus()
        bus.add_webhook("https://bad-url.invalid/hook", ["test"])

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            # Should not raise
            bus.emit("test", {"x": 1})

    def test_custom_subscriber_id(self):
        bus = EventBus()
        sid = bus.subscribe("test", subscriber_id="my-custom-id")
        assert sid == "my-custom-id"


class TestGlobalBus:
    def test_singleton(self):
        import isnad.events as mod
        mod._global_bus = None  # reset
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2
        mod._global_bus = None  # cleanup


class TestIntegration:
    """End-to-end: simulate trust events across a multi-agent system."""

    def test_attestation_flow(self):
        bus = EventBus()
        log = []

        # Subscriber: trust monitor
        bus.subscribe("attestation.*", callback=lambda e: log.append(("att", e)))
        bus.subscribe("score.*", callback=lambda e: log.append(("score", e)))

        # Agent A attests Agent B
        bus.emit(EventType.ATTESTATION_CREATED, {
            "from": "agent:aaa",
            "to": "agent:bbb",
            "claim": "qa-capability",
        }, source_agent="agent:aaa")

        # Trust score recalculated
        bus.emit(EventType.SCORE_UPDATED, {
            "agent_id": "agent:bbb",
            "old_score": 0.5,
            "new_score": 0.65,
        })

        # Later: attestation revoked
        bus.emit(EventType.ATTESTATION_REVOKED, {
            "from": "agent:aaa",
            "to": "agent:bbb",
            "reason": "capability no longer verified",
        }, source_agent="agent:aaa")

        assert len(log) == 3
        assert log[0][0] == "att"  # attestation.created
        assert log[1][0] == "score"  # score.updated
        assert log[2][0] == "att"  # attestation.revoked
        assert log[2][1].data["reason"] == "capability no longer verified"


class TestCoreIntegration:
    """Test EventBus integration with core TrustChain and RevocationRegistry."""

    def test_trustchain_emits_on_add(self):
        from isnad.core import AgentIdentity, Attestation, TrustChain
        bus = EventBus()
        events = []
        bus.subscribe("attestation.created", callback=lambda e: events.append(e))

        chain = TrustChain()
        alice = AgentIdentity()
        bob = AgentIdentity()
        att = Attestation(subject=bob.agent_id, witness=alice.agent_id, task="qa")
        att.sign(alice)
        chain.add(att, event_bus=bus)

        assert len(events) == 1
        assert events[0].data["subject"] == bob.agent_id
        assert events[0].data["witness"] == alice.agent_id
        assert events[0].data["task"] == "qa"
        assert events[0].source_agent == alice.agent_id

    def test_trustchain_no_event_on_invalid(self):
        from isnad.core import Attestation, TrustChain
        bus = EventBus()
        events = []
        bus.subscribe("attestation.*", callback=lambda e: events.append(e))

        chain = TrustChain()
        # Create an attestation with bad signature
        att = Attestation(
            witness="agent:fake",
            subject="agent:target",
            task="test",
            signature="bad",
            witness_pubkey="bad",
        )
        result = chain.add(att, event_bus=bus)
        assert result is False
        assert len(events) == 0

    def test_revocation_emits_event(self):
        from isnad.core import AgentIdentity, RevocationRegistry, RevocationEntry
        bus = EventBus()
        events = []
        bus.subscribe("attestation.revoked", callback=lambda e: events.append(e))

        reg = RevocationRegistry()
        alice = AgentIdentity()
        entry = RevocationEntry(
            target_id="att:12345",
            revoked_by=alice.agent_id,
            reason="no longer valid",
        )
        reg.revoke(entry, event_bus=bus)

        assert len(events) == 1
        assert events[0].data["target_id"] == "att:12345"
        assert events[0].data["reason"] == "no longer valid"

    def test_backward_compatible_no_bus(self):
        """Existing code without event_bus still works."""
        from isnad.core import AgentIdentity, Attestation, TrustChain, RevocationRegistry, RevocationEntry
        chain = TrustChain()
        alice = AgentIdentity()
        bob = AgentIdentity()
        att = Attestation(subject=bob.agent_id, witness=alice.agent_id, task="test")
        att.sign(alice)
        assert chain.add(att) is True  # no event_bus, no crash

        reg = RevocationRegistry()
        entry = RevocationEntry(target_id="x", revoked_by=alice.agent_id, reason="test")
        reg.revoke(entry)  # no event_bus, no crash
