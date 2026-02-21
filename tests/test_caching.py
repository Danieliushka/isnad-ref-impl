"""Tests for isnad.caching — performance caching layer."""

import time
import threading
import pytest
from isnad.caching import (
    LRUCache, CachePolicy, CacheEntry, CacheStats,
    TrustScoreCache, CacheWarmer, make_cache_key,
)


class TestCacheEntry:
    def test_not_expired_without_ttl(self):
        e = CacheEntry(key="k", value="v", created_at=time.time(), expires_at=None)
        assert not e.is_expired

    def test_not_expired_within_ttl(self):
        e = CacheEntry(key="k", value="v", created_at=time.time(), expires_at=time.time() + 100)
        assert not e.is_expired

    def test_expired(self):
        e = CacheEntry(key="k", value="v", created_at=time.time(), expires_at=time.time() - 1)
        assert e.is_expired

    def test_touch(self):
        e = CacheEntry(key="k", value="v", created_at=time.time(), expires_at=None)
        assert e.access_count == 0
        e.touch()
        assert e.access_count == 1
        assert e.last_accessed > 0


class TestCacheStats:
    def test_hit_rate_empty(self):
        s = CacheStats()
        assert s.hit_rate == 0.0

    def test_hit_rate(self):
        s = CacheStats(hits=3, misses=1)
        assert s.hit_rate == 0.75

    def test_to_dict(self):
        s = CacheStats(hits=10, misses=5)
        d = s.to_dict()
        assert d["hits"] == 10
        assert d["misses"] == 5
        assert "hit_rate" in d


class TestLRUCache:
    def test_get_set(self):
        c = LRUCache(max_size=10)
        c.set("a", 1)
        assert c.get("a") == 1

    def test_miss(self):
        c = LRUCache(max_size=10)
        assert c.get("missing") is None
        assert c.get("missing", default=42) == 42

    def test_ttl_expiry(self):
        c = LRUCache(max_size=10, default_ttl=0.05)
        c.set("a", 1)
        assert c.get("a") == 1
        time.sleep(0.06)
        assert c.get("a") is None

    def test_custom_ttl(self):
        c = LRUCache(max_size=10, default_ttl=100)
        c.set("a", 1, ttl=0.05)
        time.sleep(0.06)
        assert c.get("a") is None

    def test_no_ttl(self):
        c = LRUCache(max_size=10, default_ttl=None)
        c.set("a", 1)
        assert c.get("a") == 1

    def test_lru_eviction(self):
        c = LRUCache(max_size=3)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.set("d", 4)  # should evict "a"
        assert c.get("a") is None
        assert c.get("d") == 4

    def test_lru_access_preserves(self):
        c = LRUCache(max_size=3)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.get("a")  # touch a, b is now LRU
        c.set("d", 4)  # should evict "b"
        assert c.get("a") == 1
        assert c.get("b") is None

    def test_lfu_eviction(self):
        c = LRUCache(max_size=3, policy=CachePolicy.LFU)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.get("a")  # a.access_count = 1
        c.get("a")  # a.access_count = 2
        c.get("b")  # b.access_count = 1
        c.set("d", 4)  # evict c (access_count = 0)
        assert c.get("c") is None
        assert c.get("a") == 1

    def test_ttl_only_eviction(self):
        c = LRUCache(max_size=2, policy=CachePolicy.TTL_ONLY)
        c.set("a", 1)
        time.sleep(0.01)
        c.set("b", 2)
        c.set("c", 3)  # evicts oldest = a
        assert c.get("a") is None
        assert c.get("b") == 2

    def test_namespace_isolation(self):
        c = LRUCache(max_size=10)
        c.set("k", 1, namespace="ns1")
        c.set("k", 2, namespace="ns2")
        assert c.get("k", namespace="ns1") == 1
        assert c.get("k", namespace="ns2") == 2

    def test_delete(self):
        c = LRUCache(max_size=10)
        c.set("a", 1)
        assert c.delete("a")
        assert c.get("a") is None
        assert not c.delete("nonexistent")

    def test_invalidate_by_tag(self):
        c = LRUCache(max_size=10)
        c.set("a", 1, tags={"agent:alice"})
        c.set("b", 2, tags={"agent:alice"})
        c.set("c", 3, tags={"agent:bob"})
        count = c.invalidate_by_tag("agent:alice")
        assert count == 2
        assert c.get("a") is None
        assert c.get("c") == 3

    def test_invalidate_namespace(self):
        c = LRUCache(max_size=10)
        c.set("a", 1, namespace="ns1")
        c.set("b", 2, namespace="ns1")
        c.set("c", 3, namespace="ns2")
        count = c.invalidate_namespace("ns1")
        assert count == 2
        assert c.get("c", namespace="ns2") == 3

    def test_clear(self):
        c = LRUCache(max_size=10)
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.size == 0

    def test_cleanup_expired(self):
        c = LRUCache(max_size=10, default_ttl=0.05)
        c.set("a", 1)
        c.set("b", 2, ttl=100)
        time.sleep(0.06)
        removed = c.cleanup_expired()
        assert removed == 1
        assert c.get("b") == 2

    def test_get_or_set(self):
        c = LRUCache(max_size=10)
        calls = []
        def factory():
            calls.append(1)
            return 42
        assert c.get_or_set("k", factory) == 42
        assert c.get_or_set("k", factory) == 42
        assert len(calls) == 1  # factory called once

    def test_get_or_set_none_not_cached(self):
        c = LRUCache(max_size=10)
        calls = []
        def factory():
            calls.append(1)
            return None
        result = c.get_or_set("k", factory)
        assert result is None
        assert len(calls) == 1

    def test_overwrite(self):
        c = LRUCache(max_size=10)
        c.set("a", 1)
        c.set("a", 2)
        assert c.get("a") == 2
        assert c.size == 1

    def test_stats(self):
        c = LRUCache(max_size=10)
        c.set("a", 1)
        c.get("a")
        c.get("miss")
        assert c.stats.hits == 1
        assert c.stats.misses == 1
        assert c.stats.sets == 1

    def test_invalid_max_size(self):
        with pytest.raises(ValueError):
            LRUCache(max_size=0)

    def test_invalid_ttl(self):
        with pytest.raises(ValueError):
            LRUCache(default_ttl=-1)

    def test_thread_safety(self):
        c = LRUCache(max_size=100)
        errors = []

        def writer(start):
            try:
                for i in range(100):
                    c.set(f"k{start+i}", i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    c.get(f"k{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(0,)),
            threading.Thread(target=writer, args=(100,)),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_size_property(self):
        c = LRUCache(max_size=10)
        assert c.size == 0
        c.set("a", 1)
        assert c.size == 1


class TestTrustScoreCache:
    def test_score_set_get(self):
        tc = TrustScoreCache()
        tc.set_score("did:isnad:alice", 0.85)
        assert tc.get_score("did:isnad:alice") == 0.85

    def test_score_context_isolation(self):
        tc = TrustScoreCache()
        tc.set_score("did:isnad:alice", 0.85, context="commerce")
        tc.set_score("did:isnad:alice", 0.60, context="social")
        assert tc.get_score("did:isnad:alice", context="commerce") == 0.85
        assert tc.get_score("did:isnad:alice", context="social") == 0.60

    def test_score_miss(self):
        tc = TrustScoreCache()
        assert tc.get_score("did:isnad:unknown") is None

    def test_invalidate_agent(self):
        tc = TrustScoreCache()
        tc.set_score("did:isnad:alice", 0.85)
        tc.set_chain_verification("chain1", True, agent_did="did:isnad:alice")
        tc.set_attestation_verified("att1", True, agent_did="did:isnad:alice")
        count = tc.invalidate_agent("did:isnad:alice")
        assert count == 3
        assert tc.get_score("did:isnad:alice") is None
        assert tc.get_chain_verification("chain1") is None
        assert tc.get_attestation_verified("att1") is None

    def test_chain_verification(self):
        tc = TrustScoreCache()
        tc.set_chain_verification("hash1", True)
        assert tc.get_chain_verification("hash1") is True
        tc.set_chain_verification("hash2", False)
        assert tc.get_chain_verification("hash2") is False

    def test_attestation_verification(self):
        tc = TrustScoreCache()
        tc.set_attestation_verified("att1", True)
        assert tc.get_attestation_verified("att1") is True

    def test_stats(self):
        tc = TrustScoreCache()
        tc.set_score("a", 1.0)
        tc.get_score("a")
        tc.get_score("miss")
        s = tc.stats
        assert "scores" in s
        assert "chains" in s
        assert "verifications" in s

    def test_cleanup(self):
        tc = TrustScoreCache(score_ttl=0.05)
        tc.set_score("a", 1.0)
        time.sleep(0.06)
        removed = tc.cleanup()
        assert removed >= 1

    def test_custom_ttl(self):
        tc = TrustScoreCache()
        tc.set_score("a", 1.0, ttl=0.05)
        time.sleep(0.06)
        assert tc.get_score("a") is None

    def test_chain_without_agent(self):
        tc = TrustScoreCache()
        tc.set_chain_verification("h", True)
        assert tc.get_chain_verification("h") is True

    def test_attestation_without_agent(self):
        tc = TrustScoreCache()
        tc.set_attestation_verified("a", False)
        assert tc.get_attestation_verified("a") is False


class TestCacheWarmer:
    def test_warm(self):
        tc = TrustScoreCache()
        warmer = CacheWarmer(tc)

        def top_agents():
            return {"alice": 0.9, "bob": 0.7}

        warmer.register("top", top_agents)
        results = warmer.warm()
        assert results["top"] == 2
        assert tc.get_score("alice") == 0.9

    def test_warm_error_handling(self):
        tc = TrustScoreCache()
        warmer = CacheWarmer(tc)

        def failing():
            raise RuntimeError("boom")

        warmer.register("bad", failing)
        results = warmer.warm()
        assert results["bad"] == 0

    def test_multiple_warmers(self):
        tc = TrustScoreCache()
        warmer = CacheWarmer(tc)
        warmer.register("a", lambda: {"x": 1.0})
        warmer.register("b", lambda: {"y": 2.0})
        results = warmer.warm()
        assert results["a"] == 1
        assert results["b"] == 1


class TestMakeCacheKey:
    def test_deterministic(self):
        k1 = make_cache_key("a", 1, {"x": 2})
        k2 = make_cache_key("a", 1, {"x": 2})
        assert k1 == k2

    def test_different_inputs(self):
        k1 = make_cache_key("a")
        k2 = make_cache_key("b")
        assert k1 != k2

    def test_length(self):
        k = make_cache_key("test")
        assert len(k) == 16
