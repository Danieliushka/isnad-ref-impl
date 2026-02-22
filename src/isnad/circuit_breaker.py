"""isnad.circuit_breaker — Circuit breaker for trust network resilience.

Prevents cascading failures when trust services (attestation stores,
chain resolvers, score engines) become unreliable. Tracks failure rates
per-service and opens the circuit when a threshold is breached.

States:
    CLOSED   — Normal operation, requests pass through
    OPEN     — Service failing, requests short-circuit immediately
    HALF_OPEN — Testing recovery, limited requests allowed

Usage:
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

    try:
        result = cb.call("chain-resolver", lambda: resolve_chain(chain_id))
    except CircuitOpenError:
        use_cached_result()

    # Trust-aware variant
    tcb = TrustCircuitBreaker()
    tcb.call("attestation-store", TrustService.ATTESTATION_STORE,
             lambda: store.get(att_id))
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, service: str, retry_after: float, message: str = ""):
        self.service = service
        self.retry_after = retry_after
        super().__init__(message or f"Circuit open for '{service}'; retry after {retry_after:.1f}s")


@dataclass
class CircuitStats:
    """Snapshot of a circuit's state."""
    service: str
    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_successes_in_half_open: int = 0


@dataclass
class _ServiceCircuit:
    """Internal state for one service's circuit."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    last_state_change: float = 0.0
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    half_open_successes: int = 0


class CircuitBreaker:
    """Circuit breaker with per-service tracking.

    Args:
        failure_threshold: Consecutive failures before opening circuit.
        recovery_timeout: Seconds to wait before trying half-open.
        half_open_max_calls: Successes needed in half-open to close circuit.
        on_state_change: Optional callback(service, old_state, new_state).
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        on_state_change: Optional[Callable[[str, CircuitState, CircuitState], None]] = None,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")

        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max_calls
        self._on_state_change = on_state_change
        self._circuits: dict[str, _ServiceCircuit] = {}
        self._lock = threading.Lock()

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def recovery_timeout(self) -> float:
        return self._recovery_timeout

    def _get_circuit(self, service: str) -> _ServiceCircuit:
        if service not in self._circuits:
            self._circuits[service] = _ServiceCircuit(last_state_change=time.monotonic())
        return self._circuits[service]

    def _set_state(self, service: str, circuit: _ServiceCircuit, new_state: CircuitState) -> None:
        old = circuit.state
        if old != new_state:
            circuit.state = new_state
            circuit.last_state_change = time.monotonic()
            if new_state == CircuitState.HALF_OPEN:
                circuit.half_open_successes = 0
            if self._on_state_change:
                self._on_state_change(service, old, new_state)

    def state(self, service: str) -> CircuitState:
        """Get current state for a service."""
        with self._lock:
            c = self._get_circuit(service)
            now = time.monotonic()
            if c.state == CircuitState.OPEN:
                if now - c.last_state_change >= self._recovery_timeout:
                    self._set_state(service, c, CircuitState.HALF_OPEN)
            return c.state

    def call(self, service: str, fn: Callable[[], T]) -> T:
        """Execute fn through the circuit breaker.

        Raises CircuitOpenError if circuit is open.
        Records success/failure to manage state transitions.
        """
        now = time.monotonic()

        with self._lock:
            c = self._get_circuit(service)
            # Check for auto-transition OPEN -> HALF_OPEN
            if c.state == CircuitState.OPEN:
                elapsed = now - c.last_state_change
                if elapsed >= self._recovery_timeout:
                    self._set_state(service, c, CircuitState.HALF_OPEN)
                else:
                    raise CircuitOpenError(service, self._recovery_timeout - elapsed)
            c.total_calls += 1

        # Execute outside lock
        try:
            result = fn()
        except Exception as e:
            self._record_failure(service, time.monotonic())
            raise
        else:
            self._record_success(service, time.monotonic())
            return result

    def _record_failure(self, service: str, now: float) -> None:
        with self._lock:
            c = self._get_circuit(service)
            c.failure_count += 1
            c.total_failures += 1
            c.success_count = 0
            c.last_failure_time = now

            if c.state == CircuitState.HALF_OPEN:
                self._set_state(service, c, CircuitState.OPEN)
            elif c.state == CircuitState.CLOSED and c.failure_count >= self._failure_threshold:
                self._set_state(service, c, CircuitState.OPEN)

    def _record_success(self, service: str, now: float) -> None:
        with self._lock:
            c = self._get_circuit(service)
            c.success_count += 1
            c.total_successes += 1
            c.last_success_time = now

            if c.state == CircuitState.HALF_OPEN:
                c.half_open_successes += 1
                if c.half_open_successes >= self._half_open_max:
                    c.failure_count = 0
                    self._set_state(service, c, CircuitState.CLOSED)
            elif c.state == CircuitState.CLOSED:
                c.failure_count = 0  # reset consecutive failures on success

    def record_failure(self, service: str) -> None:
        """Manually record a failure (e.g., from external health check)."""
        self._record_failure(service, time.monotonic())

    def record_success(self, service: str) -> None:
        """Manually record a success."""
        self._record_success(service, time.monotonic())

    def reset(self, service: Optional[str] = None) -> None:
        """Reset one or all circuits to CLOSED."""
        with self._lock:
            if service:
                self._circuits.pop(service, None)
            else:
                self._circuits.clear()

    def stats(self, service: str) -> CircuitStats:
        """Get stats for a service."""
        with self._lock:
            c = self._get_circuit(service)
            now = time.monotonic()
            if c.state == CircuitState.OPEN and now - c.last_state_change >= self._recovery_timeout:
                self._set_state(service, c, CircuitState.HALF_OPEN)
            return CircuitStats(
                service=service,
                state=c.state,
                failure_count=c.failure_count,
                success_count=c.success_count,
                last_failure_time=c.last_failure_time or None,
                last_success_time=c.last_success_time or None,
                total_calls=c.total_calls,
                total_failures=c.total_failures,
                total_successes=c.total_successes,
                consecutive_successes_in_half_open=c.half_open_successes,
            )

    def all_services(self) -> list[str]:
        """List tracked services."""
        with self._lock:
            return list(self._circuits.keys())


# ---------------------------------------------------------------------------
# Trust-specific circuit breaker
# ---------------------------------------------------------------------------

class TrustService(Enum):
    """Trust infrastructure services that may need circuit breaking."""
    ATTESTATION_STORE = "attestation_store"
    CHAIN_RESOLVER = "chain_resolver"
    SCORE_ENGINE = "score_engine"
    DELEGATION_REGISTRY = "delegation_registry"
    REVOCATION_CHECK = "revocation_check"
    FEDERATION_PEER = "federation_peer"
    DISCOVERY = "discovery"


# Default thresholds per service type
_DEFAULT_THRESHOLDS: dict[TrustService, tuple[int, float, int]] = {
    # (failure_threshold, recovery_timeout, half_open_max)
    TrustService.ATTESTATION_STORE: (5, 30.0, 3),
    TrustService.CHAIN_RESOLVER: (3, 20.0, 2),
    TrustService.SCORE_ENGINE: (5, 30.0, 3),
    TrustService.DELEGATION_REGISTRY: (5, 30.0, 3),
    TrustService.REVOCATION_CHECK: (3, 15.0, 2),
    TrustService.FEDERATION_PEER: (3, 60.0, 2),
    TrustService.DISCOVERY: (5, 30.0, 3),
}


@dataclass
class TrustCircuitStats:
    """Aggregate stats across all trust services."""
    services: dict[str, CircuitStats] = field(default_factory=dict)
    open_circuits: list[str] = field(default_factory=list)
    degraded: bool = False


class TrustCircuitBreaker:
    """Circuit breaker specialized for trust infrastructure.

    Maintains per-service-type breakers with tuned thresholds.
    Provides aggregate health view across the trust network.
    """

    def __init__(
        self,
        thresholds: Optional[dict[TrustService, tuple[int, float, int]]] = None,
        on_state_change: Optional[Callable[[str, CircuitState, CircuitState], None]] = None,
    ):
        self._thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._breakers: dict[TrustService, CircuitBreaker] = {}
        self._on_state_change = on_state_change
        for svc, (ft, rt, ho) in self._thresholds.items():
            self._breakers[svc] = CircuitBreaker(
                failure_threshold=ft,
                recovery_timeout=rt,
                half_open_max_calls=ho,
                on_state_change=on_state_change,
            )

    def call(self, service_id: str, service_type: TrustService,
             fn: Callable[[], T]) -> T:
        """Execute through the appropriate circuit breaker."""
        return self._breakers[service_type].call(service_id, fn)

    def state(self, service_id: str, service_type: TrustService) -> CircuitState:
        """Get circuit state for a specific service instance."""
        return self._breakers[service_type].state(service_id)

    def stats(self, service_id: str, service_type: TrustService) -> CircuitStats:
        """Get stats for a specific service instance."""
        return self._breakers[service_type].stats(service_id)

    def health(self) -> TrustCircuitStats:
        """Get aggregate health across all trust services."""
        result = TrustCircuitStats()
        for svc_type, breaker in self._breakers.items():
            for svc_id in breaker.all_services():
                s = breaker.stats(svc_id)
                key = f"{svc_type.value}:{svc_id}"
                result.services[key] = s
                if s.state == CircuitState.OPEN:
                    result.open_circuits.append(key)
                if s.state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
                    result.degraded = True
        return result

    def reset(self, service_type: Optional[TrustService] = None,
              service_id: Optional[str] = None) -> None:
        """Reset circuits."""
        if service_type:
            self._breakers[service_type].reset(service_id)
        else:
            for b in self._breakers.values():
                b.reset(service_id)
