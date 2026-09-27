"""Chart API endpoints — generate PNG visualizations from analytics results."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.schemas.requests import TrendAnalyticsRequest, NaturalLanguageAnalyticsRequest
from app.services.analytics.facade import WikipediaTrendsAnalyzer
from app.services.charts import (
    generate_comparison_chart,
    generate_sparklines,
    generate_trend_chart,
)
from app.services.llm_parser import parse_user_query_to_schema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["Charts"])


def _png_response(png_bytes: bytes, filename: str) -> Response:
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post(
    "/chart/trend",
    summary="Trend Chart",
    description=(
        "Run the full 4-stage analytics pipeline and return a publication-ready PNG trend chart.\n\n"
        "The chart includes:\n"
        "- Rolling-average time-series lines per language (dark theme)\n"
        "- Anomaly spike markers\n"
        "- Market-share donut\n"
        "- Per-language MoM / YoY / direction badges"
    ),
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "PNG trend chart"}},
)
async def chart_trend(payload: TrendAnalyticsRequest) -> Response:
    """Return a trend time-series chart as PNG bytes."""
    try:
        analyzer = WikipediaTrendsAnalyzer()
        result = await analyzer.analyze_topic(
            topic=payload.topic,
            language_codes=payload.language_codes,
            start_date=payload.start_date,
            end_date=payload.end_date,
            granularity=payload.granularity,
            source_topic=payload.source_topic,
            include_ai_summary=payload.include_ai_summary,
        )
        png = generate_trend_chart(result)
        filename = f"trend_{result.topic.replace(' ', '_').lower()}.png"
        return _png_response(png, filename)
    except Exception as exc:
        logger.exception("chart/trend failed for topic '%s': %s", payload.topic, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/chart/compare",
    summary="Comparison Bar Chart",
    description=(
        "Run the full analytics pipeline and return a 3-panel PNG bar chart comparing:\n"
        "- Total pageviews per language\n"
        "- Month-over-Month growth rates\n"
        "- Year-over-Year growth rates"
    ),
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "PNG comparison chart"}},
)
async def chart_compare(payload: TrendAnalyticsRequest) -> Response:
    """Return a cross-language comparison bar chart as PNG bytes."""
    try:
        analyzer = WikipediaTrendsAnalyzer()
        result = await analyzer.analyze_topic(
            topic=payload.topic,
            language_codes=payload.language_codes,
            start_date=payload.start_date,
            end_date=payload.end_date,
            granularity=payload.granularity,
            source_topic=payload.source_topic,
            include_ai_summary=False,
        )
        png = generate_comparison_chart(result)
        filename = f"compare_{result.topic.replace(' ', '_').lower()}.png"
        return _png_response(png, filename)
    except Exception as exc:
        logger.exception("chart/compare failed for topic '%s': %s", payload.topic, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/chart/sparklines",
    summary="Sparkline Grid",
    description=(
        "Run the full analytics pipeline and return a compact sparkline grid PNG.\n\n"
        "One mini chart per language edition — ideal for reports and dashboards."
    ),
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "PNG sparkline grid"}},
)
async def chart_sparklines(payload: TrendAnalyticsRequest) -> Response:
    """Return a sparkline grid PNG with one cell per language."""
    try:
        analyzer = WikipediaTrendsAnalyzer()
        result = await analyzer.analyze_topic(
            topic=payload.topic,
            language_codes=payload.language_codes,
            start_date=payload.start_date,
            end_date=payload.end_date,
            granularity=payload.granularity,
            source_topic=payload.source_topic,
            include_ai_summary=False,
        )
        png = generate_sparklines(result)
        filename = f"sparklines_{result.topic.replace(' ', '_').lower()}.png"
        return _png_response(png, filename)
    except Exception as exc:
        logger.exception("chart/sparklines failed for topic '%s': %s", payload.topic, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/chart/natural-language",
    summary="Natural Language → Trend Chart",
    description=(
        "Parse a natural language query via Gemini, run the analytics pipeline, "
        "and return a PNG trend chart.\n\n"
        "Supports Ukrainian, English, or any language. "
        "Example: *'Покажи тренди кави в Україні та Польщі за рік'*"
    ),
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "PNG trend chart from NL query"}},
)
async def chart_natural_language(
    payload: NaturalLanguageAnalyticsRequest,
    chart_type: Literal["trend", "compare", "sparklines"] = "trend",
) -> Response:
    """Parse a free-form query and return the requested chart type."""
    try:
        parsed = await parse_user_query_to_schema(payload.query)

        analyzer = WikipediaTrendsAnalyzer()
        result = await analyzer.analyze_topic(
            topic=parsed.base_topic,
            language_codes=parsed.language_codes,
            start_date=parsed.start_date,
            end_date=parsed.end_date,
            granularity=parsed.granularity,
            source_topic=parsed.source_topic,
            include_ai_summary=payload.include_ai_summary,
        )

        slug = result.topic.replace(" ", "_").lower()
        if chart_type == "compare":
            png = generate_comparison_chart(result)
            return _png_response(png, f"compare_{slug}.png")
        elif chart_type == "sparklines":
            png = generate_sparklines(result)
            return _png_response(png, f"sparklines_{slug}.png")
        else:
            png = generate_trend_chart(result)
            return _png_response(png, f"trend_{slug}.png")

    except Exception as exc:
        logger.exception("chart/natural-language failed for query '%s': %s", payload.query, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
