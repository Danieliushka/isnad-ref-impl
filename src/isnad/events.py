#!/usr/bin/env python3
"""
isnad.events — Trust Event Notification System

Subscribe to trust events (attestations, revocations, score changes)
and get notified via callbacks or webhooks. Enables real-time
integrations between agent systems.

Usage:
    bus = EventBus()
    bus.subscribe("attestation.created", my_handler)
    bus.emit("attestation.created", {"from": "agent:abc", "to": "agent:def"})

Webhook integration:
    bus.add_webhook("https://example.com/hook", ["attestation.*"])
"""

import fnmatch
import json
import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
from enum import Enum


class EventType(str, Enum):
    """Standard trust event types."""
    ATTESTATION_CREATED = "attestation.created"
    ATTESTATION_REVOKED = "attestation.revoked"
    SCORE_UPDATED = "score.updated"
    AGENT_REGISTERED = "agent.registered"
    AGENT_UNREGISTERED = "agent.unregistered"
    DELEGATION_GRANTED = "delegation.granted"
    DELEGATION_REVOKED = "delegation.revoked"
    POLICY_VIOLATION = "policy.violation"


@dataclass
class Event:
    """A trust event with metadata."""
    event_type: str
    data: dict = field(default_factory=dict)
    timestamp: float = 0.0
    source_agent: str = ""
    event_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.event_id:
            import hashlib
            payload = f"{self.event_type}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
            self.event_id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Subscription:
    """A subscription to one or more event patterns."""
    subscriber_id: str
    patterns: list[str]  # glob patterns like "attestation.*"
    callback: Optional[Callable[[Event], None]] = None
    webhook_url: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    active: bool = True

    def matches(self, event_type: str) -> bool:
        """Check if this subscription matches a given event type."""
        return any(fnmatch.fnmatch(event_type, p) for p in self.patterns)


class EventBus:
    """
    In-process event bus for trust events.

    Supports both callback-based and webhook-based subscriptions.
    Thread-safe. Events are dispatched synchronously by default,
    or async with dispatch_async=True.
    """

    def __init__(self, max_history: int = 1000):
        self._subscriptions: dict[str, Subscription] = {}  # sub_id -> Subscription
        self._history: list[Event] = []
        self._max_history = max_history
        self._lock = threading.Lock()
        self._webhook_timeout = 5.0

    def subscribe(
        self,
        patterns: str | list[str],
        callback: Optional[Callable[[Event], None]] = None,
        subscriber_id: Optional[str] = None,
    ) -> str:
        """
        Subscribe to events matching glob pattern(s).

        Args:
            patterns: Event type pattern(s), e.g. "attestation.*" or ["score.*", "agent.*"]
            callback: Function called with Event when matched
            subscriber_id: Optional ID (auto-generated if not provided)

        Returns:
            Subscription ID
        """
        if isinstance(patterns, str):
            patterns = [patterns]

        if not subscriber_id:
            import hashlib
            subscriber_id = f"sub:{hashlib.sha256(f'{time.time()}'.encode()).hexdigest()[:8]}"

        sub = Subscription(
            subscriber_id=subscriber_id,
            patterns=patterns,
            callback=callback,
        )

        with self._lock:
            self._subscriptions[subscriber_id] = sub

        return subscriber_id

    def add_webhook(
        self,
        url: str,
        patterns: str | list[str],
        subscriber_id: Optional[str] = None,
    ) -> str:
        """
        Add a webhook subscription — HTTP POST on matching events.

        Args:
            url: Webhook endpoint URL
            patterns: Event type pattern(s)
            subscriber_id: Optional ID

        Returns:
            Subscription ID
        """
        if isinstance(patterns, str):
            patterns = [patterns]

        if not subscriber_id:
            import hashlib
            subscriber_id = f"wh:{hashlib.sha256(url.encode()).hexdigest()[:8]}"

        sub = Subscription(
            subscriber_id=subscriber_id,
            patterns=patterns,
            webhook_url=url,
        )

        with self._lock:
            self._subscriptions[subscriber_id] = sub

        return subscriber_id

    def unsubscribe(self, subscriber_id: str) -> bool:
        """Remove a subscription."""
        with self._lock:
            if subscriber_id in self._subscriptions:
                del self._subscriptions[subscriber_id]
                return True
            return False

    def emit(
        self,
        event_type: str,
        data: Optional[dict] = None,
        source_agent: str = "",
    ) -> Event:
        """
        Emit an event. Dispatches to all matching subscribers.

        Args:
            event_type: Event type string (e.g. "attestation.created")
            data: Event payload
            source_agent: Agent ID that triggered the event

        Returns:
            The emitted Event
        """
        event = Event(
            event_type=event_type,
            data=data or {},
            source_agent=source_agent,
        )

        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            subs = [s for s in self._subscriptions.values() if s.active and s.matches(event_type)]

        for sub in subs:
            self._dispatch(sub, event)

        return event

    def _dispatch(self, sub: Subscription, event: Event):
        """Dispatch event to a single subscriber."""
        if sub.callback:
            try:
                sub.callback(event)
            except Exception:
                pass  # don't let subscriber errors crash the bus

        if sub.webhook_url:
            self._send_webhook(sub.webhook_url, event)

    def _send_webhook(self, url: str, event: Event):
        """Send event via HTTP POST (best-effort)."""
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=json.dumps(event.to_dict()).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=self._webhook_timeout)
        except Exception:
            pass  # best-effort delivery

    def history(
        self,
        event_type: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 50,
    ) -> list[Event]:
        """Query event history with optional filters."""
        with self._lock:
            events = list(self._history)

        if event_type:
            events = [e for e in events if fnmatch.fnmatch(e.event_type, event_type)]
        if since:
            events = [e for e in events if e.timestamp >= since]

        return events[-limit:]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    def list_subscriptions(self) -> list[dict]:
        """List all active subscriptions (without callbacks)."""
        with self._lock:
            return [
                {
                    "subscriber_id": s.subscriber_id,
                    "patterns": s.patterns,
                    "webhook_url": s.webhook_url,
                    "active": s.active,
                    "created_at": s.created_at,
                }
                for s in self._subscriptions.values()
            ]


# ── Convenience: global bus ──

_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus singleton."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
