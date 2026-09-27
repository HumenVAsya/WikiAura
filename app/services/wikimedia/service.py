"""Business logic and orchestration service for multilingual Wikipedia trends retrieval."""

from __future__ import annotations

import asyncio
from typing import List, Optional
import urllib.parse
import httpx

from app.schemas.requests import LanguagePageviewsResult
from app.services.wikimedia import client as wiki_client

MAX_CONCURRENT_REQUESTS = 5


async def fetch_language_pageviews(
    client: httpx.AsyncClient,
    lang: str,
    article_title: Optional[str],
    start_date: str,
    end_date: str,
    granularity: str = "monthly",
) -> LanguagePageviewsResult:
    """Fetch pageview metrics for a resolved article title or mark as not found."""
    if not article_title:
        return LanguagePageviewsResult(
            language=lang,
            article_title=None,
            article_slug=None,
            found=False,
            total_views=0,
            items=[],
        )

    slug = article_title.replace(" ", "_")
    safe_slug = urllib.parse.quote(slug, safe="")

    items = await wiki_client.get_pageviews(
        client=client,
        lang=lang,
        article_slug=safe_slug,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )

    total_views = sum(item.views for item in items)

    return LanguagePageviewsResult(
        language=lang,
        article_title=article_title,
        article_slug=safe_slug,
        found=True,
        total_views=total_views,
        items=items,
    )


async def fetch_all_languages_data(
    client: httpx.AsyncClient,
    base_topic: str,
    language_codes: List[str],
    start_date: str,
    end_date: str,
    granularity: str = "monthly",
    max_concurrency: int = MAX_CONCURRENT_REQUESTS,
    source_topic: Optional[str] = None,
) -> List[LanguagePageviewsResult]:
    """Orchestrate concurrent resolution of localized titles and fetch pageviews with semaphore rate limiting."""
    semaphore = asyncio.Semaphore(max_concurrency)
    is_all = "all" in language_codes or "*" in language_codes

    title_map = await wiki_client.resolve_localized_titles(
        client,
        base_topic=base_topic,
        language_codes=language_codes,
        source_topic=source_topic,
    )
    target_langs = list(title_map.keys()) if is_all else language_codes

    async def fetch_with_semaphore(lang: str, title: Optional[str]) -> LanguagePageviewsResult:
        async with semaphore:
            if is_all:
                await asyncio.sleep(0.015)
            return await fetch_language_pageviews(
                client=client,
                lang=lang,
                article_title=title,
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
            )

    tasks = [
        fetch_with_semaphore(lang=lang, title=title_map.get(lang))
        for lang in target_langs
    ]
    return await asyncio.gather(*tasks)
