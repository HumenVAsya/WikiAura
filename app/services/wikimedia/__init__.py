"""Wikimedia integration package providing utilities, client, and orchestration service."""

from app.services.wikimedia.client import (
    PAGEVIEWS_API_BASE,
    USER_AGENT,
    WIKI_API_URL,
    create_wikimedia_client,
    get_http_client,
    get_pageviews,
    resolve_localized_titles,
    search_article_title_fallback,
)
from app.services.wikimedia.service import (
    MAX_CONCURRENT_REQUESTS,
    fetch_all_languages_data,
    fetch_language_pageviews,
)
from app.services.wikimedia.utils import (
    align_date_for_pageviews,
    format_date_for_pageviews,
    format_period_label,
    is_current_period,
)

__all__ = [
    "MAX_CONCURRENT_REQUESTS",
    "PAGEVIEWS_API_BASE",
    "USER_AGENT",
    "WIKI_API_URL",
    "align_date_for_pageviews",
    "create_wikimedia_client",
    "fetch_all_languages_data",
    "fetch_language_pageviews",
    "format_date_for_pageviews",
    "format_period_label",
    "get_http_client",
    "get_pageviews",
    "is_current_period",
    "resolve_localized_titles",
    "search_article_title_fallback",
]
