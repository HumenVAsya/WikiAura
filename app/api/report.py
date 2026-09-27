"""PDF report API endpoint — generate a share-ready A4 PDF from analytics results."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.schemas.requests import TrendAnalyticsRequest, NaturalLanguageAnalyticsRequest
from app.services.analytics.facade import WikipediaTrendsAnalyzer
from app.services.charts import generate_trend_chart
from app.services.llm_parser import parse_user_query_to_schema
from app.services.report import generate_pdf_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["Reports"])


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/report/pdf",
    summary="Generate PDF Report",
    description=(
        "Run the full 4-stage analytics pipeline and return a single-page A4 PDF report.\n\n"
        "The PDF includes:\n"
        "- **Header**: topic, language edition list, date range\n"
        "- **Trend chart**: embedded dark-theme PNG\n"
        "- **Metric badges**: attention share, MoM, YoY, direction — per language\n"
        "- **AI Executive Summary**: trend synthesis, key drivers, business takeaway\n"
        "- **Data Quality**: confidence, anomalies, assumptions, limitations\n"
        "- **Footer**: generation timestamp and Wikimedia attribution\n\n"
        "Returns `application/pdf` with `Content-Disposition: attachment`."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Single A4-page dark-theme PDF report",
        }
    },
)
async def report_pdf(payload: TrendAnalyticsRequest) -> Response:
    """Generate and return a full PDF report for the given topic."""
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

        chart_png = generate_trend_chart(result)
        pdf_bytes = generate_pdf_report(result, chart_png=chart_png)

        slug = result.topic.replace(" ", "_").lower()
        start = (result.start_date or "")[:6]
        end = (result.end_date or "")[:6]
        filename = f"wikiaura_{slug}_{start}_{end}.pdf"

        return _pdf_response(pdf_bytes, filename)

    except Exception as exc:
        logger.exception("report/pdf failed for topic '%s': %s", payload.topic, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post(
    "/report/pdf/natural-language",
    summary="Natural Language → PDF Report",
    description=(
        "Parse a free-form natural language query via Gemini and return a full PDF report.\n\n"
        "Example query: *'Звіт по тренду Intermittent fasting в Україні та Польщі за 2023 рік'*"
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Single A4-page PDF report generated from natural language query",
        }
    },
)
async def report_pdf_natural_language(payload: NaturalLanguageAnalyticsRequest) -> Response:
    """Parse query, run analytics, and return PDF report."""
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

        chart_png = generate_trend_chart(result)
        pdf_bytes = generate_pdf_report(result, chart_png=chart_png)

        slug = result.topic.replace(" ", "_").lower()
        start = (result.start_date or "")[:6]
        end = (result.end_date or "")[:6]
        filename = f"wikiaura_{slug}_{start}_{end}.pdf"

        return _pdf_response(pdf_bytes, filename)

    except Exception as exc:
        logger.exception("report/pdf/nl failed for query '%s': %s", payload.query, exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
