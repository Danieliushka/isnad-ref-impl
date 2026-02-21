"""
isnad.caching — Performance caching layer for trust operations.

Multi-tier cache: L1 (in-memory LRU) → L2 (optional persistent).
TTL-aware, invalidation-aware, namespace-scoped.
Designed for high-frequency trust score lookups and attestation verification.
"""

import time
import threading
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Dict, List, Set, Tuple
from enum import Enum


class CachePolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"           # Least Recently Used
    LFU = "lfu"           # Least Frequently Used
    TTL_ONLY = "ttl_only" # No eviction, TTL expiry only


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    key: str
    value: Any
    created_at: float
    expires_at: Optional[float]
    access_count: int = 0
    last_accessed: float = 0.0
    namespace: str = "default"
    tags: Set[str] = field(default_factory=set)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self):
        self.last_accessed = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    sets: int = 0
    invalidations: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "sets": self.sets,
            "invalidations": self.invalidations,
            "hit_rate": round(self.hit_rate, 4),
        }


class LRUCache:
    """
    Thread-safe LRU cache with TTL support and namespace scoping.

    Features:
    - Configurable max size with LRU/LFU eviction
    - Per-entry TTL
    - Namespace isolation
    - Tag-based bulk invalidation
    - Performance statistics
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: Optional[float] = 300.0,  # 5 minutes
        policy: CachePolicy = CachePolicy.LRU,
    ):
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if default_ttl is not None and default_ttl <= 0:
            raise ValueError("default_ttl must be positive or None")

        self._max_size = max_size
        self._default_ttl = default_ttl
        self._policy = policy
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        return self._stats

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def _make_key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    def get(
        self,
        key: str,
        namespace: str = "default",
        default: Any = None,
    ) -> Any:
        """Get value from cache. Returns default if not found or expired."""
        full_key = self._make_key(namespace, key)

        with self._lock:
            entry = self._entries.get(full_key)
            if entry is None:
                self._stats.misses += 1
                return default

            if entry.is_expired:
                del self._entries[full_key]
                self._stats.expirations += 1
                self._stats.misses += 1
                return default

            entry.touch()
            if self._policy == CachePolicy.LRU:
                self._entries.move_to_end(full_key)
            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl: Optional[float] = None,
        tags: Optional[Set[str]] = None,
    ) -> None:
        """Set value in cache with optional TTL and tags."""
        full_key = self._make_key(namespace, key)
        now = time.time()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = now + effective_ttl if effective_ttl is not None else None

        entry = CacheEntry(
            key=full_key,
            value=value,
            created_at=now,
            expires_at=expires_at,
            last_accessed=now,
            namespace=namespace,
            tags=tags or set(),
        )

        with self._lock:
            if full_key in self._entries:
                del self._entries[full_key]

            self._entries[full_key] = entry
            self._stats.sets += 1

            while len(self._entries) > self._max_size:
                self._evict()

    def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete specific entry. Returns True if found."""
        full_key = self._make_key(namespace, key)
        with self._lock:
            if full_key in self._entries:
                del self._entries[full_key]
                self._stats.invalidations += 1
                return True
            return False

    def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all entries with given tag. Returns count."""
        with self._lock:
            to_delete = [
                k for k, v in self._entries.items() if tag in v.tags
            ]
            for k in to_delete:
                del self._entries[k]
            self._stats.invalidations += len(to_delete)
            return len(to_delete)

    def invalidate_namespace(self, namespace: str) -> int:
        """Invalidate all entries in namespace. Returns count."""
        with self._lock:
            to_delete = [
                k for k, v in self._entries.items() if v.namespace == namespace
            ]
            for k in to_delete:
                del self._entries[k]
            self._stats.invalidations += len(to_delete)
            return len(to_delete)

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._stats.invalidations += count

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        with self._lock:
            expired = [
                k for k, v in self._entries.items() if v.is_expired
            ]
            for k in expired:
                del self._entries[k]
            self._stats.expirations += len(expired)
            return len(expired)

    def _evict(self) -> None:
        """Evict one entry based on policy."""
        if not self._entries:
            return

        if self._policy == CachePolicy.LRU:
            self._entries.popitem(last=False)
        elif self._policy == CachePolicy.LFU:
            min_key = min(self._entries, key=lambda k: self._entries[k].access_count)
            del self._entries[min_key]
        else:  # TTL_ONLY
            oldest = min(self._entries, key=lambda k: self._entries[k].created_at)
            del self._entries[oldest]

        self._stats.evictions += 1

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        namespace: str = "default",
        ttl: Optional[float] = None,
        tags: Optional[Set[str]] = None,
    ) -> Any:
        """Get from cache or compute and cache the result."""
        value = self.get(key, namespace)
        if value is not None:
            return value

        value = factory()
        if value is not None:
            self.set(key, value, namespace, ttl, tags)
        return value


class TrustScoreCache:
    """
    Specialized cache for trust score lookups.

    Optimized for the trust score access pattern:
    - Agent → score lookups (high frequency)
    - Score invalidation on new attestation
    - Namespace per scoring context
    """

    def __init__(
        self,
        max_size: int = 5000,
        score_ttl: float = 600.0,  # 10 min
        chain_ttl: float = 300.0,   # 5 min for chain verification
    ):
        self._score_cache = LRUCache(max_size=max_size, default_ttl=score_ttl)
        self._chain_cache = LRUCache(max_size=max_size // 2, default_ttl=chain_ttl)
        self._verification_cache = LRUCache(max_size=max_size, default_ttl=chain_ttl * 2)

    def get_score(self, agent_did: str, context: str = "global") -> Optional[float]:
        """Get cached trust score for agent."""
        return self._score_cache.get(agent_did, namespace=f"score:{context}")

    def set_score(
        self,
        agent_did: str,
        score: float,
        context: str = "global",
        ttl: Optional[float] = None,
    ) -> None:
        """Cache trust score for agent."""
        self._score_cache.set(
            agent_did, score,
            namespace=f"score:{context}",
            ttl=ttl,
            tags={f"agent:{agent_did}"},
        )

    def invalidate_agent(self, agent_did: str) -> int:
        """Invalidate all cached data for an agent (new attestation, etc)."""
        count = self._score_cache.invalidate_by_tag(f"agent:{agent_did}")
        count += self._chain_cache.invalidate_by_tag(f"agent:{agent_did}")
        count += self._verification_cache.invalidate_by_tag(f"agent:{agent_did}")
        return count

    def get_chain_verification(self, chain_hash: str) -> Optional[bool]:
        """Get cached chain verification result."""
        return self._chain_cache.get(chain_hash, namespace="chain_verify")

    def set_chain_verification(
        self,
        chain_hash: str,
        is_valid: bool,
        agent_did: Optional[str] = None,
    ) -> None:
        """Cache chain verification result."""
        tags = set()
        if agent_did:
            tags.add(f"agent:{agent_did}")
        self._chain_cache.set(
            chain_hash, is_valid,
            namespace="chain_verify",
            tags=tags,
        )

    def get_attestation_verified(self, attestation_id: str) -> Optional[bool]:
        """Get cached attestation verification."""
        return self._verification_cache.get(attestation_id, namespace="attest_verify")

    def set_attestation_verified(
        self,
        attestation_id: str,
        is_valid: bool,
        agent_did: Optional[str] = None,
    ) -> None:
        """Cache attestation verification result."""
        tags = set()
        if agent_did:
            tags.add(f"agent:{agent_did}")
        self._verification_cache.set(
            attestation_id, is_valid,
            namespace="attest_verify",
            tags=tags,
        )

    @property
    def stats(self) -> dict:
        return {
            "scores": self._score_cache.stats.to_dict(),
            "chains": self._chain_cache.stats.to_dict(),
            "verifications": self._verification_cache.stats.to_dict(),
        }

    def cleanup(self) -> int:
        """Cleanup expired entries across all caches."""
        count = self._score_cache.cleanup_expired()
        count += self._chain_cache.cleanup_expired()
        count += self._verification_cache.cleanup_expired()
        return count


class CacheWarmer:
    """
    Pre-populate cache with frequently accessed data.

    Use during startup or periodic refresh to reduce cold-start latency.
    """

    def __init__(self, cache: TrustScoreCache):
        self._cache = cache
        self._warmup_functions: List[Tuple[str, Callable]] = []

    def register(self, name: str, fn: Callable[[], Dict[str, float]]) -> None:
        """Register a warmup function that returns {agent_did: score}."""
        self._warmup_functions.append((name, fn))

    def warm(self, context: str = "global") -> Dict[str, int]:
        """Run all warmup functions. Returns {name: count_warmed}."""
        results = {}
        for name, fn in self._warmup_functions:
            try:
                scores = fn()
                for agent_did, score in scores.items():
                    self._cache.set_score(agent_did, score, context=context)
                results[name] = len(scores)
            except Exception:
                results[name] = 0
        return results


def make_cache_key(*args: Any) -> str:
    """Create deterministic cache key from arguments."""
    raw = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
