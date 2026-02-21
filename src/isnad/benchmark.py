"""isnad benchmarking — measure throughput, latency, and scalability.

Usage:
    from isnad.benchmark import BenchmarkSuite
    suite = BenchmarkSuite()
    results = suite.run_all()
    print(results.summary())
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from isnad.core import Attestation, TrustChain


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""
    name: str
    iterations: int
    total_seconds: float
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def ops_per_second(self) -> float:
        return self.iterations / self.total_seconds if self.total_seconds > 0 else float("inf")

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def p99_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.99)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def stdev_ms(self) -> float:
        if len(self.latencies_ms) < 2:
            return 0.0
        return statistics.stdev(self.latencies_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_seconds": round(self.total_seconds, 4),
            "ops_per_second": round(self.ops_per_second, 1),
            "mean_ms": round(self.mean_ms, 4),
            "median_ms": round(self.median_ms, 4),
            "p95_ms": round(self.p95_ms, 4),
            "p99_ms": round(self.p99_ms, 4),
            "stdev_ms": round(self.stdev_ms, 4),
        }


@dataclass
class BenchmarkReport:
    """Collection of benchmark results."""
    results: list[BenchmarkResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    def summary(self) -> str:
        lines = ["isnad Benchmark Report", "=" * 60]
        if self.metadata:
            for k, v in self.metadata.items():
                lines.append(f"  {k}: {v}")
            lines.append("-" * 60)
        for r in self.results:
            lines.append(
                f"  {r.name:<40} {r.ops_per_second:>10,.0f} ops/s  "
                f"mean={r.mean_ms:.3f}ms  p95={r.p95_ms:.3f}ms  p99={r.p99_ms:.3f}ms"
            )
        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "results": [r.to_dict() for r in self.results],
        }


def _bench(name: str, fn: Callable[[], Any], iterations: int = 1000, warmup: int = 100) -> BenchmarkResult:
    """Run a benchmark: warmup, then measure each iteration."""
    for _ in range(warmup):
        fn()

    latencies: list[float] = []
    start = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - t0) * 1000)
    total = time.perf_counter() - start

    return BenchmarkResult(name=name, iterations=iterations, total_seconds=total, latencies_ms=latencies)


class BenchmarkSuite:
    """Standard isnad benchmarks."""

    def __init__(self, iterations: int = 1000, warmup: int = 100):
        self.iterations = iterations
        self.warmup = warmup

    def bench_attestation_create(self) -> BenchmarkResult:
        """Measure attestation creation throughput."""
        counter = 0

        def fn():
            nonlocal counter
            counter += 1
            Attestation(
                subject=f"did:key:agent{counter}",
                witness="did:key:issuer1",
                task="benchmark",
                evidence=f"run {counter}",
            )

        return _bench("attestation_create", fn, self.iterations, self.warmup)

    def bench_chain_add(self) -> BenchmarkResult:
        """Measure adding attestations to a chain."""
        chain = TrustChain()

        def fn():
            a = Attestation(
                subject="did:key:bench_agent",
                witness="did:key:issuer1",
                task="benchmark",
            )
            chain.add(a)

        return _bench("chain_add", fn, self.iterations, self.warmup)

    def bench_chain_score(self) -> BenchmarkResult:
        """Measure trust score computation on a pre-built chain."""
        chain = TrustChain()
        for i in range(200):
            chain.add(Attestation(
                subject="did:key:score_agent",
                witness=f"did:key:issuer{i % 10}",
                task=f"task_{i % 5}",
            ))

        def fn():
            chain.trust_score("did:key:score_agent")

        return _bench("chain_score (200 attestations)", fn, self.iterations, self.warmup)

    def bench_chain_trust(self) -> BenchmarkResult:
        """Measure chain_trust computation."""
        chain = TrustChain()
        for i in range(100):
            chain.add(Attestation(
                subject="did:key:trust_agent",
                witness=f"did:key:issuer{i % 5}",
                task="benchmark",
            ))

        def fn():
            chain.chain_trust("did:key:trust_agent", "did:key:issuer0")

        return _bench("chain_trust (100 attestations)", fn, self.iterations, self.warmup)

    def bench_attestation_lookup(self) -> BenchmarkResult:
        """Measure looking up attestations by subject."""
        chain = TrustChain()
        for i in range(500):
            chain.add(Attestation(
                subject=f"did:key:agent{i % 20}",
                witness=f"did:key:issuer{i % 10}",
                task="benchmark",
            ))

        def fn():
            chain._by_subject.get("did:key:agent5", [])

        return _bench("attestation_lookup (500 in chain)", fn, self.iterations, self.warmup)

    def bench_scalability(self, sizes: list[int] | None = None) -> list[BenchmarkResult]:
        """Measure score computation at different chain sizes."""
        if sizes is None:
            sizes = [10, 50, 100, 500, 1000]

        results = []
        for size in sizes:
            chain = TrustChain()
            for i in range(size):
                chain.add(Attestation(
                    subject=f"did:key:scale_agent",
                    witness=f"did:key:issuer{i % 10}",
                    task="benchmark",
                ))
            iters = max(100, self.iterations // (size // 10 + 1))

            def make_fn(c=chain):
                return lambda: c.trust_score("did:key:scale_agent")

            results.append(_bench(f"score_at_{size}_attestations", make_fn(), iters, min(50, iters)))
        return results

    def run_all(self) -> BenchmarkReport:
        """Run all standard benchmarks."""
        report = BenchmarkReport(metadata={
            "iterations": self.iterations,
            "warmup": self.warmup,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

        report.add(self.bench_attestation_create())
        report.add(self.bench_chain_add())
        report.add(self.bench_chain_score())
        report.add(self.bench_chain_trust())
        report.add(self.bench_attestation_lookup())
        for r in self.bench_scalability():
            report.add(r)

        return report
