"""Facade Pattern implementation orchestrating the 4-stage analytics pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional
import httpx
import instructor
import pandas as pd

from app.constants.regions import expand_region_codes
from app.schemas.analytics import (
    AnalyticsResultDTO,
    ComparisonMetricsDTO,
    LanguageAnalyticsDTO,
    TrendMetricsDTO,
)
from app.schemas.requests import LanguagePageviewsResult
from app.services.analytics.cleaner import standardize_pageviews_to_dataframe
from app.services.analytics.interpreter import synthesize_trend_insights
from app.services.analytics.strategies import (
    ComparisonAnalysisStrategy,
    TrendAnalysisStrategy,
)
from app.services.cache import CacheKey, analytics_cache
from app.services.wikimedia.client import create_wikimedia_client
from app.services.wikimedia.service import fetch_all_languages_data

logger = logging.getLogger(__name__)


class WikipediaTrendsAnalyzer:
    """Facade orchestrating the 4-stage analytical engine (Ingestion -> Standardization -> Computation -> Synthesis)."""

    def __init__(
        self,
        trend_strategy: Optional[TrendAnalysisStrategy] = None,
        comparison_strategy: Optional[ComparisonAnalysisStrategy] = None,
    ) -> None:
        self.trend_strategy = trend_strategy or TrendAnalysisStrategy()
        self.comparison_strategy = comparison_strategy or ComparisonAnalysisStrategy()

    async def analyze_topic(
        self,
        topic: str,
        language_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        granularity: str = "monthly",
        source_topic: Optional[str] = None,
        include_ai_summary: bool = True,
        client: Optional[httpx.AsyncClient] = None,
        instructor_client: Optional[instructor.AsyncInstructor] = None,
    ) -> AnalyticsResultDTO:
        """Run the complete 4-stage analytics pipeline for a topic across language editions."""
        today = datetime.now()
        resolved_end = end_date or today.strftime("%Y%m%d")
        if not start_date:
            resolved_start = (today - timedelta(days=365)).strftime("%Y%m%d")
        else:
            resolved_start = start_date

        raw_languages = language_codes or ["en"]
        resolved_languages = expand_region_codes(raw_languages)

        # ── Stage 0: Cache lookup ────────────────────────────────────────────
        cache_key = CacheKey.build(
            topic=topic,
            language_codes=resolved_languages,
            start_date=resolved_start,
            end_date=resolved_end,
            granularity=granularity,
            include_ai_summary=include_ai_summary,
        )
        cached = await analytics_cache.get(cache_key)
        if cached is not None:
            return cached

        logger.info(
            "Fetching Wikipedia data for topic '%s' (hub: %s) across %d language(s)...",
            topic,
            source_topic,
            len(resolved_languages),
        )

        async def _run_fetch(http_client: httpx.AsyncClient) -> List[LanguagePageviewsResult]:
            return await fetch_all_languages_data(
                client=http_client,
                base_topic=topic,
                language_codes=resolved_languages,
                start_date=resolved_start,
                end_date=resolved_end,
                granularity=granularity,
                source_topic=source_topic,
            )

        if client is not None:
            raw_responses = await _run_fetch(client)
        else:
            async with create_wikimedia_client() as default_client:
                raw_responses = await _run_fetch(default_client)

        language_results: Dict[str, LanguageAnalyticsDTO] = {}
        standardized_dfs: Dict[str, pd.DataFrame] = {}
        language_metrics_map: Dict[str, TrendMetricsDTO] = {}

        for resp in raw_responses:
            lang = resp.language
            if not resp.found:
                language_results[lang] = LanguageAnalyticsDTO(
                    language=lang,
                    article_title=resp.article_title,
                    found=False,
                    metrics=None,
                    time_series=[],
                )
                continue

            df = standardize_pageviews_to_dataframe(
                items=resp.items,
                start_date=resolved_start,
                end_date=resolved_end,
                granularity=granularity,
            )
            standardized_dfs[lang] = df

            metrics_dto, time_series_points = self.trend_strategy.analyze(
                df=df,
                granularity=granularity,
            )
            language_metrics_map[lang] = metrics_dto

            language_results[lang] = LanguageAnalyticsDTO(
                language=lang,
                article_title=resp.article_title,
                found=True,
                metrics=metrics_dto,
                time_series=time_series_points,
            )

        comparison_dto: Optional[ComparisonMetricsDTO] = None
        if standardized_dfs:
            comparison_dto = self.comparison_strategy.compare(
                language_dfs=standardized_dfs,
                language_metrics=language_metrics_map,
            )

        ai_interpretation = None
        if include_ai_summary and language_metrics_map:
            logger.info("Synthesizing AI executive business interpretation...")
            ai_interpretation = await synthesize_trend_insights(
                topic=topic,
                start_date=resolved_start,
                end_date=resolved_end,
                granularity=granularity,
                language_metrics=language_metrics_map,
                comparison=comparison_dto,
                source_topic=source_topic,
                client=instructor_client,
            )

        result = AnalyticsResultDTO(
            topic=topic,
            source_topic=source_topic,
            granularity=granularity,
            start_date=resolved_start,
            end_date=resolved_end,
            languages=language_results,
            comparison=comparison_dto,
            ai_interpretation=ai_interpretation,
        )

        # ── Stage 5: Cache store ─────────────────────────────────────────────
        await analytics_cache.set(cache_key, result)
        return result
