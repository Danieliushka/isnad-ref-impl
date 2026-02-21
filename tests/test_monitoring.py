"""Tests for isnad.monitoring — trust network health monitoring."""

import time
import pytest
from unittest.mock import patch
from isnad.monitoring import (
    EventType, MetricEvent, SlidingWindow, AnomalyDetector,
    AnomalyAlert, TrustHealthMonitor, MetricsExporter,
)


# ─── SlidingWindow ───


class TestSlidingWindow:
    def test_add_and_count(self):
        w = SlidingWindow(window_seconds=60)
        e = MetricEvent(EventType.ATTESTATION, time.time(), "a1")
        w.add(e)
        assert w.count() == 1

    def test_count_by_type(self):
        w = SlidingWindow(60)
        w.add(MetricEvent(EventType.ATTESTATION, time.time(), "a1"))
        w.add(MetricEvent(EventType.REVOCATION, time.time(), "a1"))
        w.add(MetricEvent(EventType.ATTESTATION, time.time(), "a2"))
        assert w.count(EventType.ATTESTATION) == 2
        assert w.count(EventType.REVOCATION) == 1

    def test_prune_old_events(self):
        w = SlidingWindow(window_seconds=10)
        old = MetricEvent(EventType.ATTESTATION, time.time() - 20, "a1")
        new = MetricEvent(EventType.ATTESTATION, time.time(), "a1")
        w.add(old)
        w.add(new)
        assert w.count() == 1

    def test_rate_per_minute_empty(self):
        w = SlidingWindow(60)
        assert w.rate_per_minute() == 0.0

    def test_rate_per_minute_with_events(self):
        w = SlidingWindow(600)
        now = time.time()
        for i in range(10):
            w.add(MetricEvent(EventType.ATTESTATION, now - 60 + i, "a1"))
        rate = w.rate_per_minute()
        assert rate > 0

    def test_events_returns_copy(self):
        w = SlidingWindow(60)
        w.add(MetricEvent(EventType.ATTESTATION, time.time(), "a1"))
        events = w.events()
        events.clear()
        assert w.count() == 1


# ─── AnomalyDetector ───


class TestAnomalyDetector:
    def test_no_anomalies_on_healthy_network(self):
        d = AnomalyDetector()
        w = SlidingWindow(60)
        now = time.time()
        for i in range(20):
            w.add(MetricEvent(EventType.ATTESTATION, now - i, f"a{i}", score=0.8, latency_ms=10))
        alerts = d.analyze(w)
        assert len(alerts) == 0

    def test_revocation_spike(self):
        d = AnomalyDetector(revocation_spike_threshold=2.0)
        w = SlidingWindow(60)
        now = time.time()
        w.add(MetricEvent(EventType.ATTESTATION, now, "a1"))
        for i in range(5):
            w.add(MetricEvent(EventType.REVOCATION, now, f"a{i}", target_id="t1"))
        alerts = d.analyze(w)
        assert any(a.alert_type == "revocation_spike" for a in alerts)

    def test_low_avg_trust(self):
        d = AnomalyDetector(low_score_threshold=0.3)
        w = SlidingWindow(60)
        now = time.time()
        for i in range(10):
            w.add(MetricEvent(EventType.ATTESTATION, now, "a1", score=0.1))
        alerts = d.analyze(w)
        assert any(a.alert_type == "low_avg_trust" for a in alerts)

    def test_high_failure_rate(self):
        d = AnomalyDetector(high_failure_rate=0.2)
        w = SlidingWindow(60)
        now = time.time()
        for i in range(8):
            w.add(MetricEvent(EventType.ATTESTATION, now, "a1", success=True))
        for i in range(5):
            w.add(MetricEvent(EventType.ATTESTATION, now, "a1", success=False))
        alerts = d.analyze(w)
        assert any(a.alert_type == "high_failure_rate" for a in alerts)

    def test_latency_spike(self):
        d = AnomalyDetector(latency_spike_factor=3.0)
        w = SlidingWindow(60)
        now = time.time()
        # Baseline: 10ms
        for i in range(20):
            w.add(MetricEvent(EventType.ATTESTATION, now - 30 + i, "a1", latency_ms=10))
        # Spike: 100ms
        for i in range(5):
            w.add(MetricEvent(EventType.ATTESTATION, now, "a1", latency_ms=100))
        alerts = d.analyze(w)
        assert any(a.alert_type == "latency_spike" for a in alerts)

    def test_mass_revocation(self):
        d = AnomalyDetector()
        w = SlidingWindow(60)
        now = time.time()
        for i in range(6):
            w.add(MetricEvent(EventType.REVOCATION, now, "evil_agent", target_id=f"t{i}"))
        w.add(MetricEvent(EventType.ATTESTATION, now, "good_agent"))
        alerts = d.analyze(w)
        assert any(a.alert_type == "mass_revocation" and a.agent_id == "evil_agent" for a in alerts)

    def test_no_alerts_below_threshold(self):
        d = AnomalyDetector()
        w = SlidingWindow(60)
        now = time.time()
        # Everything healthy
        for i in range(10):
            w.add(MetricEvent(EventType.ATTESTATION, now, "a1", score=0.9, latency_ms=5, success=True))
        assert d.analyze(w) == []


# ─── TrustHealthMonitor ───


class TestTrustHealthMonitor:
    def test_record_attestation(self):
        m = TrustHealthMonitor()
        m.record_attestation("a1", "t1", score=0.9, latency_ms=5)
        assert m.total_events == 1

    def test_record_revocation(self):
        m = TrustHealthMonitor()
        m.record_revocation("a1", "t1", reason="spam")
        report = m.health_report()
        assert report["revocations"] == 1

    def test_record_delegation(self):
        m = TrustHealthMonitor()
        m.record_delegation("a1", "d1", scope="read")
        assert m.total_events == 1

    def test_record_verification(self):
        m = TrustHealthMonitor()
        m.record_verification("a1", "t1", valid=True, latency_ms=2)
        report = m.health_report()
        assert report["verifications"] == 1

    def test_record_federation_sync(self):
        m = TrustHealthMonitor()
        m.record_federation_sync("a1", "network_b", records_synced=10)
        assert m.total_events == 1

    def test_record_handshake(self):
        m = TrustHealthMonitor()
        m.record_handshake("a1", "a2", latency_ms=15)
        assert m.total_events == 1

    def test_health_report_perfect(self):
        m = TrustHealthMonitor()
        for i in range(10):
            m.record_attestation(f"a{i}", "t1", score=0.9, latency_ms=5)
        report = m.health_report()
        assert report["score"] >= 0.9
        assert report["attestations"] == 10
        assert report["active_agents"] == 11  # 10 agents + 1 target

    def test_health_report_degraded(self):
        m = TrustHealthMonitor()
        for i in range(10):
            m.record_attestation("a1", "t1", score=0.9, success=True)
        for i in range(10):
            m.record_attestation("a2", "t2", score=0.5, success=False)
        report = m.health_report()
        assert report["score"] < 0.9

    def test_health_report_latency_stats(self):
        m = TrustHealthMonitor()
        for i in range(10):
            m.record_attestation("a1", "t1", latency_ms=10 + i)
        report = m.health_report()
        assert "p50_ms" in report["latency"]
        assert "mean_ms" in report["latency"]

    def test_on_alert_callback(self):
        alerts_received = []
        m = TrustHealthMonitor()
        m.on_alert(lambda a: alerts_received.append(a))
        # Trigger mass revocation
        for i in range(6):
            m.record_revocation("evil", f"t{i}")
        # Also need at least one attestation for revocation_spike check
        m.record_attestation("good", "t1")
        # Should have triggered alerts
        assert len(alerts_received) > 0

    def test_empty_report(self):
        m = TrustHealthMonitor()
        report = m.health_report()
        assert report["score"] == 1.0
        assert report["total_events"] == 0
        assert report["anomalies"] == []

    def test_health_score_bounded(self):
        m = TrustHealthMonitor()
        # All failures
        for i in range(20):
            m.record_attestation("a1", "t1", success=False)
        report = m.health_report()
        assert 0.0 <= report["score"] <= 1.0

    def test_active_agents_count(self):
        m = TrustHealthMonitor()
        m.record_attestation("a1", "a2")
        m.record_attestation("a3", "a4")
        m.record_handshake("a1", "a3")
        report = m.health_report()
        assert report["active_agents"] == 4


# ─── MetricsExporter ───


class TestMetricsExporter:
    def test_prometheus_format(self):
        m = TrustHealthMonitor()
        m.record_attestation("a1", "t1", score=0.9, latency_ms=10)
        exp = MetricsExporter(m)
        prom = exp.prometheus()
        assert "isnad_health_score" in prom
        assert "isnad_events_total 1" in prom
        assert "isnad_attestations_total 1" in prom
        assert "isnad_latency_p50_ms" in prom

    def test_prometheus_empty(self):
        m = TrustHealthMonitor()
        exp = MetricsExporter(m)
        prom = exp.prometheus()
        assert "isnad_health_score 1" in prom
        assert "isnad_events_total 0" in prom

    def test_json_report(self):
        m = TrustHealthMonitor()
        m.record_attestation("a1", "t1")
        exp = MetricsExporter(m)
        report = exp.json_report()
        assert isinstance(report, dict)
        assert "score" in report
        assert "attestations" in report

    def test_prometheus_with_anomalies(self):
        m = TrustHealthMonitor()
        for i in range(6):
            m.record_revocation("evil", f"t{i}")
        m.record_attestation("good", "t1")
        exp = MetricsExporter(m)
        prom = exp.prometheus()
        assert "isnad_anomalies_total" in prom
        # Should show > 0 anomalies
        lines = prom.split("\n")
        anomaly_line = [l for l in lines if l.startswith("isnad_anomalies_total")]
        assert anomaly_line
        count = int(anomaly_line[0].split()[-1])
        assert count > 0


# ─── Integration ───


class TestMonitoringIntegration:
    def test_full_workflow(self):
        """Simulate a full trust network monitoring workflow."""
        alerts = []
        m = TrustHealthMonitor(window_seconds=60)
        m.on_alert(lambda a: alerts.append(a))

        # Normal operations
        for i in range(10):
            m.record_attestation(f"agent_{i}", "service_a", score=0.85, latency_ms=12)
        m.record_delegation("agent_0", "agent_1", scope="verify")
        m.record_handshake("agent_0", "agent_2", latency_ms=20)
        m.record_federation_sync("agent_0", "network_b", records_synced=5)

        report = m.health_report()
        assert report["score"] > 0.8
        assert report["attestations"] == 10
        assert report["active_agents"] >= 10

        # Verify export works
        exp = MetricsExporter(m)
        prom = exp.prometheus()
        assert len(prom) > 100

    def test_degradation_scenario(self):
        """Test network degradation detection."""
        alerts = []
        m = TrustHealthMonitor(window_seconds=60)
        m.on_alert(lambda a: alerts.append(a))

        # Start healthy
        for i in range(10):
            m.record_attestation("good_agent", "target", score=0.9, latency_ms=5, success=True)

        healthy_report = m.health_report()

        # Network degrades
        for i in range(10):
            m.record_attestation("bad_agent", "target", score=0.1, latency_ms=500, success=False)
        for i in range(6):
            m.record_revocation("attacker", f"target_{i}")

        degraded_report = m.health_report()
        assert degraded_report["score"] < healthy_report["score"]
        assert len(degraded_report["anomalies"]) > 0
        assert len(alerts) > 0
