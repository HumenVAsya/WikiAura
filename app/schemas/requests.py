"""Pydantic schemas for WikiAura requests and responses."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, Field


def default_start_date() -> str:
    """Return default start date formatted as YYYYMMDD (1 year ago)."""
    return (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")


def default_end_date() -> str:
    """Return default end date formatted as YYYYMMDD (today)."""
    return datetime.now().strftime("%Y%m%d")


class WikipediaQueryParams(BaseModel):
    """Structured query parameters for Wikipedia pageview analysis resolved by LLM."""

    base_topic: str = Field(
        ...,
        description="The core topic translated to an exact English Wikipedia article title (e.g., 'Tobacco smoking').",
        examples=["Tobacco smoking"],
    )
    source_topic: Optional[str] = Field(
        default=None,
        description="Original localized topic name in user's query language if different from base_topic (e.g., 'єПідтримка' or 'Запорізька Січ').",
        examples=["єПідтримка"],
    )
    language_codes: List[str] = Field(
        default_factory=lambda: ["en"],
        description="List of ISO 639-1 language codes. If a region is mentioned, expanded to major languages of that region.",
        examples=[["en", "de", "fr", "es", "it", "pl", "uk", "nl", "cs"]],
    )
    start_date: str = Field(
        default_factory=default_start_date,
        description="Start date in YYYYMMDD format. Default to 1 year ago if not specified.",
        examples=["20250927"],
    )
    end_date: str = Field(
        default_factory=default_end_date,
        description="End date in YYYYMMDD format. Default to today if not specified.",
        examples=["20260927"],
    )
    granularity: str = Field(
        default="monthly",
        description="Pageview granularity: either 'daily' or 'monthly'. Default is 'monthly'.",
        examples=["monthly"],
    )


class AnalyzeTopicRequest(BaseModel):
    """Natural language query request payload."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural language query describing the topic, region, or timeframe.",
        examples=["статистика по всій європі по людям які люблять курити"],
    )


class WikiTrendAnalysisRequest(BaseModel):
    """Payload schema for manual Wikipedia trend analysis request."""

    base_topic: str = Field(
        ...,
        description="The main topic to analyze in the user's base language (e.g., 'Intermittent fasting').",
        examples=["Intermittent fasting"],
    )
    source_topic: Optional[str] = Field(
        default=None,
        description="Optional original localized topic name in user's query language.",
        examples=["єПідтримка"],
    )
    language_codes: List[str] = Field(
        ...,
        description="List of 2-letter Wikipedia language codes (e.g., ['pl', 'cs']).",
        examples=[["en", "pl", "cs"]],
    )
    start_date: str = Field(
        ...,
        description="Start date in YYYY-MM-DD or YYYYMMDD format.",
        examples=["2023-01-01"],
    )
    end_date: str = Field(
        ...,
        description="End date in YYYY-MM-DD or YYYYMMDD format.",
        examples=["2023-12-31"],
    )
    granularity: str = Field(
        default="monthly",
        description="Either 'daily' or 'monthly'.",
        examples=["monthly"],
    )
    generate_pdf: bool = Field(
        default=False,
        description="Whether to generate a PDF report (reserved for future phases).",
    )


AnalyzeRequest = WikiTrendAnalysisRequest


class PageviewItem(BaseModel):
    """Individual pageview record for a specific date or month."""

    timestamp: str = Field(..., description="Timestamp in Wikimedia format (e.g. '2023010100').")
    date: str = Field(..., description="Formatted date (e.g. '2023-01' or '2023-01-01').")
    views: int = Field(..., description="Number of user pageviews in this period.")
    is_partial: bool = Field(
        default=False,
        description="True if the period is currently ongoing and metrics are partial.",
    )


class LanguagePageviewsResult(BaseModel):
    """Pageview metrics and article metadata for a specific Wikipedia language edition."""

    language: str
    article_title: Optional[str] = None
    article_slug: Optional[str] = None
    found: bool = False
    total_views: int = 0
    items: List[PageviewItem] = Field(default_factory=list)


class WikiTrendAnalysisResponse(BaseModel):
    """Clean response schema containing resolved articles and pageviews data."""

    status: str = "success"
    topic: str
    granularity: str
    start_date: str
    end_date: str
    languages_analyzed: List[str]
    results: List[LanguagePageviewsResult]


class AnalyzeTopicResponse(BaseModel):
    """Response containing parsed natural language parameters and Wikipedia statistics."""

    status: str = "success"
    query: str
    parsed_params: WikipediaQueryParams
    results: List[LanguagePageviewsResult]


class TrendAnalyticsRequest(BaseModel):
    """Structured request for full 4-stage analytics engine."""

    topic: str = Field(
        ...,
        description="Wikipedia base topic to analyze (e.g. 'Coffee', 'Artificial intelligence').",
    )
    language_codes: List[str] = Field(
        default=["en"],
        description="List of ISO 639-1 language codes or region names (e.g. ['uk', 'pl'], ['europe']).",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date in YYYYMMDD or YYYY-MM-DD format (defaults to 1 year ago).",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date in YYYYMMDD or YYYY-MM-DD format (defaults to today).",
    )
    granularity: str = Field(
        default="monthly",
        pattern="^(monthly|daily)$",
        description="Aggregation interval ('monthly' or 'daily').",
    )
    source_topic: Optional[str] = Field(
        default=None,
        description="Native language article title hub (e.g. 'єПідтримка', 'Кава').",
    )
    include_ai_summary: bool = Field(
        default=True,
        description="Whether to generate AI executive synthesis and insights.",
    )


class NaturalLanguageAnalyticsRequest(BaseModel):
    """Natural language request for complete 4-stage analytics engine."""

    query: str = Field(
        ...,
        min_length=2,
        description="Natural language query (e.g. 'Покажи тренди єПідтримки в Україні та Польщі за рік')",
    )
    include_ai_summary: bool = Field(
        default=True,
        description="Whether to generate AI executive synthesis and insights.",
    )
