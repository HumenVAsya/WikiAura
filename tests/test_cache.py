"""Unit and integration tests for the WikiAura in-memory cache."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.schemas.analytics import (
    AnalyticsResultDTO,
    LanguageAnalyticsDTO,
)
from app.services.cache import (
    CacheKey,
    WikiAuraCache,
    DEFAULT_TTL_SECONDS,
    DEFAULT_MAX_ENTRIES,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_result(topic: str = "Coffee", lang: str = "en") -> AnalyticsResultDTO:
    return AnalyticsResultDTO(
        topic=topic,
        granularity="monthly",
        start_date="20230101",
        end_date="20231231",
        languages={lang: LanguageAnalyticsDTO(language=lang, found=True)},
    )


def _make_key(
    topic: str = "Coffee",
    langs: list[str] | None = None,
    start: str = "20230101",
    end: str = "20231231",
    granularity: str = "monthly",
    ai: bool = True,
) -> CacheKey:
    return CacheKey.build(
        topic=topic,
        language_codes=langs or ["en"],
        start_date=start,
        end_date=end,
        granularity=granularity,
        include_ai_summary=ai,
    )


# ── CacheKey Tests ─────────────────────────────────────────────────────────────


class TestCacheKey:
    def test_canonical_topic_lowercase(self):
        key = _make_key(topic="Coffee")
        assert key.topic == "coffee"

    def test_canonical_lang_sorted(self):
        key = _make_key(langs=["pl", "en", "uk"])
        assert key.language_codes == ("en", "pl", "uk")

    def test_canonical_date_normalisation(self):
        """YYYY-MM-DD and YYYYMMDD formats must produce the same key."""
        key1 = _make_key(start="2023-01-01", end="2023-12-31")
        key2 = _make_key(start="20230101", end="20231231")
        assert key1 == key2

    def test_duplicate_langs_deduplicated(self):
        key = _make_key(langs=["en", "en", "uk"])
        assert key.language_codes == ("en", "uk")

    def test_different_topics_different_keys(self):
        assert _make_key(topic="Coffee") != _make_key(topic="Tea")

    def test_different_dates_different_keys(self):
        assert _make_key(start="20230101") != _make_key(start="20220101")

    def test_different_ai_flags_different_keys(self):
        assert _make_key(ai=True) != _make_key(ai=False)

    def test_str_representation(self):
        key = _make_key()
        s = str(key)
        assert "coffee" in s
        assert "en" in s

    def test_hashable_usable_as_dict_key(self):
        d = {_make_key(): "value"}
        assert d[_make_key()] == "value"


# ── Cache Get/Set Tests ────────────────────────────────────────────────────────


class TestWikiAuraCache:
    @pytest.fixture
    def cache(self):
        return WikiAuraCache(ttl_seconds=60, max_entries=10)

    @pytest.mark.asyncio
    async def test_miss_on_empty_cache(self, cache):
        key = _make_key()
        result = await cache.get(key)
        assert result is None

    @pytest.mark.asyncio
    async def test_hit_after_set(self, cache):
        key = _make_key()
        result = _make_result()
        await cache.set(key, result)
        cached = await cache.get(key)
        assert cached is not None
        assert cached.topic == result.topic

    @pytest.mark.asyncio
    async def test_miss_after_expiry(self):
        """Entry expired by TTL should return None."""
        cache = WikiAuraCache(ttl_seconds=0)  # immediate expiry
        key = _make_key()
        result = _make_result()
        await cache.set(key, result)
        # Force entry to look old by patching stored_at
        async with cache._lock:
            cache._store[key].stored_at = time.monotonic() - 1  # 1s ago > ttl 0

        cached = await cache.get(key)
        assert cached is None

    @pytest.mark.asyncio
    async def test_different_keys_independent(self, cache):
        key1 = _make_key(topic="Coffee")
        key2 = _make_key(topic="Tea")
        await cache.set(key1, _make_result(topic="Coffee"))
        await cache.set(key2, _make_result(topic="Tea"))

        c1 = await cache.get(key1)
        c2 = await cache.get(key2)
        assert c1.topic == "Coffee"
        assert c2.topic == "Tea"

    @pytest.mark.asyncio
    async def test_refresh_updates_entry(self, cache):
        """Calling set on an existing key replaces the entry."""
        key = _make_key()
        await cache.set(key, _make_result(topic="Coffee"))
        new_result = _make_result(topic="Coffee")
        new_result.source_topic = "Kava"
        await cache.set(key, new_result)
        cached = await cache.get(key)
        assert cached.source_topic == "Kava"

    @pytest.mark.asyncio
    async def test_lru_eviction_when_full(self):
        """When capacity is reached, the least-recently-used entry is evicted."""
        cache = WikiAuraCache(ttl_seconds=3600, max_entries=3)
        keys = [_make_key(topic=f"topic{i}") for i in range(3)]
        results = [_make_result(topic=f"topic{i}") for i in range(3)]

        for k, r in zip(keys, results):
            await cache.set(k, r)

        # Access key[0] to make it recently used
        await cache.get(keys[0])

        # Insert a 4th entry — should evict key[1] (oldest that wasn't accessed)
        new_key = _make_key(topic="topic99")
        await cache.set(new_key, _make_result(topic="topic99"))

        assert await cache.get(keys[0]) is not None, "key[0] should survive (recently used)"
        assert await cache.get(keys[1]) is None, "key[1] should be evicted (LRU)"
        assert await cache.get(new_key) is not None, "new key should be present"

    @pytest.mark.asyncio
    async def test_eviction_counter_increments(self):
        cache = WikiAuraCache(ttl_seconds=3600, max_entries=2)
        for i in range(3):
            await cache.set(_make_key(topic=f"t{i}"), _make_result(topic=f"t{i}"))

        stats = await cache.stats()
        assert stats.evictions == 1


# ── Invalidation Tests ─────────────────────────────────────────────────────────


class TestCacheInvalidation:
    @pytest.fixture
    def cache(self):
        return WikiAuraCache(ttl_seconds=3600, max_entries=50)

    @pytest.mark.asyncio
    async def test_invalidate_by_topic_removes_matching(self, cache):
        k1 = _make_key(topic="Coffee", langs=["en"])
        k2 = _make_key(topic="Coffee", langs=["uk"])
        k3 = _make_key(topic="Tea", langs=["en"])

        await cache.set(k1, _make_result("Coffee"))
        await cache.set(k2, _make_result("Coffee"))
        await cache.set(k3, _make_result("Tea"))

        removed = await cache.invalidate("Coffee")
        assert removed == 2

        assert await cache.get(k1) is None
        assert await cache.get(k2) is None
        assert await cache.get(k3) is not None, "Tea entry should remain"

    @pytest.mark.asyncio
    async def test_invalidate_case_insensitive(self, cache):
        key = _make_key(topic="Coffee")
        await cache.set(key, _make_result("Coffee"))
        removed = await cache.invalidate("COFFEE")
        assert removed == 1
        assert await cache.get(key) is None

    @pytest.mark.asyncio
    async def test_invalidate_missing_topic_returns_zero(self, cache):
        removed = await cache.invalidate("NonExistentTopic")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_clear_removes_all(self, cache):
        for i in range(5):
            await cache.set(_make_key(topic=f"t{i}"), _make_result(f"t{i}"))

        removed = await cache.clear()
        assert removed == 5

        stats = await cache.stats()
        assert stats.total_entries == 0

    @pytest.mark.asyncio
    async def test_clear_resets_counters(self, cache):
        key = _make_key()
        await cache.set(key, _make_result())
        await cache.get(key)   # hit
        await cache.get(_make_key(topic="unknown"))  # miss

        await cache.clear()
        stats = await cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0


# ── Stats Tests ────────────────────────────────────────────────────────────────


class TestCacheStats:
    @pytest.fixture
    def cache(self):
        return WikiAuraCache(ttl_seconds=3600, max_entries=50)

    @pytest.mark.asyncio
    async def test_empty_cache_stats(self, cache):
        stats = await cache.stats()
        assert stats.total_entries == 0
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate_percent == 0.0
        assert stats.oldest_entry_age_seconds is None
        assert stats.estimated_memory_kb == 0.0

    @pytest.mark.asyncio
    async def test_stats_hit_rate_calculation(self, cache):
        key = _make_key()
        await cache.set(key, _make_result())

        await cache.get(key)                     # hit
        await cache.get(key)                     # hit
        await cache.get(_make_key(topic="x"))    # miss

        stats = await cache.stats()
        assert stats.hits == 2
        assert stats.misses == 1
        assert abs(stats.hit_rate_percent - 66.67) < 0.01

    @pytest.mark.asyncio
    async def test_stats_total_entries(self, cache):
        for i in range(4):
            await cache.set(_make_key(topic=f"t{i}"), _make_result(f"t{i}"))
        stats = await cache.stats()
        assert stats.total_entries == 4

    @pytest.mark.asyncio
    async def test_stats_memory_kb_nonzero_when_entries_present(self, cache):
        await cache.set(_make_key(), _make_result())
        stats = await cache.stats()
        assert stats.estimated_memory_kb > 0

    @pytest.mark.asyncio
    async def test_stats_oldest_age_is_non_negative(self, cache):
        await cache.set(_make_key(), _make_result())
        stats = await cache.stats()
        assert stats.oldest_entry_age_seconds is not None
        assert stats.oldest_entry_age_seconds >= 0

    @pytest.mark.asyncio
    async def test_stats_ttl_and_max_entries_match_config(self, cache):
        stats = await cache.stats()
        assert stats.ttl_seconds == 3600
        assert stats.max_entries == 50


# ── Concurrency Tests ──────────────────────────────────────────────────────────


class TestCacheConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_set_same_key(self):
        """Multiple concurrent writes to the same key must not corrupt state."""
        cache = WikiAuraCache(ttl_seconds=3600, max_entries=100)
        key = _make_key()

        async def write(n: int) -> None:
            r = _make_result()
            r.source_topic = str(n)
            await cache.set(key, r)

        await asyncio.gather(*[write(i) for i in range(20)])

        # After all writes, exactly one entry should exist
        stats = await cache.stats()
        assert stats.total_entries == 1
        # And it should be readable
        cached = await cache.get(key)
        assert cached is not None

    @pytest.mark.asyncio
    async def test_concurrent_get_after_set(self):
        """Multiple concurrent reads must all return the same result."""
        cache = WikiAuraCache(ttl_seconds=3600, max_entries=100)
        key = _make_key()
        result = _make_result()
        await cache.set(key, result)

        reads = await asyncio.gather(*[cache.get(key) for _ in range(20)])
        assert all(r is not None and r.topic == result.topic for r in reads)

    @pytest.mark.asyncio
    async def test_concurrent_set_different_keys(self):
        """Concurrent writes of 50 different keys must all persist."""
        cache = WikiAuraCache(ttl_seconds=3600, max_entries=100)
        keys = [_make_key(topic=f"t{i}") for i in range(50)]
        results = [_make_result(f"t{i}") for i in range(50)]

        await asyncio.gather(*[cache.set(k, r) for k, r in zip(keys, results)])

        stats = await cache.stats()
        assert stats.total_entries == 50
