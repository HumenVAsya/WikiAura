"""Raw HTTP client functions for English Wikipedia and Wikimedia REST APIs."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional
import httpx

from app.schemas.requests import PageviewItem
from app.services.wikimedia.utils import (
    WIKIMEDIA_MIN_DATE,
    align_date_for_pageviews,
    format_date_for_pageviews,
    format_period_label,
    is_current_period,
)

logger = logging.getLogger(__name__)

WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_API_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
USER_AGENT = "B2C-WikiAura-Agent/1.0 (https://github.com/WikiAura; contact@wikiaura.io)"


def get_wiki_api_url(lang: str = "en") -> str:
    """Return the MediaWiki Action API URL for a given language edition."""
    subdomain = "no" if lang == "nb" else lang
    return f"https://{subdomain}.wikipedia.org/w/api.php"


def create_wikimedia_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Create an AsyncClient preconfigured with standard Wikimedia User-Agent and timeout."""
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=timeout)


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """FastAPI dependency yielding an AsyncClient configured with standard User-Agent and timeout."""
    async with create_wikimedia_client() as client:
        yield client


async def search_article_title_fallback(
    client: httpx.AsyncClient,
    query: str,
    lang: str = "en",
) -> Optional[str]:
    """Search for the best-matching Wikipedia article title if direct resolution failed."""
    api_url = get_wiki_api_url(lang)
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "format": "json",
    }
    try:
        response = await client.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        search_hits = data.get("query", {}).get("search", [])
        if search_hits and "title" in search_hits[0]:
            hit_title = search_hits[0]["title"]
            logger.info("Search fallback (%s) resolved '%s' -> '%s'", lang, query, hit_title)
            return hit_title
        suggestion = data.get("query", {}).get("searchinfo", {}).get("suggestion")
        if suggestion:
            logger.info("Search fallback (%s) found suggestion '%s' -> '%s'", lang, query, suggestion)
            return suggestion
    except Exception as exc:
        logger.warning("Search fallback (%s) failed for '%s': %s", lang, query, exc)
    return None


async def resolve_localized_titles(
    client: httpx.AsyncClient,
    base_topic: str,
    language_codes: List[str],
    source_topic: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Resolve localized article titles across Wikipedia language editions using prop=langlinks.

    Supports dynamic multilingual starting hubs: if an article is missing on English Wikipedia
    or is a native concept (e.g. Ukrainian, German, Polish local phenomenon), it automatically
    resolves via the native language hub edition.
    """
    is_all_languages = "all" in language_codes or "*" in language_codes
    requested_set = set(language_codes)

    async def _fetch_langlinks_data(topic: str, lang: str = "en") -> dict:
        api_url = get_wiki_api_url(lang)
        params = {
            "action": "query",
            "prop": "langlinks|pageprops",
            "titles": topic,
            "redirects": "1",
            "lllimit": "max",
            "format": "json",
        }
        resp = await client.get(api_url, params=params)
        resp.raise_for_status()
        return resp.json()

    is_cyrillic = any("\u0400" <= c <= "\u04FF" for c in base_topic)
    candidates = []

    local_lang = next((l for l in language_codes if l != "en" and l != "all"), "uk")

    if is_cyrillic:
        candidates.append((base_topic, local_lang))
        candidates.append((base_topic, "en"))
    else:
        candidates.append((base_topic, "en"))
        if source_topic:
            candidates.append((source_topic, local_lang))
        elif local_lang and local_lang != "en":
            candidates.append((base_topic, local_lang))

    resolved_pages: dict = {}
    active_hub_lang = "en"

    for candidate_topic, hub_lang in candidates:
        try:
            data = await _fetch_langlinks_data(candidate_topic, lang=hub_lang)
            pages = data.get("query", {}).get("pages", {})

            is_missing_or_disambig = False
            if not pages or "-1" in pages:
                is_missing_or_disambig = True
            else:
                for page_id, page_info in pages.items():
                    if not isinstance(page_info, dict) or "missing" in page_info:
                        is_missing_or_disambig = True
                        break
                    pageprops = page_info.get("pageprops", {})
                    if "disambiguation" in pageprops:
                        is_missing_or_disambig = True
                        break

            if is_missing_or_disambig:
                fallback_title = await search_article_title_fallback(client, candidate_topic, lang=hub_lang)
                if fallback_title and fallback_title.lower() != candidate_topic.lower():
                    logger.info("Retrying langlinks on %s with fallback title '%s'", hub_lang, fallback_title)
                    fallback_data = await _fetch_langlinks_data(fallback_title, lang=hub_lang)
                    fb_pages = fallback_data.get("query", {}).get("pages", {})
                    has_valid = fb_pages and "-1" not in fb_pages and not any("missing" in p for p in fb_pages.values() if isinstance(p, dict))
                    if has_valid:
                        resolved_pages = fb_pages
                        active_hub_lang = hub_lang
                        break
            else:
                resolved_pages = pages
                active_hub_lang = hub_lang
                break
        except Exception as exc:
            logger.warning("Error checking hub (%s, %s): %s", candidate_topic, hub_lang, exc)

    if not resolved_pages:
        return {} if is_all_languages else {lang: None for lang in language_codes}

    if is_all_languages:
        all_lang_map: Dict[str, Optional[str]] = {}
        for page_id, page_info in resolved_pages.items():
            if not isinstance(page_info, dict) or page_id == "-1" or "missing" in page_info:
                continue
            canonical_title = page_info.get("title", base_topic)
            norm_hub = "no" if active_hub_lang == "nb" else active_hub_lang
            all_lang_map[norm_hub] = canonical_title
            for item in page_info.get("langlinks", []):
                lang = item.get("lang")
                title = item.get("*")
                if lang and title:
                    norm_lang = "no" if lang == "nb" else lang
                    all_lang_map[norm_lang] = title
        return all_lang_map

    lang_map: Dict[str, Optional[str]] = {lang: None for lang in language_codes}

    for page_id, page_info in resolved_pages.items():
        if not isinstance(page_info, dict) or page_id == "-1" or "missing" in page_info:
            continue

        canonical_title = page_info.get("title", base_topic)
        if active_hub_lang in requested_set:
            lang_map[active_hub_lang] = canonical_title
        elif active_hub_lang == "nb" and "no" in requested_set:
            lang_map["no"] = canonical_title
        elif active_hub_lang == "no" and "nb" in requested_set:
            lang_map["nb"] = canonical_title

        langlinks = page_info.get("langlinks", [])
        for item in langlinks:
            lang = item.get("lang")
            title = item.get("*")
            if not lang or not title:
                continue
            if lang in requested_set:
                lang_map[lang] = title
            elif lang == "nb" and "no" in requested_set and lang_map.get("no") is None:
                lang_map["no"] = title
            elif lang == "no" and "nb" in requested_set and lang_map.get("nb") is None:
                lang_map["nb"] = title

    return lang_map


async def get_pageviews(
    client: httpx.AsyncClient,
    lang: str,
    article_slug: str,
    start_date: str,
    end_date: str,
    granularity: str = "monthly",
) -> List[PageviewItem]:
    """Fetch per-article pageview metrics from Wikimedia REST API.

    Aligns date boundaries according to granularity and marks ongoing periods as partial.
    """
    start_formatted = align_date_for_pageviews(start_date, is_end=False, granularity=granularity)
    end_formatted = align_date_for_pageviews(end_date, is_end=True, granularity=granularity)

    if end_formatted < WIKIMEDIA_MIN_DATE:
        logger.info(
            "Requested end date %s is before Wikimedia Pageviews availability (2015-07-01). Returning empty metrics.",
            end_date,
        )
        return []
    if start_formatted < WIKIMEDIA_MIN_DATE:
        start_formatted = WIKIMEDIA_MIN_DATE

    api_lang = "no" if lang == "nb" else lang

    url = (
        f"{PAGEVIEWS_API_BASE}/"
        f"{api_lang}.wikipedia.org/all-access/user/{article_slug}/{granularity}/"
        f"{start_formatted}/{end_formatted}"
    )

    try:
        response = await client.get(url)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 1.0))
            await asyncio.sleep(min(retry_after, 2.0))
            response = await client.get(url)
        if response.status_code == 404:
            logger.info("Pageviews not found (404) for '%s' in '%s'", article_slug, lang)
            return []
        response.raise_for_status()
        data = response.json()
        raw_items = data.get("items", [])

        parsed_items: List[PageviewItem] = []
        for item in raw_items:
            ts = str(item.get("timestamp", ""))
            views = int(item.get("views", 0))
            formatted_date = format_period_label(ts, granularity=granularity)
            is_partial = is_current_period(ts, granularity=granularity)
            parsed_items.append(
                PageviewItem(
                    timestamp=ts,
                    date=formatted_date,
                    views=views,
                    is_partial=is_partial,
                )
            )

        return parsed_items
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return []
        logger.error("HTTP status error fetching pageviews for '%s' (%s): %s", article_slug, lang, exc)
        return []
    except httpx.HTTPError as exc:
        logger.error("HTTP error fetching pageviews for '%s' (%s): %s", article_slug, lang, exc)
        return []
    except Exception as exc:
        logger.error("Unexpected error fetching pageviews for '%s' (%s): %s", article_slug, lang, exc)
        return []
