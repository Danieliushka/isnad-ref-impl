"""Tests for isnad.benchmark module."""

import json
import time

import pytest

from isnad.benchmark import BenchmarkResult, BenchmarkReport, BenchmarkSuite, _bench


class TestBenchmarkResult:
    def test_basic_properties(self):
        r = BenchmarkResult(name="test", iterations=100, total_seconds=1.0, latencies_ms=[10.0] * 100)
        assert r.ops_per_second == 100.0
        assert r.mean_ms == 10.0
        assert r.median_ms == 10.0
        assert r.p95_ms == 10.0
        assert r.p99_ms == 10.0
        assert r.stdev_ms == 0.0

    def test_varied_latencies(self):
        lats = [float(x) for x in range(1, 101)]
        r = BenchmarkResult(name="varied", iterations=100, total_seconds=5.05, latencies_ms=lats)
        assert r.ops_per_second == pytest.approx(100 / 5.05, rel=0.01)
        assert r.mean_ms == pytest.approx(50.5, rel=0.01)
        assert r.median_ms == pytest.approx(50.5, rel=0.01)
        assert r.p95_ms >= 95.0
        assert r.p99_ms >= 99.0
        assert r.stdev_ms > 0

    def test_zero_total_seconds(self):
        r = BenchmarkResult(name="fast", iterations=10, total_seconds=0.0, latencies_ms=[0.001] * 10)
        assert r.ops_per_second == float("inf")

    def test_empty_latencies(self):
        r = BenchmarkResult(name="empty", iterations=0, total_seconds=0.0)
        assert r.mean_ms == 0.0
        assert r.median_ms == 0.0
        assert r.p95_ms == 0.0
        assert r.p99_ms == 0.0
        assert r.stdev_ms == 0.0

    def test_single_latency(self):
        r = BenchmarkResult(name="single", iterations=1, total_seconds=0.005, latencies_ms=[5.0])
        assert r.mean_ms == 5.0
        assert r.stdev_ms == 0.0

    def test_to_dict(self):
        r = BenchmarkResult(name="test", iterations=50, total_seconds=1.0, latencies_ms=[2.0] * 50)
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["iterations"] == 50
        assert d["ops_per_second"] == 50.0
        assert d["mean_ms"] == 2.0
        assert "p95_ms" in d
        assert "p99_ms" in d
        assert "stdev_ms" in d


class TestBenchmarkReport:
    def test_add_and_summary(self):
        report = BenchmarkReport()
        r1 = BenchmarkResult(name="bench1", iterations=100, total_seconds=0.5, latencies_ms=[5.0] * 100)
        r2 = BenchmarkResult(name="bench2", iterations=200, total_seconds=1.0, latencies_ms=[5.0] * 200)
        report.add(r1)
        report.add(r2)
        assert len(report.results) == 2
        summary = report.summary()
        assert "bench1" in summary
        assert "bench2" in summary
        assert "ops/s" in summary

    def test_metadata_in_summary(self):
        report = BenchmarkReport(metadata={"version": "1.0"})
        summary = report.summary()
        assert "version" in summary

    def test_to_dict(self):
        report = BenchmarkReport(metadata={"test": True})
        report.add(BenchmarkResult(name="b", iterations=10, total_seconds=0.1, latencies_ms=[10.0] * 10))
        d = report.to_dict()
        assert d["metadata"]["test"] is True
        assert len(d["results"]) == 1
        json.dumps(d)

    def test_empty_report(self):
        report = BenchmarkReport()
        summary = report.summary()
        assert "Benchmark Report" in summary
        assert report.to_dict()["results"] == []


class TestBenchFunction:
    def test_basic_bench(self):
        counter = {"n": 0}
        def fn():
            counter["n"] += 1
        result = _bench("counter", fn, iterations=50, warmup=10)
        assert result.name == "counter"
        assert result.iterations == 50
        assert counter["n"] == 60
        assert len(result.latencies_ms) == 50
        assert result.total_seconds > 0

    def test_slow_function(self):
        def fn():
            time.sleep(0.001)
        result = _bench("slow", fn, iterations=10, warmup=2)
        assert result.mean_ms >= 0.5
        assert result.iterations == 10


class TestBenchmarkSuite:
    @pytest.fixture
    def suite(self):
        return BenchmarkSuite(iterations=50, warmup=10)

    def test_attestation_create(self, suite):
        r = suite.bench_attestation_create()
        assert r.name == "attestation_create"
        assert r.iterations == 50
        assert r.ops_per_second > 0
        assert r.mean_ms > 0

    def test_chain_add(self, suite):
        r = suite.bench_chain_add()
        assert r.name == "chain_add"
        assert r.ops_per_second > 0

    def test_chain_score(self, suite):
        r = suite.bench_chain_score()
        assert "chain_score" in r.name
        assert r.ops_per_second > 0

    def test_chain_trust(self, suite):
        r = suite.bench_chain_trust()
        assert "chain_trust" in r.name
        assert r.ops_per_second > 0

    def test_attestation_lookup(self, suite):
        r = suite.bench_attestation_lookup()
        assert "attestation_lookup" in r.name
        assert r.ops_per_second > 0

    def test_scalability(self, suite):
        results = suite.bench_scalability(sizes=[10, 50, 100])
        assert len(results) == 3
        assert "10" in results[0].name
        assert "100" in results[2].name
        for r in results:
            assert r.ops_per_second > 0

    def test_run_all(self, suite):
        report = suite.run_all()
        assert len(report.results) >= 8
        assert report.metadata["iterations"] == 50
        summary = report.summary()
        assert "attestation_create" in summary
        assert "chain_add" in summary

    def test_custom_scalability_sizes(self, suite):
        results = suite.bench_scalability(sizes=[5, 20])
        assert len(results) == 2

    def test_report_json_serializable(self, suite):
        report = suite.run_all()
        d = report.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 0


class TestBenchmarkIntegration:
    def test_full_pipeline(self):
        suite = BenchmarkSuite(iterations=20, warmup=5)
        report = suite.run_all()
        assert len(report.results) > 0
        for r in report.results:
            assert r.ops_per_second > 0
            assert r.mean_ms >= 0
        summary = report.summary()
        assert len(summary) > 100

    def test_benchmark_result_consistency(self):
        suite = BenchmarkSuite(iterations=100, warmup=10)
        r = suite.bench_attestation_create()
        latency_sum_s = sum(r.latencies_ms) / 1000
        assert latency_sum_s <= r.total_seconds * 1.5
