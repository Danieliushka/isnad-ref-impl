"""Tests for isnad.circuit_breaker — circuit breaker for trust network resilience."""

import threading
import time
import pytest

from isnad.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    CircuitStats,
    TrustCircuitBreaker,
    TrustCircuitStats,
    TrustService,
)


# ── CircuitBreaker basics ────────────────────────────────────

class TestCircuitBreakerInit:
    def test_defaults(self):
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 30.0

    def test_custom(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0, half_open_max_calls=2)
        assert cb.failure_threshold == 3

    def test_invalid_threshold(self):
        with pytest.raises(ValueError):
            CircuitBreaker(failure_threshold=0)

    def test_invalid_timeout(self):
        with pytest.raises(ValueError):
            CircuitBreaker(recovery_timeout=0)

    def test_invalid_half_open(self):
        with pytest.raises(ValueError):
            CircuitBreaker(half_open_max_calls=0)


class TestCircuitBreakerClosed:
    def test_passes_through(self):
        cb = CircuitBreaker()
        assert cb.call("svc", lambda: 42) == 42

    def test_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state("svc") == CircuitState.CLOSED

    def test_propagates_exceptions(self):
        cb = CircuitBreaker()
        with pytest.raises(RuntimeError, match="boom"):
            cb.call("svc", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    def test_failure_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        # 2 failures then success
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        cb.call("svc", lambda: "ok")
        assert cb.state("svc") == CircuitState.CLOSED
        # Can tolerate 2 more failures without opening
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        assert cb.state("svc") == CircuitState.CLOSED


class TestCircuitBreakerOpen:
    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        assert cb.state("svc") == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=100.0)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        with pytest.raises(CircuitOpenError) as exc_info:
            cb.call("svc", lambda: "should not run")
        assert exc_info.value.service == "svc"
        assert exc_info.value.retry_after > 0

    def test_open_error_message(self):
        e = CircuitOpenError("my-svc", 5.0)
        assert "my-svc" in str(e)
        assert "5.0" in str(e)

    def test_custom_error_message(self):
        e = CircuitOpenError("svc", 1.0, "custom")
        assert str(e) == "custom"


class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        time.sleep(0.02)
        assert cb.state("svc") == CircuitState.HALF_OPEN

    def test_closes_after_enough_successes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max_calls=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        time.sleep(0.02)
        cb.call("svc", lambda: "ok")
        cb.call("svc", lambda: "ok")
        assert cb.state("svc") == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max_calls=3)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        time.sleep(0.02)
        with pytest.raises(RuntimeError):
            cb.call("svc", _fail)
        assert cb.state("svc") == CircuitState.OPEN


class TestCircuitBreakerMultiService:
    def test_independent_services(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc-a", _fail)
        assert cb.state("svc-a") == CircuitState.OPEN
        assert cb.state("svc-b") == CircuitState.CLOSED
        assert cb.call("svc-b", lambda: 99) == 99

    def test_all_services(self):
        cb = CircuitBreaker()
        cb.call("a", lambda: 1)
        cb.call("b", lambda: 2)
        svcs = cb.all_services()
        assert "a" in svcs
        assert "b" in svcs


class TestCircuitBreakerStats:
    def test_initial_stats(self):
        cb = CircuitBreaker()
        s = cb.stats("svc")
        assert s.state == CircuitState.CLOSED
        assert s.failure_count == 0
        assert s.total_calls == 0

    def test_stats_after_calls(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.call("svc", lambda: "ok")
        with pytest.raises(RuntimeError):
            cb.call("svc", _fail)
        s = cb.stats("svc")
        assert s.total_calls == 2
        assert s.total_successes == 1
        assert s.total_failures == 1

    def test_stats_type(self):
        cb = CircuitBreaker()
        s = cb.stats("svc")
        assert isinstance(s, CircuitStats)
        assert s.service == "svc"


class TestCircuitBreakerReset:
    def test_reset_single(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        cb.reset("svc")
        assert cb.state("svc") == CircuitState.CLOSED

    def test_reset_all(self):
        cb = CircuitBreaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("a", _fail)
            with pytest.raises(RuntimeError):
                cb.call("b", _fail)
        cb.reset()
        assert cb.state("a") == CircuitState.CLOSED
        assert cb.state("b") == CircuitState.CLOSED


class TestCircuitBreakerManualRecording:
    def test_manual_failure(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("svc")
        cb.record_failure("svc")
        assert cb.state("svc") == CircuitState.OPEN

    def test_manual_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("svc")
        cb.record_failure("svc")
        cb.record_success("svc")
        # Success resets consecutive failures
        cb.record_failure("svc")
        cb.record_failure("svc")
        assert cb.state("svc") == CircuitState.CLOSED  # only 2 consecutive


class TestCircuitBreakerStateChangeCallback:
    def test_callback_fires(self):
        changes = []
        cb = CircuitBreaker(
            failure_threshold=2,
            on_state_change=lambda svc, old, new: changes.append((svc, old, new)),
        )
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call("svc", _fail)
        assert len(changes) == 1
        assert changes[0] == ("svc", CircuitState.CLOSED, CircuitState.OPEN)


class TestCircuitBreakerThreadSafety:
    def test_concurrent_calls(self):
        cb = CircuitBreaker(failure_threshold=100)
        results = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            try:
                r = cb.call("svc", lambda: 1)
                results.append(r)
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 10


# ── TrustCircuitBreaker ──────────────────────────────────────

class TestTrustCircuitBreaker:
    def test_default_construction(self):
        tcb = TrustCircuitBreaker()
        result = tcb.call("store-1", TrustService.ATTESTATION_STORE, lambda: "ok")
        assert result == "ok"

    def test_opens_on_failures(self):
        tcb = TrustCircuitBreaker({
            TrustService.CHAIN_RESOLVER: (2, 100.0, 2),
        })
        for _ in range(2):
            with pytest.raises(RuntimeError):
                tcb.call("resolver-1", TrustService.CHAIN_RESOLVER, _fail)
        assert tcb.state("resolver-1", TrustService.CHAIN_RESOLVER) == CircuitState.OPEN

    def test_service_type_isolation(self):
        tcb = TrustCircuitBreaker({
            TrustService.CHAIN_RESOLVER: (2, 100.0, 2),
            TrustService.SCORE_ENGINE: (2, 100.0, 2),
        })
        for _ in range(2):
            with pytest.raises(RuntimeError):
                tcb.call("svc-1", TrustService.CHAIN_RESOLVER, _fail)
        assert tcb.state("svc-1", TrustService.CHAIN_RESOLVER) == CircuitState.OPEN
        assert tcb.state("svc-1", TrustService.SCORE_ENGINE) == CircuitState.CLOSED

    def test_stats(self):
        tcb = TrustCircuitBreaker()
        tcb.call("store-1", TrustService.ATTESTATION_STORE, lambda: "ok")
        s = tcb.stats("store-1", TrustService.ATTESTATION_STORE)
        assert isinstance(s, CircuitStats)
        assert s.total_calls == 1

    def test_health_healthy(self):
        tcb = TrustCircuitBreaker()
        tcb.call("s1", TrustService.ATTESTATION_STORE, lambda: 1)
        h = tcb.health()
        assert isinstance(h, TrustCircuitStats)
        assert h.degraded is False
        assert len(h.open_circuits) == 0

    def test_health_degraded(self):
        tcb = TrustCircuitBreaker({
            TrustService.CHAIN_RESOLVER: (2, 100.0, 2),
        })
        for _ in range(2):
            with pytest.raises(RuntimeError):
                tcb.call("r1", TrustService.CHAIN_RESOLVER, _fail)
        h = tcb.health()
        assert h.degraded is True
        assert len(h.open_circuits) == 1

    def test_reset_specific(self):
        tcb = TrustCircuitBreaker({
            TrustService.CHAIN_RESOLVER: (2, 100.0, 2),
        })
        for _ in range(2):
            with pytest.raises(RuntimeError):
                tcb.call("r1", TrustService.CHAIN_RESOLVER, _fail)
        tcb.reset(TrustService.CHAIN_RESOLVER, "r1")
        assert tcb.state("r1", TrustService.CHAIN_RESOLVER) == CircuitState.CLOSED

    def test_reset_all(self):
        tcb = TrustCircuitBreaker({
            TrustService.CHAIN_RESOLVER: (2, 100.0, 2),
        })
        for _ in range(2):
            with pytest.raises(RuntimeError):
                tcb.call("r1", TrustService.CHAIN_RESOLVER, _fail)
        tcb.reset()
        assert tcb.state("r1", TrustService.CHAIN_RESOLVER) == CircuitState.CLOSED

    def test_all_service_types_available(self):
        tcb = TrustCircuitBreaker()
        for svc in TrustService:
            result = tcb.call("test", svc, lambda: "ok")
            assert result == "ok"

    def test_state_change_callback(self):
        changes = []
        tcb = TrustCircuitBreaker(
            thresholds={TrustService.DISCOVERY: (1, 100.0, 1)},
            on_state_change=lambda s, o, n: changes.append((s, o, n)),
        )
        with pytest.raises(RuntimeError):
            tcb.call("d1", TrustService.DISCOVERY, _fail)
        assert len(changes) == 1


class TestTrustServiceEnum:
    def test_count(self):
        assert len(list(TrustService)) == 7

    def test_values(self):
        assert TrustService.ATTESTATION_STORE.value == "attestation_store"
        assert TrustService.FEDERATION_PEER.value == "federation_peer"


class TestCircuitStateEnum:
    def test_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


# ── Helper ────────────────────────────────────────────────────

def _fail():
    raise RuntimeError("service error")
