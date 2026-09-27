"""Schemas package."""

from app.schemas.requests import (
    AnalyzeRequest,
    AnalyzeTopicRequest,
    AnalyzeTopicResponse,
    LanguagePageviewsResult,
    PageviewItem,
    WikipediaQueryParams,
    WikiTrendAnalysisRequest,
    WikiTrendAnalysisResponse,
)

__all__ = [
    "AnalyzeRequest",
    "AnalyzeTopicRequest",
    "AnalyzeTopicResponse",
    "LanguagePageviewsResult",
    "PageviewItem",
    "WikipediaQueryParams",
    "WikiTrendAnalysisRequest",
    "WikiTrendAnalysisResponse",
]
