"""Tests for isnad.benchmarking — 30+ tests covering all benchmark types."""

import json
import time

import pytest

from isnad.benchmarking import (
    BenchmarkReport,
    BenchmarkResult,
    BenchmarkSuite,
    CacheBenchmark,
    GraphBenchmark,
    StorageBenchmark,
    TrustScoreBenchmark,
    _bench,
    _measure,
)


# ─── BenchmarkResult ───────────────────────────────────────────────

class TestBenchmarkResult:
    def test_create(self):
        r = BenchmarkResult("op", 1.5, 100.0, 2.0)
        assert r.operation == "op"
        assert r.duration_ms == 1.5
        assert r.throughput_ops == 100.0
        assert r.memory_delta_kb == 2.0

    def test_defaults(self):
        r = BenchmarkResult("op", 1.0)
        assert r.throughput_ops == 0.0
        assert r.memory_delta_kb == 0.0

    def test_to_dict(self):
        r = BenchmarkResult("op", 1.5, 100.0, 2.0)
        d = r.to_dict()
        assert d["operation"] == "op"
        assert d["duration_ms"] == 1.5
        assert isinstance(d, dict)

    def test_to_dict_roundtrip_json(self):
        r = BenchmarkResult("test", 3.14, 50.0, 1.2)
        s = json.dumps(r.to_dict())
        d = json.loads(s)
        assert d["operation"] == "test"


# ─── BenchmarkReport ──────────────────────────────────────────────

class TestBenchmarkReport:
    def test_empty_report(self):
        rpt = BenchmarkReport("empty")
        assert rpt.summary()["count"] == 0

    def test_add_result(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("a", 10.0))
        assert len(rpt.results) == 1

    def test_add_many(self):
        rpt = BenchmarkReport("test")
        rpt.add_many([BenchmarkResult("a", 1.0), BenchmarkResult("b", 2.0)])
        assert len(rpt.results) == 2

    def test_summary_stats(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("a", 10.0))
        rpt.add(BenchmarkResult("b", 20.0))
        rpt.add(BenchmarkResult("c", 30.0))
        s = rpt.summary()
        assert s["count"] == 3
        assert s["mean_duration_ms"] == 20.0
        assert s["min_duration_ms"] == 10.0
        assert s["max_duration_ms"] == 30.0
        assert s["total_duration_ms"] == 60.0
        assert "stdev_duration_ms" in s

    def test_summary_single(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("a", 5.0))
        s = rpt.summary()
        assert "stdev_duration_ms" not in s

    def test_by_operation(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("read", 1.0))
        rpt.add(BenchmarkResult("write", 2.0))
        rpt.add(BenchmarkResult("read", 3.0))
        groups = rpt.by_operation()
        assert len(groups["read"]) == 2
        assert len(groups["write"]) == 1

    def test_format_table(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("op1", 1.5, 100.0, 0.5))
        table = rpt.format_table()
        assert "op1" in table
        assert "test" in table

    def test_format_table_empty(self):
        rpt = BenchmarkReport("empty")
        assert "No results" in rpt.format_table()

    def test_to_json(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("op1", 1.0))
        j = rpt.to_json()
        data = json.loads(j)
        assert data["name"] == "test"
        assert len(data["results"]) == 1
        assert "summary" in data

    def test_to_json_metadata(self):
        rpt = BenchmarkReport("test")
        rpt.metadata["version"] = "1.0"
        rpt.add(BenchmarkResult("x", 1.0))
        data = json.loads(rpt.to_json())
        assert data["metadata"]["version"] == "1.0"

    def test_compare(self):
        a = BenchmarkReport("before")
        a.add(BenchmarkResult("op1", 10.0))
        b = BenchmarkReport("after")
        b.add(BenchmarkResult("op1", 5.0))
        c = BenchmarkReport.compare(a, b)
        assert c["a_name"] == "before"
        assert c["operations"]["op1"]["speedup"] == 2.0

    def test_compare_disjoint_ops(self):
        a = BenchmarkReport("a")
        a.add(BenchmarkResult("only_a", 10.0))
        b = BenchmarkReport("b")
        b.add(BenchmarkResult("only_b", 5.0))
        c = BenchmarkReport.compare(a, b)
        assert "only_a" in c["operations"]
        assert "only_b" in c["operations"]
        assert "speedup" not in c["operations"]["only_a"]

    def test_summary_throughput(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("a", 1.0, 500.0))
        rpt.add(BenchmarkResult("b", 2.0, 300.0))
        s = rpt.summary()
        assert s["mean_throughput_ops"] == 400.0

    def test_summary_memory(self):
        rpt = BenchmarkReport("test")
        rpt.add(BenchmarkResult("a", 1.0, 0.0, 10.0))
        rpt.add(BenchmarkResult("b", 1.0, 0.0, 20.0))
        s = rpt.summary()
        assert s["total_memory_delta_kb"] == 30.0


# ─── Helpers ───────────────────────────────────────────────────────

class TestHelpers:
    def test_measure(self):
        result, ms, mem = _measure(sum, range(1000))
        assert result == 499500
        assert ms > 0

    def test_bench(self):
        r = _bench("add", sum, range(100), iterations=5)
        assert r.operation == "add"
        assert r.duration_ms > 0
        assert r.throughput_ops > 0


# ─── TrustScoreBenchmark ──────────────────────────────────────────

class TestTrustScoreBenchmark:
    def test_run_single(self):
        b = TrustScoreBenchmark(iterations=2)
        r = b.run_single()
        assert r.operation == "trust_score_single"
        assert r.duration_ms > 0

    def test_run_batch(self):
        b = TrustScoreBenchmark(iterations=2)
        r = b.run_batch(batch_size=5)
        assert r.operation == "trust_score_batch"
        assert r.duration_ms > 0

    def test_run_cached_vs_uncached(self):
        b = TrustScoreBenchmark(iterations=2)
        results = b.run_cached_vs_uncached()
        assert len(results) == 2
        assert results[0].operation == "trust_score_uncached"
        assert results[1].operation == "trust_score_cached"

    def test_run_all(self):
        b = TrustScoreBenchmark(iterations=2)
        rpt = b.run_all()
        assert rpt.name == "TrustScoreBenchmark"
        assert len(rpt.results) >= 4


# ─── StorageBenchmark ─────────────────────────────────────────────

class TestStorageBenchmark:
    def test_run_memory(self):
        b = StorageBenchmark(iterations=10)
        results = b.run_memory()
        assert len(results) == 2
        ops = [r.operation for r in results]
        assert "memory_write" in ops
        assert "memory_read" in ops

    def test_run_sqlite(self):
        b = StorageBenchmark(iterations=10)
        results = b.run_sqlite()
        assert len(results) == 2
        assert any("sqlite" in r.operation for r in results)

    def test_run_file(self):
        b = StorageBenchmark(iterations=10)
        results = b.run_file()
        assert len(results) == 2
        assert any("file" in r.operation for r in results)

    def test_run_all(self):
        b = StorageBenchmark(iterations=10)
        rpt = b.run_all()
        assert len(rpt.results) == 6

    def test_throughput_positive(self):
        b = StorageBenchmark(iterations=10)
        results = b.run_memory()
        for r in results:
            assert r.throughput_ops > 0


# ─── GraphBenchmark ───────────────────────────────────────────────

class TestGraphBenchmark:
    def test_run_pagerank(self):
        g = GraphBenchmark(sizes=[10, 50])
        results = g.run_pagerank()
        assert len(results) == 2
        assert "pagerank_n10" == results[0].operation

    def test_run_sybil(self):
        g = GraphBenchmark(sizes=[10])
        results = g.run_sybil()
        assert len(results) == 1
        assert "sybil_n10" == results[0].operation

    def test_run_communities(self):
        g = GraphBenchmark(sizes=[10, 50])
        results = g.run_communities()
        assert len(results) == 2

    def test_run_all(self):
        g = GraphBenchmark(sizes=[10, 50])
        rpt = g.run_all()
        assert rpt.name == "GraphBenchmark"
        assert len(rpt.results) == 6

    def test_default_sizes(self):
        g = GraphBenchmark()
        assert g.sizes == [10, 100, 1000, 10000]

    def test_pagerank_duration_scales(self):
        g = GraphBenchmark(sizes=[10, 100])
        results = g.run_pagerank()
        # Larger graph should generally take longer (not strictly enforced)
        assert all(r.duration_ms > 0 for r in results)


# ─── CacheBenchmark ───────────────────────────────────────────────

class TestCacheBenchmark:
    def test_run_hit_miss(self):
        c = CacheBenchmark(cache_size=50, iterations=100)
        r = c.run_hit_miss()
        assert r.operation == "cache_hit_miss"
        assert r.duration_ms > 0
        assert r.throughput_ops > 0

    def test_run_eviction(self):
        c = CacheBenchmark(cache_size=50, iterations=100)
        r = c.run_eviction()
        assert r.operation == "cache_eviction"
        assert r.duration_ms > 0

    def test_run_all(self):
        c = CacheBenchmark(cache_size=50, iterations=100)
        rpt = c.run_all()
        assert len(rpt.results) == 2


# ─── BenchmarkSuite ───────────────────────────────────────────────

class TestBenchmarkSuite:
    def test_run_quick(self):
        suite = BenchmarkSuite(graph_sizes=[10])
        rpt = suite.run_quick()
        assert rpt.name == "QuickBenchmark"
        assert len(rpt.results) >= 4

    def test_run_all_small(self):
        suite = BenchmarkSuite(
            trust_iterations=2,
            storage_iterations=5,
            graph_sizes=[10],
            cache_size=20,
            cache_iterations=50,
        )
        rpt = suite.run_all()
        assert rpt.name == "FullBenchmarkSuite"
        assert len(rpt.results) >= 10

    def test_suite_report_json(self):
        suite = BenchmarkSuite(
            trust_iterations=1,
            storage_iterations=5,
            graph_sizes=[10],
            cache_size=20,
            cache_iterations=50,
        )
        rpt = suite.run_all()
        data = json.loads(rpt.to_json())
        assert "results" in data
        assert "summary" in data
