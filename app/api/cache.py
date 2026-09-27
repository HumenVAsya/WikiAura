"""Cache management API endpoints — stats, invalidation, and clear."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.cache import CacheStatsDTO, analytics_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cache", tags=["Cache"])


class InvalidateResponse(BaseModel):
    topic: str
    entries_removed: int
    message: str


class ClearResponse(BaseModel):
    entries_removed: int
    message: str


@router.get(
    "/stats",
    response_model=CacheStatsDTO,
    summary="Cache Statistics",
    description=(
        "Return a real-time snapshot of the in-memory analytics cache.\n\n"
        "Includes:\n"
        "- `total_entries` — number of cached results currently stored\n"
        "- `hit_rate_percent` — cache efficiency since last restart\n"
        "- `hits` / `misses` — absolute counters\n"
        "- `evictions` — LRU eviction count\n"
        "- `estimated_memory_kb` — approximate memory footprint\n"
        "- `oldest_entry_age_seconds` — age of least-recently-used entry\n"
        "- `ttl_seconds` — configured entry time-to-live (default: 21600 = 6h)\n"
        "- `max_entries` — LRU capacity limit"
    ),
)
async def cache_stats() -> CacheStatsDTO:
    """Return point-in-time cache statistics."""
    return await analytics_cache.stats()


@router.post(
    "/invalidate",
    response_model=InvalidateResponse,
    summary="Invalidate Topic Cache",
    description=(
        "Remove all cached analytics results for a specific topic (case-insensitive).\n\n"
        "Useful when you suspect stale data or want to force a fresh Wikimedia API fetch "
        "for a topic that was recently queried.\n\n"
        "Example: `POST /api/v1/cache/invalidate?topic=Coffee`"
    ),
)
async def cache_invalidate(
    topic: Annotated[
        str,
        Query(description="Topic name to invalidate (case-insensitive, matches all language combinations)."),
    ],
) -> InvalidateResponse:
    """Remove all cache entries matching the given topic."""
    removed = await analytics_cache.invalidate(topic)
    return InvalidateResponse(
        topic=topic,
        entries_removed=removed,
        message=f"Removed {removed} cache entry/entries for topic '{topic}'.",
    )


@router.post(
    "/clear",
    response_model=ClearResponse,
    summary="Clear Entire Cache",
    description=(
        "Remove **all** cached analytics results and reset hit/miss/eviction counters.\n\n"
        "> **Warning**: This forces all subsequent requests to perform fresh Wikimedia API "
        "fetches until the cache warms up again. Use sparingly."
    ),
)
async def cache_clear() -> ClearResponse:
    """Clear the entire cache and reset all statistics."""
    removed = await analytics_cache.clear()
    return ClearResponse(
        entries_removed=removed,
        message=f"Cache cleared. Removed {removed} entries and reset all counters.",
    )
