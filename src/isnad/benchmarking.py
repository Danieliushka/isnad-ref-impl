"""
isnad.benchmarking — Performance benchmarking suite for isnad operations.

Measure trust score computation, storage throughput, graph analytics,
and cache performance. Stdlib only: time, statistics, tracemalloc, dataclasses, json.
"""

from __future__ import annotations

import json
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BenchmarkResult:
    """Single benchmark measurement."""
    operation: str
    duration_ms: float
    throughput_ops: float = 0.0
    memory_delta_kb: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class BenchmarkReport:
    """Aggregate results, format as table/JSON, compare runs."""

    def __init__(self, name: str = "benchmark"):
        self.name = name
        self.results: List[BenchmarkResult] = []
        self.metadata: Dict[str, Any] = {}
        self._timestamp: float = time.time()

    def add(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    def add_many(self, results: List[BenchmarkResult]) -> None:
        self.results.extend(results)

    def summary(self) -> Dict[str, Any]:
        if not self.results:
            return {"count": 0}
        durations = [r.duration_ms for r in self.results]
        throughputs = [r.throughput_ops for r in self.results if r.throughput_ops > 0]
        memory = [r.memory_delta_kb for r in self.results]
        s: Dict[str, Any] = {
            "count": len(self.results),
            "total_duration_ms": sum(durations),
            "mean_duration_ms": statistics.mean(durations),
            "median_duration_ms": statistics.median(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
        }
        if len(durations) >= 2:
            s["stdev_duration_ms"] = statistics.stdev(durations)
        if throughputs:
            s["mean_throughput_ops"] = statistics.mean(throughputs)
        if memory:
            s["total_memory_delta_kb"] = sum(memory)
        return s

    def by_operation(self) -> Dict[str, List[BenchmarkResult]]:
        groups: Dict[str, List[BenchmarkResult]] = {}
        for r in self.results:
            groups.setdefault(r.operation, []).append(r)
        return groups

    def format_table(self, width: int = 80) -> str:
        if not self.results:
            return f"No results in '{self.name}'"
        lines = [
            f"Benchmark Report: {self.name}",
            "=" * width,
            f"{'Operation':<30} {'Duration(ms)':>12} {'Throughput':>12} {'Memory(KB)':>12}",
            "-" * width,
        ]
        for r in self.results:
            lines.append(
                f"{r.operation:<30} {r.duration_ms:>12.3f} {r.throughput_ops:>12.1f} {r.memory_delta_kb:>12.1f}"
            )
        lines.append("-" * width)
        s = self.summary()
        lines.append(f"Total: {s['count']} operations, {s['total_duration_ms']:.3f}ms")
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps({
            "name": self.name,
            "timestamp": self._timestamp,
            "metadata": self.metadata,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary(),
        }, indent=indent)

    @staticmethod
    def compare(a: "BenchmarkReport", b: "BenchmarkReport") -> Dict[str, Any]:
        a_ops = {op: statistics.mean([r.duration_ms for r in rs])
                 for op, rs in a.by_operation().items()}
        b_ops = {op: statistics.mean([r.duration_ms for r in rs])
                 for op, rs in b.by_operation().items()}
        comparison: Dict[str, Any] = {"a_name": a.name, "b_name": b.name, "operations": {}}
        for op in sorted(set(a_ops) | set(b_ops)):
            entry: Dict[str, Any] = {}
            if op in a_ops:
                entry["a_ms"] = a_ops[op]
            if op in b_ops:
                entry["b_ms"] = b_ops[op]
            if op in a_ops and op in b_ops and b_ops[op] > 0:
                entry["speedup"] = a_ops[op] / b_ops[op]
            comparison["operations"][op] = entry
        return comparison


def _measure(func: Callable, *args: Any, **kwargs: Any) -> tuple:
    """Run func, return (result, duration_ms, memory_delta_kb)."""
    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = (time.perf_counter() - start) * 1000.0
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    stats = snap_after.compare_to(snap_before, "lineno")
    mem_delta = sum(s.size_diff for s in stats) / 1024.0
    return result, elapsed, mem_delta


def _bench(operation: str, func: Callable, *args: Any,
           iterations: int = 1, **kwargs: Any) -> BenchmarkResult:
    """Benchmark a callable over N iterations."""
    total_ms = 0.0
    total_mem = 0.0
    for _ in range(iterations):
        _, ms, mem = _measure(func, *args, **kwargs)
        total_ms += ms
        total_mem += mem
    avg_ms = total_ms / iterations
    throughput = (iterations / total_ms * 1000.0) if total_ms > 0 else 0.0
    return BenchmarkResult(
        operation=operation,
        duration_ms=avg_ms,
        throughput_ops=throughput,
        memory_delta_kb=total_mem / iterations,
    )


class TrustScoreBenchmark:
    """Benchmark trust score computation."""

    def __init__(self, iterations: int = 10):
        self.iterations = iterations

    def _make_scorer(self, n_interactions: int = 20, n_endorsements: int = 10):
        from isnad.trustscore.bridge import InteractionRecord, EndorsementRecord
        from isnad.trustscore.scorer import TrustScorer
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        interactions = [
            InteractionRecord(
                agent_id=f"agent-{i % 5}",
                interaction_type="task_complete",
                outcome="success",
                timestamp=(now - timedelta(hours=i)).isoformat(),
                context={"topic": f"topic-{i % 3}"},
            )
            for i in range(n_interactions)
        ]
        endorsements = [
            EndorsementRecord(
                endorser_id=f"endorser-{i}",
                endorsed_id="target",
                skill_area="general",
                confidence=0.7 + (i % 4) * 0.05,
                evidence_hash=f"hash-{i}",
            )
            for i in range(n_endorsements)
        ]
        return TrustScorer(interactions=interactions, endorsements=endorsements)

    def run_single(self) -> BenchmarkResult:
        scorer = self._make_scorer()
        return _bench("trust_score_single", scorer.compute, iterations=self.iterations)

    def run_batch(self, batch_size: int = 50) -> BenchmarkResult:
        scorers = [self._make_scorer() for _ in range(batch_size)]
        def score_all():
            for s in scorers:
                s.compute()
        return _bench("trust_score_batch", score_all, iterations=self.iterations)

    def run_cached_vs_uncached(self) -> List[BenchmarkResult]:
        from isnad.caching import LRUCache
        scorer = self._make_scorer()
        uncached = _bench("trust_score_uncached", scorer.compute, iterations=self.iterations)

        cache = LRUCache(max_size=100, default_ttl=60.0)
        cache_key = "bench_score"

        def cached_score():
            hit = cache.get(cache_key)
            if hit is not None:
                return hit
            val = scorer.compute()
            cache.set(cache_key, val)
            return val

        cached_score()  # warm
        cached = _bench("trust_score_cached", cached_score, iterations=self.iterations)
        return [uncached, cached]

    def run_all(self) -> BenchmarkReport:
        report = BenchmarkReport("TrustScoreBenchmark")
        report.add(self.run_single())
        report.add(self.run_batch())
        report.add_many(self.run_cached_vs_uncached())
        return report


class StorageBenchmark:
    """Benchmark read/write throughput for each storage backend."""

    def __init__(self, iterations: int = 100):
        self.iterations = iterations

    @staticmethod
    def _make_data(i: int) -> dict:
        return {"id": f"item-{i}", "value": i, "payload": "x" * 200}

    def _bench_backend(self, backend, name: str) -> List[BenchmarkResult]:
        results = []
        n = self.iterations

        def do_writes():
            for i in range(n):
                backend.save(f"bench-{i}", self._make_data(i))

        results.append(_bench(f"{name}_write", do_writes))

        def do_reads():
            for i in range(n):
                backend.load(f"bench-{i}")

        results.append(_bench(f"{name}_read", do_reads))

        for r in results:
            if r.duration_ms > 0:
                r.throughput_ops = n / r.duration_ms * 1000.0

        for i in range(n):
            backend.delete(f"bench-{i}")

        return results

    def run_memory(self) -> List[BenchmarkResult]:
        from isnad.storage import MemoryBackend
        return self._bench_backend(MemoryBackend(), "memory")

    def run_sqlite(self) -> List[BenchmarkResult]:
        import tempfile, os
        from isnad.storage import SQLiteBackend
        tmp = tempfile.mktemp(suffix=".db")
        try:
            return self._bench_backend(SQLiteBackend(tmp), "sqlite")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def run_file(self) -> List[BenchmarkResult]:
        import tempfile, shutil
        from isnad.storage import FileBackend
        tmp = tempfile.mkdtemp()
        try:
            return self._bench_backend(FileBackend(tmp), "file")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def run_all(self) -> BenchmarkReport:
        report = BenchmarkReport("StorageBenchmark")
        report.add_many(self.run_memory())
        report.add_many(self.run_sqlite())
        report.add_many(self.run_file())
        return report


class GraphBenchmark:
    """Benchmark graph analytics at different graph sizes."""

    DEFAULT_SIZES = [10, 100, 1000, 10000]

    def __init__(self, sizes: Optional[List[int]] = None):
        self.sizes = sizes or self.DEFAULT_SIZES

    @staticmethod
    def _build_analytics(n: int):
        from isnad.analytics import TrustGraph, TrustAnalytics
        g = TrustGraph()
        for i in range(n):
            g.add_agent(f"a{i}")
        for i in range(n - 1):
            g.add_edge(f"a{i}", f"a{i+1}", 0.8)
        for i in range(0, n, 2):
            j = (i * 7 + 3) % n
            if i != j:
                g.add_edge(f"a{i}", f"a{j}", 0.6)
        return TrustAnalytics(g)

    def run_pagerank(self) -> List[BenchmarkResult]:
        results = []
        for n in self.sizes:
            a = self._build_analytics(n)
            r = _bench(f"pagerank_n{n}", a.pagerank, iterations=1)
            results.append(r)
        return results

    def run_sybil(self) -> List[BenchmarkResult]:
        results = []
        for n in self.sizes:
            a = self._build_analytics(n)
            seeds = {f"a0", f"a1"}
            r = _bench(f"sybil_n{n}", a.sybil_scores, seeds, iterations=1)
            results.append(r)
        return results

    def run_communities(self) -> List[BenchmarkResult]:
        results = []
        for n in self.sizes:
            a = self._build_analytics(n)
            r = _bench(f"communities_n{n}", a.communities, iterations=1)
            results.append(r)
        return results

    def run_all(self) -> BenchmarkReport:
        report = BenchmarkReport("GraphBenchmark")
        report.add_many(self.run_pagerank())
        report.add_many(self.run_sybil())
        report.add_many(self.run_communities())
        return report


class CacheBenchmark:
    """Benchmark cache hit/miss ratios, eviction overhead."""

    def __init__(self, cache_size: int = 100, iterations: int = 500):
        self.cache_size = cache_size
        self.iterations = iterations

    def run_hit_miss(self) -> BenchmarkResult:
        from isnad.caching import LRUCache
        cache = LRUCache(max_size=self.cache_size, default_ttl=60.0)
        for i in range(self.cache_size):
            cache.set(f"k{i}", i)

        _, ms, mem = _measure(self._do_hit_miss, cache)
        stats = cache.stats
        total = stats.hits + stats.misses
        throughput = total / ms * 1000.0 if ms > 0 else 0.0
        return BenchmarkResult(
            operation="cache_hit_miss",
            duration_ms=ms,
            throughput_ops=throughput,
            memory_delta_kb=mem,
        )

    def _do_hit_miss(self, cache):
        for i in range(self.iterations):
            if i % 10 < 7:
                key = f"k{i % self.cache_size}"
            else:
                key = f"miss-{i}"
            val = cache.get(key)
            if val is None:
                cache.set(key, i)

    def run_eviction(self) -> BenchmarkResult:
        from isnad.caching import LRUCache
        cache = LRUCache(max_size=self.cache_size, default_ttl=60.0)

        def fill_and_overflow():
            for i in range(self.cache_size * 3):
                cache.set(f"ek{i}", i)

        r = _bench("cache_eviction", fill_and_overflow, iterations=1)
        r.throughput_ops = self.cache_size * 3 / r.duration_ms * 1000.0 if r.duration_ms > 0 else 0.0
        return r

    def run_all(self) -> BenchmarkReport:
        report = BenchmarkReport("CacheBenchmark")
        report.add(self.run_hit_miss())
        report.add(self.run_eviction())
        return report


class BenchmarkSuite:
    """Run all benchmarks and aggregate into a single report."""

    def __init__(
        self,
        trust_iterations: int = 5,
        storage_iterations: int = 50,
        graph_sizes: Optional[List[int]] = None,
        cache_size: int = 100,
        cache_iterations: int = 300,
    ):
        self.trust = TrustScoreBenchmark(iterations=trust_iterations)
        self.storage = StorageBenchmark(iterations=storage_iterations)
        self.graph = GraphBenchmark(sizes=graph_sizes)
        self.cache = CacheBenchmark(cache_size=cache_size, iterations=cache_iterations)

    def run_all(self) -> BenchmarkReport:
        report = BenchmarkReport("FullBenchmarkSuite")
        for sub in [self.trust, self.storage, self.graph, self.cache]:
            sub_report = sub.run_all()
            report.add_many(sub_report.results)
        return report

    def run_quick(self) -> BenchmarkReport:
        report = BenchmarkReport("QuickBenchmark")
        t = TrustScoreBenchmark(iterations=2)
        report.add(t.run_single())
        s = StorageBenchmark(iterations=10)
        report.add_many(s.run_memory())
        g = GraphBenchmark(sizes=[10, 100])
        report.add_many(g.run_pagerank())
        c = CacheBenchmark(cache_size=50, iterations=100)
        report.add(c.run_hit_miss())
        return report
