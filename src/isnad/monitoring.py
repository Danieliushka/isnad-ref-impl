"""
isnad.monitoring — Trust network health monitoring & metrics.

Provides real-time observability into trust network operations:
- AttestationMetrics: counters, rates, latency tracking
- TrustHealthMonitor: network health scoring, anomaly detection
- MetricsExporter: Prometheus-compatible metrics export

Usage:
    monitor = TrustHealthMonitor()
    monitor.record_attestation(agent_id, target_id, score=0.85, latency_ms=12)
    monitor.record_revocation(agent_id, target_id, reason="misbehavior")
    
    health = monitor.health_report()
    # {'score': 0.92, 'attestations_1h': 47, 'anomalies': [], ...}
    
    exporter = MetricsExporter(monitor)
    print(exporter.prometheus())  # Prometheus text format
"""

from __future__ import annotations

import time
import threading
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable


class EventType(Enum):
    ATTESTATION = "attestation"
    REVOCATION = "revocation"
    DELEGATION = "delegation"
    VERIFICATION = "verification"
    FEDERATION_SYNC = "federation_sync"
    HANDSHAKE = "handshake"


@dataclass
class MetricEvent:
    """A single recorded metric event."""
    event_type: EventType
    timestamp: float
    agent_id: str
    target_id: Optional[str] = None
    score: Optional[float] = None
    latency_ms: Optional[float] = None
    success: bool = True
    metadata: dict = field(default_factory=dict)


class SlidingWindow:
    """Thread-safe sliding window for time-series metrics."""

    def __init__(self, window_seconds: float = 3600):
        self._window = window_seconds
        self._events: list[MetricEvent] = []
        self._lock = threading.Lock()

    def add(self, event: MetricEvent) -> None:
        with self._lock:
            self._events.append(event)
            self._prune()

    def _prune(self) -> None:
        cutoff = time.time() - self._window
        self._events = [e for e in self._events if e.timestamp >= cutoff]

    def events(self, event_type: Optional[EventType] = None) -> list[MetricEvent]:
        with self._lock:
            self._prune()
            if event_type:
                return [e for e in self._events if e.event_type == event_type]
            return list(self._events)

    def count(self, event_type: Optional[EventType] = None) -> int:
        return len(self.events(event_type))

    def rate_per_minute(self, event_type: Optional[EventType] = None) -> float:
        events = self.events(event_type)
        if not events:
            return 0.0
        span = time.time() - events[0].timestamp
        if span < 1:
            return float(len(events))
        return len(events) / (span / 60)

    @property
    def window_seconds(self) -> float:
        return self._window


@dataclass
class AnomalyAlert:
    """Detected anomaly in trust network."""
    alert_type: str
    severity: str  # "low", "medium", "high", "critical"
    message: str
    timestamp: float
    agent_id: Optional[str] = None
    details: dict = field(default_factory=dict)


class AnomalyDetector:
    """Detects anomalies in trust network behavior."""

    def __init__(
        self,
        revocation_spike_threshold: float = 3.0,
        low_score_threshold: float = 0.3,
        high_failure_rate: float = 0.25,
        latency_spike_factor: float = 5.0,
    ):
        self.revocation_spike_threshold = revocation_spike_threshold
        self.low_score_threshold = low_score_threshold
        self.high_failure_rate = high_failure_rate
        self.latency_spike_factor = latency_spike_factor

    def analyze(self, window: SlidingWindow) -> list[AnomalyAlert]:
        alerts: list[AnomalyAlert] = []
        now = time.time()

        # 1. Revocation spike detection
        revocations = window.events(EventType.REVOCATION)
        attestations = window.events(EventType.ATTESTATION)
        if attestations and revocations:
            ratio = len(revocations) / max(len(attestations), 1)
            if ratio > self.revocation_spike_threshold:
                alerts.append(AnomalyAlert(
                    alert_type="revocation_spike",
                    severity="high",
                    message=f"Revocation rate {ratio:.1f}x higher than attestation rate",
                    timestamp=now,
                    details={"ratio": ratio, "revocations": len(revocations), "attestations": len(attestations)},
                ))

        # 2. Low trust scores
        scored = [e for e in attestations if e.score is not None]
        if scored:
            avg_score = statistics.mean(e.score for e in scored)
            if avg_score < self.low_score_threshold:
                alerts.append(AnomalyAlert(
                    alert_type="low_avg_trust",
                    severity="medium",
                    message=f"Average trust score critically low: {avg_score:.2f}",
                    timestamp=now,
                    details={"avg_score": avg_score, "sample_size": len(scored)},
                ))

        # 3. High failure rate
        all_events = window.events()
        if len(all_events) >= 10:
            failures = sum(1 for e in all_events if not e.success)
            fail_rate = failures / len(all_events)
            if fail_rate > self.high_failure_rate:
                alerts.append(AnomalyAlert(
                    alert_type="high_failure_rate",
                    severity="high",
                    message=f"Operation failure rate: {fail_rate:.0%}",
                    timestamp=now,
                    details={"fail_rate": fail_rate, "failures": failures, "total": len(all_events)},
                ))

        # 4. Latency spikes
        timed = [e for e in all_events if e.latency_ms is not None]
        if len(timed) >= 5:
            latencies = [e.latency_ms for e in timed]
            median = statistics.median(latencies)
            if median > 0:
                recent = timed[-5:]
                recent_median = statistics.median(e.latency_ms for e in recent)
                if recent_median > median * self.latency_spike_factor:
                    alerts.append(AnomalyAlert(
                        alert_type="latency_spike",
                        severity="medium",
                        message=f"Latency spike detected: {recent_median:.0f}ms vs {median:.0f}ms baseline",
                        timestamp=now,
                        details={"recent_median_ms": recent_median, "baseline_median_ms": median},
                    ))

        # 5. Per-agent anomalies: single agent revoking many
        agent_revocations: dict[str, int] = {}
        for e in revocations:
            agent_revocations[e.agent_id] = agent_revocations.get(e.agent_id, 0) + 1
        for agent, count in agent_revocations.items():
            if count >= 5:
                alerts.append(AnomalyAlert(
                    alert_type="mass_revocation",
                    severity="critical",
                    message=f"Agent {agent} issued {count} revocations in window",
                    timestamp=now,
                    agent_id=agent,
                    details={"count": count},
                ))

        return alerts


class TrustHealthMonitor:
    """Central monitoring hub for trust network health."""

    def __init__(
        self,
        window_seconds: float = 3600,
        anomaly_detector: Optional[AnomalyDetector] = None,
    ):
        self._window = SlidingWindow(window_seconds)
        self._detector = anomaly_detector or AnomalyDetector()
        self._alert_callbacks: list[Callable[[AnomalyAlert], None]] = []
        self._total_events = 0
        self._lock = threading.Lock()

    def record_attestation(
        self,
        agent_id: str,
        target_id: str,
        score: float = 1.0,
        latency_ms: Optional[float] = None,
        success: bool = True,
        **metadata,
    ) -> None:
        self._record(EventType.ATTESTATION, agent_id, target_id, score, latency_ms, success, metadata)

    def record_revocation(
        self,
        agent_id: str,
        target_id: str,
        reason: str = "",
        latency_ms: Optional[float] = None,
        success: bool = True,
        **metadata,
    ) -> None:
        metadata["reason"] = reason
        self._record(EventType.REVOCATION, agent_id, target_id, None, latency_ms, success, metadata)

    def record_delegation(
        self,
        agent_id: str,
        delegate_id: str,
        scope: str = "*",
        latency_ms: Optional[float] = None,
        success: bool = True,
        **metadata,
    ) -> None:
        metadata["scope"] = scope
        self._record(EventType.DELEGATION, agent_id, delegate_id, None, latency_ms, success, metadata)

    def record_verification(
        self,
        agent_id: str,
        target_id: str,
        valid: bool = True,
        latency_ms: Optional[float] = None,
        **metadata,
    ) -> None:
        self._record(EventType.VERIFICATION, agent_id, target_id, None, latency_ms, valid, metadata)

    def record_federation_sync(
        self,
        agent_id: str,
        peer_network: str,
        records_synced: int = 0,
        latency_ms: Optional[float] = None,
        success: bool = True,
        **metadata,
    ) -> None:
        metadata.update(peer_network=peer_network, records_synced=records_synced)
        self._record(EventType.FEDERATION_SYNC, agent_id, None, None, latency_ms, success, metadata)

    def record_handshake(
        self,
        agent_id: str,
        target_id: str,
        latency_ms: Optional[float] = None,
        success: bool = True,
        **metadata,
    ) -> None:
        self._record(EventType.HANDSHAKE, agent_id, target_id, None, latency_ms, success, metadata)

    def _record(
        self,
        event_type: EventType,
        agent_id: str,
        target_id: Optional[str],
        score: Optional[float],
        latency_ms: Optional[float],
        success: bool,
        metadata: dict,
    ) -> None:
        event = MetricEvent(
            event_type=event_type,
            timestamp=time.time(),
            agent_id=agent_id,
            target_id=target_id,
            score=score,
            latency_ms=latency_ms,
            success=success,
            metadata=metadata,
        )
        self._window.add(event)
        with self._lock:
            self._total_events += 1

        # Check for anomalies
        alerts = self._detector.analyze(self._window)
        for alert in alerts:
            for cb in self._alert_callbacks:
                cb(alert)

    def on_alert(self, callback: Callable[[AnomalyAlert], None]) -> None:
        """Register an alert callback."""
        self._alert_callbacks.append(callback)

    def health_report(self) -> dict:
        """Generate a health report for the trust network."""
        all_events = self._window.events()
        attestations = self._window.events(EventType.ATTESTATION)
        revocations = self._window.events(EventType.REVOCATION)
        verifications = self._window.events(EventType.VERIFICATION)
        anomalies = self._detector.analyze(self._window)

        # Health score: 1.0 = perfect, 0.0 = critical
        score = 1.0
        if all_events:
            fail_rate = sum(1 for e in all_events if not e.success) / len(all_events)
            score -= fail_rate * 0.5

        if attestations and revocations:
            rev_ratio = len(revocations) / max(len(attestations), 1)
            score -= min(rev_ratio * 0.1, 0.3)

        for a in anomalies:
            penalty = {"low": 0.02, "medium": 0.05, "high": 0.1, "critical": 0.2}
            score -= penalty.get(a.severity, 0.05)

        score = max(0.0, min(1.0, score))

        # Latency stats
        timed = [e for e in all_events if e.latency_ms is not None]
        latency_stats = {}
        if timed:
            latencies = [e.latency_ms for e in timed]
            latency_stats = {
                "p50_ms": statistics.median(latencies),
                "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies),
                "mean_ms": statistics.mean(latencies),
            }

        # Active agents
        agents = set()
        for e in all_events:
            agents.add(e.agent_id)
            if e.target_id:
                agents.add(e.target_id)

        return {
            "score": round(score, 3),
            "window_seconds": self._window.window_seconds,
            "total_events": len(all_events),
            "total_events_all_time": self._total_events,
            "attestations": len(attestations),
            "revocations": len(revocations),
            "verifications": len(verifications),
            "attestation_rate_per_min": round(self._window.rate_per_minute(EventType.ATTESTATION), 2),
            "active_agents": len(agents),
            "latency": latency_stats,
            "anomalies": [
                {"type": a.alert_type, "severity": a.severity, "message": a.message}
                for a in anomalies
            ],
        }

    @property
    def total_events(self) -> int:
        return self._total_events


class MetricsExporter:
    """Export metrics in standard formats."""

    def __init__(self, monitor: TrustHealthMonitor):
        self._monitor = monitor

    def prometheus(self) -> str:
        """Export metrics in Prometheus text exposition format."""
        report = self._monitor.health_report()
        lines = [
            "# HELP isnad_health_score Trust network health score (0-1)",
            "# TYPE isnad_health_score gauge",
            f'isnad_health_score {report["score"]}',
            "",
            "# HELP isnad_events_total Total trust events in window",
            "# TYPE isnad_events_total gauge",
            f'isnad_events_total {report["total_events"]}',
            "",
            "# HELP isnad_attestations_total Attestations in window",
            "# TYPE isnad_attestations_total gauge",
            f'isnad_attestations_total {report["attestations"]}',
            "",
            "# HELP isnad_revocations_total Revocations in window",
            "# TYPE isnad_revocations_total gauge",
            f'isnad_revocations_total {report["revocations"]}',
            "",
            "# HELP isnad_verifications_total Verifications in window",
            "# TYPE isnad_verifications_total gauge",
            f'isnad_verifications_total {report["verifications"]}',
            "",
            "# HELP isnad_active_agents Active agents in network",
            "# TYPE isnad_active_agents gauge",
            f'isnad_active_agents {report["active_agents"]}',
            "",
            "# HELP isnad_attestation_rate Attestations per minute",
            "# TYPE isnad_attestation_rate gauge",
            f'isnad_attestation_rate {report["attestation_rate_per_min"]}',
            "",
            "# HELP isnad_anomalies_total Active anomaly alerts",
            "# TYPE isnad_anomalies_total gauge",
            f'isnad_anomalies_total {len(report["anomalies"])}',
        ]

        if report.get("latency"):
            lat = report["latency"]
            lines.extend([
                "",
                "# HELP isnad_latency_p50_ms Median operation latency",
                "# TYPE isnad_latency_p50_ms gauge",
                f'isnad_latency_p50_ms {lat["p50_ms"]:.1f}',
                "",
                "# HELP isnad_latency_p95_ms 95th percentile operation latency",
                "# TYPE isnad_latency_p95_ms gauge",
                f'isnad_latency_p95_ms {lat["p95_ms"]:.1f}',
            ])

        return "\n".join(lines) + "\n"

    def json_report(self) -> dict:
        """Export full health report as JSON-compatible dict."""
        return self._monitor.health_report()
