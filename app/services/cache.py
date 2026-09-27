"""In-process TTL cache for WikiAura analytics results.

Design decisions:
- In-memory (no Redis) — stateless FastAPI container, single process.
- TTL = 6 hours — Wikimedia pageview data is updated once per day; 6h is conservative.
- Cache key = (topic, languages_tuple, start_date, end_date, granularity, include_ai_summary).
- Thread-safe via asyncio.Lock — all access is from async FastAPI handlers.
- Capacity-limited (LRU eviction) to prevent unbounded memory growth.
- Public interface: get / set / invalidate / clear / stats.
- Designed for drop-in Redis replacement: only the store backend needs to change.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

from app.schemas.analytics import AnalyticsResultDTO

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_TTL_SECONDS: int = 6 * 3600          # 6 hours
DEFAULT_MAX_ENTRIES: int = 256               # max cache entries before LRU eviction


# ── Cache Key ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CacheKey:
    """Immutable, hashable key representing a unique analytics request."""

    topic: str
    language_codes: tuple[str, ...]          # sorted for canonical form
    start_date: str
    end_date: str
    granularity: str
    include_ai_summary: bool

    @classmethod
    def build(
        cls,
        topic: str,
        language_codes: list[str],
        start_date: str,
        end_date: str,
        granularity: str,
        include_ai_summary: bool,
    ) -> "CacheKey":
        """Construct a canonical cache key from mutable inputs."""
        return cls(
            topic=topic.strip().lower(),
            language_codes=tuple(sorted(set(lc.strip().lower() for lc in language_codes))),
            start_date=start_date.replace("-", "")[:8],   # normalise YYYY-MM-DD → YYYYMMDD
            end_date=end_date.replace("-", "")[:8],
            granularity=granularity.lower(),
            include_ai_summary=include_ai_summary,
        )

    def __str__(self) -> str:
        langs = ",".join(self.language_codes)
        return (
            f"{self.topic}|{langs}|{self.start_date}-{self.end_date}"
            f"|{self.granularity}|ai={self.include_ai_summary}"
        )


# ── Internal Entry ─────────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    result: AnalyticsResultDTO
    stored_at: float = field(default_factory=time.monotonic)
    hit_count: int = 0

    def is_expired(self, ttl: int) -> bool:
        return (time.monotonic() - self.stored_at) > ttl

    def age_seconds(self) -> float:
        return time.monotonic() - self.stored_at


# ── Stats DTO ──────────────────────────────────────────────────────────────────


@dataclass
class CacheStatsDTO:
    """Public cache statistics snapshot."""

    total_entries: int
    max_entries: int
    ttl_seconds: int
    hits: int
    misses: int
    hit_rate_percent: float
    evictions: int
    oldest_entry_age_seconds: Optional[float]
    estimated_memory_kb: float


# ── Cache ──────────────────────────────────────────────────────────────────────


class WikiAuraCache:
    """Thread-safe in-memory TTL cache for AnalyticsResultDTO objects.

    Uses an OrderedDict for O(1) LRU eviction. Access is serialised
    through a single asyncio.Lock so callers never see torn state.

    Example usage:
        cache = WikiAuraCache()

        key = CacheKey.build(topic="Coffee", language_codes=["en", "uk"],
                             start_date="20230101", end_date="20231231",
                             granularity="monthly", include_ai_summary=True)

        cached = await cache.get(key)
        if cached is None:
            result = await expensive_fetch()
            await cache.set(key, result)
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: OrderedDict[CacheKey, _CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    async def get(self, key: CacheKey) -> Optional[AnalyticsResultDTO]:
        """Return cached result or None if missing / expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                logger.debug("Cache MISS  key=%s", key)
                return None
            if entry.is_expired(self._ttl):
                del self._store[key]
                self._misses += 1
                logger.debug("Cache EXPIRED  key=%s  age=%.0fs", key, entry.age_seconds())
                return None
            # LRU: move to end (most recently used)
            self._store.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            logger.info(
                "Cache HIT  key=%s  age=%.0fs  hits=%d",
                key, entry.age_seconds(), entry.hit_count,
            )
            return entry.result

    async def set(self, key: CacheKey, result: AnalyticsResultDTO) -> None:
        """Store result; evict LRU entry if capacity is exceeded."""
        async with self._lock:
            if key in self._store:
                # Refresh existing entry
                self._store.move_to_end(key)
                self._store[key] = _CacheEntry(result=result)
                logger.debug("Cache REFRESH  key=%s", key)
                return

            if len(self._store) >= self._max:
                oldest_key, _ = self._store.popitem(last=False)
                self._evictions += 1
                logger.info("Cache EVICT (LRU)  key=%s", oldest_key)

            self._store[key] = _CacheEntry(result=result)
            logger.debug("Cache SET  key=%s  total=%d", key, len(self._store))

    async def invalidate(self, topic: str) -> int:
        """Remove all cache entries whose topic matches (case-insensitive).

        Returns the number of entries removed.
        """
        normalised = topic.strip().lower()
        async with self._lock:
            keys_to_delete = [k for k in self._store if k.topic == normalised]
            for k in keys_to_delete:
                del self._store[k]
            if keys_to_delete:
                logger.info("Cache INVALIDATE  topic=%s  removed=%d", topic, len(keys_to_delete))
            return len(keys_to_delete)

    async def clear(self) -> int:
        """Remove all entries. Returns count removed."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            logger.info("Cache CLEAR  removed=%d", count)
            return count

    async def stats(self) -> CacheStatsDTO:
        """Return a point-in-time stats snapshot."""
        async with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            oldest_age: Optional[float] = None
            if self._store:
                oldest_entry = next(iter(self._store.values()))
                oldest_age = oldest_entry.age_seconds()

            # Rough memory estimate: sum of pickled result sizes
            mem_kb = sum(
                sys.getsizeof(e.result.model_dump_json())
                for e in self._store.values()
            ) / 1024

            return CacheStatsDTO(
                total_entries=len(self._store),
                max_entries=self._max,
                ttl_seconds=self._ttl,
                hits=self._hits,
                misses=self._misses,
                hit_rate_percent=round(hit_rate, 2),
                evictions=self._evictions,
                oldest_entry_age_seconds=oldest_age,
                estimated_memory_kb=round(mem_kb, 2),
            )


# ── Singleton ──────────────────────────────────────────────────────────────────

# Application-wide shared cache instance.
# Imported by facade and cache API router.
analytics_cache = WikiAuraCache(
    ttl_seconds=DEFAULT_TTL_SECONDS,
    max_entries=DEFAULT_MAX_ENTRIES,
)
