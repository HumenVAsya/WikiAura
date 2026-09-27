from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status
import httpx

from app.schemas.requests import (
    AnalyzeTopicRequest,
    AnalyzeTopicResponse,
    WikiTrendAnalysisRequest,
    WikiTrendAnalysisResponse,
)
from app.services.llm_parser import parse_user_query_to_schema
from app.services.wikimedia import fetch_all_languages_data, get_http_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])


@router.post(
    "/analyze",
    response_model=WikiTrendAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch Wikipedia pageviews across languages",
    description="Resolves localized article titles and retrieves per-article pageview metrics across requested languages.",
)
@router.post(
    "/api/v1/analyze",
    response_model=WikiTrendAnalysisResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def analyze_trends(
    payload: WikiTrendAnalysisRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
) -> WikiTrendAnalysisResponse:
    """Handle Wikipedia trend data retrieval across languages."""
    try:
        results = await fetch_all_languages_data(
            client=client,
            base_topic=payload.base_topic,
            language_codes=payload.language_codes,
            start_date=payload.start_date,
            end_date=payload.end_date,
            granularity=payload.granularity,
            source_topic=payload.source_topic,
        )

        return WikiTrendAnalysisResponse(
            status="success",
            topic=payload.base_topic,
            granularity=payload.granularity,
            start_date=payload.start_date,
            end_date=payload.end_date,
            languages_analyzed=payload.language_codes,
            results=results,
        )
    except Exception as exc:
        logger.exception("Error executing Wikipedia request for topic '%s': %s", payload.base_topic, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Wikipedia data for topic '{payload.base_topic}': {exc}",
        ) from exc


@router.post(
    "/api/v1/analyze-topic",
    response_model=AnalyzeTopicResponse,
    status_code=status.HTTP_200_OK,
    summary="Natural language Wikipedia trend analysis",
    description="Parses natural language query via Gemini into structured parameters and retrieves Wikipedia pageview metrics.",
)
@router.post(
    "/analyze-topic",
    response_model=AnalyzeTopicResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def analyze_topic_natural_language(
    payload: AnalyzeTopicRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
) -> AnalyzeTopicResponse:
    """Parse natural language query into structured WikipediaQueryParams and fetch pageviews."""
    try:
        parsed_params = await parse_user_query_to_schema(payload.query)

        results = await fetch_all_languages_data(
            client=client,
            base_topic=parsed_params.base_topic,
            language_codes=parsed_params.language_codes,
            start_date=parsed_params.start_date,
            end_date=parsed_params.end_date,
            granularity=parsed_params.granularity,
            source_topic=parsed_params.source_topic,
        )

        return AnalyzeTopicResponse(
            status="success",
            query=payload.query,
            parsed_params=parsed_params,
            results=results,
        )
    except ValueError as exc:
        logger.error("Configuration or parsing validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error analyzing topic for query '%s': %s", payload.query, exc)
        error_msg = str(exc).lower()
        if "quota" in error_msg or "credit balance" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"LLM quota or balance exceeded: {exc}",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze topic for query '{payload.query}': {exc}",
        ) from exc

